"""Recorded incident provenance for the `red_green_replay` commit-range gate.

An expedited commit defers replay, so it carries no TDD trailers and the range
gate has to learn from somewhere else that the deferral was authorized. That
somewhere is the canonical incident chain, read on the observer's host through
its query-only `/provenance` route, because CI holds no tenant credential.

Nothing the candidate writes grants this. The PR's `livespec-incident-ci` block
only locates which attempt to ask about, and the `Factory-Override` trailer only
has to be present and name that item: an agent can write both. What admits a
commit is the chain recording the PR's exact base and head, with the commit
inside that head's history. Labels and incident flags are never read, so the
answer holds after they are gone. Every other outcome keeps the commit convicted
on its missing evidence (contracts `Expedited incident execution`).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_dev_tooling.incident_ci_authority import CiAuthorityBoundary
from livespec_dev_tooling.incident_ci_event import incident_block
from livespec_dev_tooling.incident_ci_payload import decode_authority

if TYPE_CHECKING:
    from livespec_dev_tooling.incident_ci_payload import CiAuthority
    from livespec_dev_tooling.incident_execution import OperationIdentity

__all__: list[str] = ["admitted_by_recorded_incident"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zbzls2
_REFUSAL_PREFIX = "incident-provenance-refused: "
_URL = "LIVESPEC_INCIDENT_OBSERVER_URL"
_TOKEN = "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN"


def _refuse(*, sha: str, reason: str) -> bool:
    _ = sys.stderr.write(_REFUSAL_PREFIX + sha + ": " + reason + "\n")
    return False


def _mapping(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _pull_request(*, environ: Mapping[str, str]) -> dict[str, Any]:
    """The event's pull request, or nothing outside a readable pull_request event."""
    if environ.get("GITHUB_EVENT_NAME") != "pull_request":
        return {}
    try:
        text = Path(environ.get("GITHUB_EVENT_PATH", "")).read_text(encoding="utf-8")
        return _mapping(value=_mapping(value=json.loads(text)).get("pull_request"))
    except (OSError, ValueError):
        return {}


def _git(*, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _unmet(
    *,
    sha: str,
    message: str,
    pull_request: dict[str, Any],
    authority: CiAuthority,
    identity: OperationIdentity,
    environ: Mapping[str, str],
) -> str | None:
    """The first local reason not to ask the observer at all, or None."""
    head = _mapping(value=pull_request.get("head")).get("sha")
    base = _mapping(value=pull_request.get("base")).get("sha")
    if (pull_request.get("number"), base, head) != (
        authority.pr_number,
        identity.base_sha,
        identity.head_sha,
    ):
        return "the block names a different pull request, base or head"
    trailer = "Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag: " + identity.incident_item_id
    if trailer not in message.splitlines():
        return "the commit has no audited trailer naming the incident"
    if _git(args=["merge-base", "--is-ancestor", sha, identity.head_sha]).returncode != 0:
        return "the commit is not in the recorded head's history"
    if not environ.get(_URL) or not environ.get(_TOKEN):
        return "the observer URL or query token is not configured"
    return None


def admitted_by_recorded_incident(
    *, sha: str, message: str, environ: Mapping[str, str] = os.environ
) -> bool:
    """Whether the canonical chain records this PR head, with `sha` in its history."""
    pull_request = _pull_request(environ=environ)
    body = pull_request.get("body")
    block = incident_block(body=body) if isinstance(body, str) else None
    if block is None:
        return False
    authority = decode_authority(payload=block)
    identity = None if authority is None else authority.context.identity
    if authority is None or identity is None:
        return _refuse(sha=sha, reason="the livespec-incident-ci block does not decode")
    unmet = _unmet(
        sha=sha,
        message=message,
        pull_request=pull_request,
        authority=authority,
        identity=identity,
        environ=environ,
    )
    if unmet is not None:
        return _refuse(sha=sha, reason=unmet)
    recorded = CiAuthorityBoundary(
        observer_url=environ[_URL], observer_token=environ[_TOKEN]
    ).provenance(
        query={
            "repository": identity.repository,
            "item_id": identity.incident_item_id,
            "attempt_id": identity.attempt_id,
            "phase": identity.phase,
            "operation_id": identity.operation_id,
            "generation": authority.generation,
            "owner": authority.owner,
            "base": identity.base_sha,
            "head": identity.head_sha,
            "pr_number": authority.pr_number,
            "commit_sha": identity.head_sha,
            "tree_sha": _git(args=["rev-parse", identity.head_sha + "^{tree}"]).stdout.strip(),
        }
    )
    return recorded or _refuse(sha=sha, reason="the observer does not record this head")
