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

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from livespec_dev_tooling.checks._red_green_replay_merge_group import locate_queued_pull_request
from livespec_dev_tooling.incident_ci_authority import (
    CiAuthorityBoundary,
    ObserverTokenError,
    ObserverUnreachableError,
)
from livespec_dev_tooling.incident_ci_event import incident_block
from livespec_dev_tooling.incident_ci_payload import decode_authority
from livespec_dev_tooling.incident_git import IncidentGitError, git_text, run_git
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

if TYPE_CHECKING:
    from livespec_dev_tooling.incident_ci_payload import CiAuthority
    from livespec_dev_tooling.incident_execution import OperationIdentity

__all__: list[str] = ["admitted_by_recorded_incident"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zbzls2
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-a6wgjz
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
        return _mapping(
            value=_mapping(value=strict_json(text=text, limit=None)).get("pull_request")
        )
    except (OSError, ValueError, IncidentJsonRefusalError):
        return {}


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
    trailer = _trailer_unmet(message=message, identity=identity)
    if trailer is not None:
        return trailer
    try:
        ancestor = run_git(
            repo=Path.cwd(),
            args=["merge-base", "--is-ancestor", sha, identity.head_sha],
            check=False,
        )
    except IncidentGitError as error:
        return str(error)
    if ancestor.returncode != 0:
        return "the commit is not in the recorded head's history"
    return _unconfigured(environ=environ)


def _trailer_unmet(*, message: str, identity: OperationIdentity) -> str | None:
    trailer = "Factory-Override: EXPEDITED_INCIDENT_RESPONSE flag: " + identity.incident_item_id
    if trailer in message.splitlines():
        return None
    return "the commit has no audited trailer naming the incident"


def _unconfigured(*, environ: Mapping[str, str]) -> str | None:
    if environ.get(_URL) and environ.get(_TOKEN):
        return None
    return "the observer URL or query token is not configured"


def _no_block(*, sha: str, event: str | None) -> bool:
    """No block was found: name it on a pull_request event, with the source read.

    Scenario "incident commit provenance remains verifiable on normal master": the
    replay gate prints a line naming the missing block and the source it read, and
    keeps the commit convicted. A merge_group event never reaches here: it is judged by
    queue attribution (livespec-dev-tooling-txon2s), and any other event is not an
    incident pull request run, so it stays silent (livespec-dev-tooling-yfrepg).
    """
    if event == "pull_request":
        return _refuse(sha=sha, reason="no livespec-incident-ci block in the pull_request body")
    return False


def admitted_by_recorded_incident(
    *, sha: str, message: str, environ: Mapping[str, str] = os.environ
) -> bool:
    """Whether the canonical chain records this PR head, with `sha` in its history."""
    if environ.get("GITHUB_EVENT_NAME") == "merge_group":
        return _admitted_in_merge_group(sha=sha, message=message, environ=environ)
    pull_request = _pull_request(environ=environ)
    body = pull_request.get("body")
    block = incident_block(body=body) if isinstance(body, str) else None
    if block is None:
        return _no_block(sha=sha, event=environ.get("GITHUB_EVENT_NAME"))
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
    return _recorded(sha=sha, authority=authority, identity=identity, environ=environ)


def _admitted_in_merge_group(*, sha: str, message: str, environ: Mapping[str, str]) -> bool:
    """Admit a rebased copy the queue attributed to one pull request, by the same chain."""
    located = locate_queued_pull_request(sha=sha, environ=environ)
    if isinstance(located, str):
        return _refuse(sha=sha, reason=located)
    unmet = _trailer_unmet(message=message, identity=located.identity) or _unconfigured(
        environ=environ
    )
    if unmet is not None:
        return _refuse(sha=sha, reason=unmet)
    return _recorded(
        sha=sha, authority=located.authority, identity=located.identity, environ=environ
    )


def _recorded(
    *, sha: str, authority: CiAuthority, identity: OperationIdentity, environ: Mapping[str, str]
) -> bool:
    """Whether the observer's chain records the identity's head, asked through its query route."""
    try:
        tree_sha = git_text(repo=Path.cwd(), args=["rev-parse", identity.head_sha + "^{tree}"])
    except IncidentGitError as error:
        return _refuse(sha=sha, reason=str(error))
    query = {
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
        "tree_sha": tree_sha,
    }
    return _observer_records(sha=sha, query=query, environ=environ)


def _observer_records(*, sha: str, query: dict[str, Any], environ: Mapping[str, str]) -> bool:
    """Whether the observer's canonical chain records `query`; each refusal names its cause."""
    boundary = CiAuthorityBoundary(observer_url=environ[_URL], observer_token=environ[_TOKEN])
    try:
        recorded = boundary.provenance(query=query)
    except ObserverTokenError:
        return _refuse(
            sha=sha,
            reason="the observer query token is not a valid header value; no request was made",
        )
    except ObserverUnreachableError:
        return _refuse(sha=sha, reason="the observer is unreachable, so this head was not checked")
    return recorded or _refuse(sha=sha, reason="the observer does not record this head")
