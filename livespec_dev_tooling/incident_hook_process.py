"""Consume canonical authority and bind the exact local Git operation.

Only the registered producer reads incident state. This module checks its
process protocol and local carrier consistency, never caller JSON authority.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, NoReturn, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling.flake_retry_filer import registered_plugin_root  # noqa: E402
from livespec_dev_tooling.incident_authority_client import (  # noqa: E402
    call_authority,
    registered_authority_command,
)
from livespec_dev_tooling.incident_execution import (  # noqa: E402
    ExecutionContext,
    Invocation,
    OperationIdentity,
    resolve_execution_context,
)
from livespec_dev_tooling.incident_strict_json import (  # noqa: E402
    IncidentJsonRefusalError,
    strict_json,
)
from livespec_dev_tooling.incident_transport import (  # noqa: E402
    CONTEXT_ENV,
    decode_execution_context,
)

__all__: list[str] = [
    "HookRefusalError",
    "canonical",
    "exact_tree",
    "git_text",
    "invoke_authority",
    "mapping",
    "parse_query",
    "resolve_current",
]
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
_QUERY_KEYS = frozenset(
    ("repository", "item", "attempt", "phase", "operation", "generation", "owner")
)
_TIMEOUT = 30
_MAX_QUERY = 16384


class HookRefusalError(Exception):
    """An unverifiable carrier refuses before ordinary work can run."""


def mapping(*, value: object) -> dict[str, Any]:
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def canonical(*, value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _fail(*, detail: str) -> NoReturn:
    raise HookRefusalError(detail)


def parse_query(*, text: str) -> dict[str, Any] | None:
    if len(text) > _MAX_QUERY:
        return None
    try:
        value = mapping(value=strict_json(text=text, limit=None))
    except IncidentJsonRefusalError:
        return None
    if frozenset(value) != _QUERY_KEYS or canonical(value=value) != text:
        return None
    if type(value["generation"]) is not int or value["generation"] <= 0:
        return None
    return (
        value
        if all(
            isinstance(v, str) and v and v.strip() == v
            for k, v in value.items()
            if k != "generation"
        )
        else None
    )


def _governed_root(*, repo: Path) -> Path:
    common = Path(
        git_text(repo=repo, args=["rev-parse", "--path-format=absolute", "--git-common-dir"])
    )
    if common.name != ".git":
        _fail(detail="registered incident lookup requires a standard governed primary")
    return common.parent.resolve()


def invoke_authority(
    *,
    repo: Path,
    query: dict[str, Any],
    action: str,
    receipt: str | None = None,
    receipt_id: str | None = None,
) -> dict[str, Any]:
    governed = _governed_root(repo=repo)
    plugin = registered_plugin_root(
        repo_root=governed, registry=Path.home() / ".claude/plugins/installed_plugins.json"
    )
    flags: dict[str, object] = {"repo": governed, **query}
    if receipt is not None:
        flags["receipt-json"] = receipt
    if receipt_id is not None:
        flags["receipt-id"] = receipt_id
    checked = call_authority(
        command=registered_authority_command(plugin_root=plugin),
        action=action,
        flags=flags,
        cwd=repo,
    )
    if not is_successful(checked):
        refusal = checked.failure()
        _fail(
            detail=f"registered canonical incident process refused {refusal.code}: {refusal.detail}"
        )
    return checked.unwrap()


def resolve_current(*, reading: dict[str, Any], query: dict[str, Any]) -> ExecutionContext:
    attempt = mapping(value=reading["attempt"])
    names = {
        "repository": "repository",
        "item": "item_id",
        "attempt": "attempt_id",
        "phase": "phase",
        "operation": "operation_id",
        "generation": "generation",
        "owner": "owner",
    }
    if reading.get("is_current") is not True or any(
        type(attempt.get(names[k])) is not type(v) or attempt.get(names[k]) != v
        for k, v in query.items()
    ):
        _fail(detail="canonical response does not bind current requested identity")
    identity = OperationIdentity(
        incident_item_id=attempt["item_id"],
        attempt_id=attempt["attempt_id"],
        phase=attempt["phase"],
        repository=attempt["repository"],
        base_sha=attempt["base"],
        head_sha=attempt["head"],
        operation_id=attempt["operation_id"],
        recorded_incident_merge_sha=attempt["landed_commits"][-1]
        if attempt["phase"] == "reverting" and attempt["landed_commits"]
        else None,
    )
    resolved = resolve_execution_context(
        environ=os.environ, invocation=Invocation.ORDINARY, identity=identity
    )
    if not resolved.is_successful:
        _fail(detail=resolved.failure().detail)
    context = resolved.unwrap()
    if (
        CONTEXT_ENV in os.environ
        and not decode_execution_context(
            payload=os.environ[CONTEXT_ENV], trusted_context=context
        ).is_successful
    ):
        _fail(detail="incident transport differs from canonical current context")
    return context


def git_text(*, repo: Path, args: list[str]) -> str:
    return subprocess.run(  # noqa: S603 — fixed git executable and structured argv.
        ["git", *args],  # noqa: S607 — git is the repository toolchain executable.
        cwd=repo,
        text=True,
        capture_output=True,
        timeout=_TIMEOUT,
        check=True,
    ).stdout.strip()


def exact_tree(*, repo: Path, context: ExecutionContext, hook: str) -> str:
    identity = context.identity
    if identity is None or git_text(repo=repo, args=["rev-parse", "HEAD"]) != identity.head_sha:
        _fail(detail="canonical head does not match local HEAD")
    if git_text(repo=repo, args=["symbolic-ref", "--short", "HEAD"]) in {"master", "main"}:
        _fail(detail="incident commits require a feature worktree branch")
    if git_text(repo=repo, args=["diff", "--name-only"]) or git_text(
        repo=repo, args=["ls-files", "--others", "--exclude-standard"]
    ):
        _fail(detail="working tree must equal the exact staged or committed scope")
    if hook == "pre-push" and git_text(repo=repo, args=["diff", "--cached", "--name-only"]):
        _fail(detail="push validation requires the committed tree without staged changes")
    remote = git_text(repo=repo, args=["config", "--get", "remote.origin.url"])
    accepted = {
        "https://github.com/" + identity.repository,
        "git@github.com:" + identity.repository,
    }
    if remote.removesuffix(".git") not in accepted:
        _fail(detail="canonical repository does not match local origin")
    if hook == "pre-push":
        targets = git_text(
            repo=repo, args=["remote", "get-url", "--push", "--all", "origin"]
        ).splitlines()
        if len(targets) != 1 or targets[0].removesuffix(".git") not in accepted:
            _fail(detail="resolved push destination is not the single canonical repository")
    return git_text(
        repo=repo, args=["rev-parse", "HEAD^{tree}"] if hook == "pre-push" else ["write-tree"]
    )
