"""Consume canonical authority and bind the exact local Git operation.

Only the registered producer reads incident state. This module checks its
process protocol and local carrier consistency, never caller JSON authority.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, NoReturn, cast

from livespec_dev_tooling.flake_retry_filer import registered_plugin_root
from livespec_dev_tooling.incident_execution import (
    ExecutionContext,
    Invocation,
    OperationIdentity,
    resolve_execution_context,
)
from livespec_dev_tooling.incident_transport import CONTEXT_ENV, decode_execution_context

__all__: list[str] = [
    "AUTHORITY_CALL_CEILING_SECONDS",
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
# A hang guard for one canonical authority call, never a verdict. Measured on the
# dev host 2026-11-08 (livespec-dev-tooling-yaprm4): read-local-gates took 21-39 s
# and grows with the chain's generation, so a 30 s bound refused live expedited
# commits. Ten minutes stops a hung wrapper or ledger without deciding a slow one.
AUTHORITY_CALL_CEILING_SECONDS = 600
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
    value = mapping(value=json.loads(text))
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
    command = [
        "/usr/local/bin/with-livespec-env.sh",
        "--",
        "python3",
        str(plugin / "scripts/bin/incident_authority.py"),
        action,
        "--repo",
        str(governed),
    ]
    for name, value in query.items():
        command.extend(["--" + name, str(value)])
    if receipt is not None:
        command.extend(["--receipt-json", receipt])
    if receipt_id is not None:
        command.extend(["--receipt-id", receipt_id])
    try:
        done = subprocess.run(  # noqa: S603 — fixed registered executable; structured query argv.
            command,
            cwd=repo,
            text=True,
            capture_output=True,
            timeout=AUTHORITY_CALL_CEILING_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        _fail(
            detail=f"registered canonical incident process {action} exceeded its"
            f" {AUTHORITY_CALL_CEILING_SECONDS} s liveness ceiling"
        )
    response = mapping(value=json.loads(done.stdout))
    if (
        done.returncode
        or response.get("schema") != 1
        or type(response.get("schema")) is not int
        or response.get("status") != "verified"
        or response.get("normal_factory_proof") is not False
    ):
        _fail(detail="registered canonical incident process refused or returned invalid proof")
    if response.get("authorizes_current_effects") is not (action == "read-current"):
        _fail(detail="registered canonical incident process returned wrong authority kind")
    return mapping(value=response["result"])


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
    recorded = attempt.get("landed_commits")
    landed = cast("list[str]", recorded) if isinstance(recorded, list) else []
    identity = OperationIdentity(
        incident_item_id=attempt["item_id"],
        attempt_id=attempt["attempt_id"],
        phase=attempt["phase"],
        repository=attempt["repository"],
        base_sha=attempt["base"],
        head_sha=attempt["head"],
        operation_id=attempt["operation_id"],
        recorded_incident_merge_sha=landed[-1]
        if attempt["phase"] == "reverting" and landed
        else None,
    )
    resolved = resolve_execution_context(
        environ=os.environ, invocation=Invocation.ORDINARY, identity=identity
    )
    if not resolved.is_successful:
        refusal = resolved.failure()
        _fail(detail=f"{refusal.code}: {refusal.detail}")
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
