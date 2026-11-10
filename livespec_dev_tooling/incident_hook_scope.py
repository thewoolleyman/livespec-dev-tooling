"""Bind repair markers, cumulative paths and the exact canonical carrier push."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling.budgeted_gh import gh_read  # noqa: E402
from livespec_dev_tooling.incident_execution import ExecutionContext  # noqa: E402
from livespec_dev_tooling.incident_hook_process import (  # noqa: E402
    HookRefusalError,
    git_text,
    mapping,
)
from livespec_dev_tooling.incident_markers import validate_python_repair_marker  # noqa: E402
from livespec_dev_tooling.incident_strict_json import strict_json  # noqa: E402

__all__: list[str] = ["HookCall", "validate_scope"]
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
_MAX_STDIN = 16384
_PUSH_FIELDS = 4
_PUSH_ARGUMENTS = 2
# The discriminated carrier states the orchestrator publishes on `attempt.carrier`
# (livespec-orchestrator-beads-fabro `_incident_carrier.py`; its
# SPECIFICATION/contracts.md binds carrier identity before and after PR
# creation). A pre-PR state carries no PR number.
_PRE_PR_STATES = frozenset(("branch-reserved", "head-published"))
_CARRIER_STATES = _PRE_PR_STATES | {"pr-bound"}


@dataclass(frozen=True, kw_only=True)
class HookCall:
    """The actual Git hook arguments and its bounded ref-update input."""

    hook: str
    extra: tuple[str, ...]
    stdin: str


@dataclass(frozen=True, kw_only=True)
class _RefUpdate:
    """The single identified branch update Git handed the pre-push hook."""

    local: str
    head: str
    remote: str
    previous: str


def _fail(*, detail: str) -> NoReturn:
    raise HookRefusalError(detail)


def _marker(*, repo: Path, paths: set[str], tree: str, item: str) -> str:
    for path in sorted(paths):
        if not path.endswith(".py") or not git_text(
            repo=repo, args=["ls-tree", "--name-only", tree, "--", path]
        ):
            continue
        source = git_text(repo=repo, args=["show", f"{tree}:{path}"])
        if is_successful(validate_python_repair_marker(source=source, incident_item_id=item)):
            return path
    _fail(detail="no legal Python comment carrier in the cumulative changed scope")


def _carrier(*, attempt: dict[str, Any]) -> dict[str, Any]:
    if "carrier" not in attempt:
        _fail(detail="current attempt publishes no canonical carrier state")
    carrier = mapping(value=attempt["carrier"])
    if carrier.get("state") not in _CARRIER_STATES:
        _fail(detail="unsupported canonical carrier state")
    return carrier


def _update(
    *, query: dict[str, Any], attempt: dict[str, Any], stdin: str, extra: tuple[str, ...]
) -> _RefUpdate:
    rows = stdin.splitlines()
    if len(stdin) > _MAX_STDIN or len(rows) != 1 or len(rows[0].split()) != _PUSH_FIELDS:
        _fail(detail="exactly one identified branch update is required")
    local, head, remote, previous = rows[0].split()
    destinations = {
        "https://github.com/" + query["repository"],
        "git@github.com:" + query["repository"],
    }
    if (
        len(extra) != _PUSH_ARGUMENTS
        or extra[0] != "origin"
        or extra[1].removesuffix(".git") not in destinations
        or head != attempt["head"]
    ):
        _fail(detail="push does not name the approved origin/head")
    return _RefUpdate(local=local, head=head, remote=remote, previous=previous)


def _reserved(*, repo: Path, carrier: dict[str, Any], tree: str, update: _RefUpdate) -> None:
    """A pre-PR push lands only on the reserved ref, at its recorded precondition."""
    absent = set(update.previous) == {"0"}
    expected_previous = (
        absent
        if carrier["state"] == "branch-reserved"
        else update.previous == carrier.get("remote_head")
    )
    if (
        update.local != carrier.get("target_ref")
        or update.remote != update.local
        or tree != carrier.get("staged_tree")
        or git_text(repo=repo, args=["rev-parse", update.head + "^"]) != carrier.get("input_parent")
        or not expected_previous
    ):
        _fail(detail="push does not match the reserved canonical carrier branch")


def _bound(
    *, query: dict[str, Any], attempt: dict[str, Any], carrier: dict[str, Any], update: _RefUpdate
) -> None:
    """A pr-bound push updates exactly the open PR the carrier is bound to."""
    if type(attempt.get("pr_number")) is not int or attempt["pr_number"] <= 0:
        _fail(detail="pr-bound carrier requires a positive canonical PR number")
    result = gh_read(
        args=["api", f"repos/{query['repository']}/pulls/{attempt['pr_number']}"], timeout=10
    )
    pr = mapping(value=strict_json(text=result.stdout, limit=None))
    source, base = mapping(value=pr.get("head")), mapping(value=pr.get("base"))
    branch = source.get("ref")
    if (
        result.returncode != 0
        or pr.get("state") != "open"
        or pr.get("merged") is not False
        or type(pr.get("number")) is not int
        or pr.get("number") != attempt["pr_number"]
        or not isinstance(branch, str)
        or update.local != "refs/heads/" + branch
        or update.local != carrier.get("target_ref")
        or update.remote != update.local
        or source.get("sha") != update.previous
        or base.get("sha") != attempt["base"]
        or mapping(value=source.get("repo")).get("full_name") != query["repository"]
        or mapping(value=base.get("repo")).get("full_name") != query["repository"]
    ):
        _fail(detail="push update does not match the current canonical existing PR")


def _push(
    *,
    repo: Path,
    query: dict[str, Any],
    attempt: dict[str, Any],
    tree: str,
    call: HookCall,
) -> dict[str, str]:
    carrier = _carrier(attempt=attempt)
    update = _update(query=query, attempt=attempt, stdin=call.stdin, extra=call.extra)
    if carrier["state"] in _PRE_PR_STATES:
        _reserved(repo=repo, carrier=carrier, tree=tree, update=update)
    else:
        _bound(query=query, attempt=attempt, carrier=carrier, update=update)
    return dict(
        local_ref=update.local,
        local_sha=update.head,
        remote_ref=update.remote,
        remote_sha=update.previous,
        carrier_state=carrier["state"],
    )


def validate_scope(
    *,
    repo: Path,
    context: ExecutionContext,
    reading: dict[str, Any],
    query: dict[str, Any],
    tree: str,
    call: HookCall,
) -> dict[str, Any]:
    """Refuse unsupported authority scopes before selecting any quality gate."""
    hook, extra = call.hook, call.extra
    if context.mode != "expedited-repair" or context.identity is None:
        _fail(detail="host emergency revert requires the separately trusted inverse boundary")
    attempt = mapping(value=reading["attempt"])
    original = attempt.get("original_paths")
    values = cast("list[object]", original) if isinstance(original, list) else []
    if not values or not all(isinstance(v, str) for v in values):
        _fail(detail="canonical cumulative scope is missing")
    original = cast("list[str]", values)
    paths = set(
        git_text(repo=repo, args=["diff", "--name-only", attempt["base"], tree, "--"]).splitlines()
    )
    if not paths or not paths.issubset(original):
        _fail(detail="changed paths escape the canonical cumulative scope")
    if any(path.startswith(".github/workflows/") for path in paths):
        _fail(detail="workflow publication requires separately scoped canonical authorization")
    if hook == "commit-msg" and (
        not extra
        or not any(
            line.startswith("Factory-Override:") and line.partition(":")[2].strip()
            for line in Path(extra[0]).read_text().splitlines()
        )
    ):
        _fail(detail="incident commit requires an audited nonempty Factory-Override trailer")
    marker = _marker(repo=repo, paths=paths, tree=tree, item=context.identity.incident_item_id)
    push = (
        _push(repo=repo, query=query, attempt=attempt, tree=tree, call=call)
        if hook == "pre-push"
        else None
    )
    return dict(original_paths=sorted(paths), marker=marker, push_update=push)
