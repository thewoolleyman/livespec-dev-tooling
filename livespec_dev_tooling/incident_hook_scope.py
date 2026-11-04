"""Bind repair markers, cumulative paths and the exact existing-PR update."""

from __future__ import annotations

import json
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

__all__: list[str] = ["HookCall", "validate_scope"]
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
_MAX_STDIN = 16384
_PUSH_FIELDS = 4
_PUSH_ARGUMENTS = 2


@dataclass(frozen=True, kw_only=True)
class HookCall:
    """The actual Git hook arguments and its bounded ref-update input."""

    hook: str
    extra: tuple[str, ...]
    stdin: str


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


def _push(
    *, query: dict[str, Any], attempt: dict[str, Any], stdin: str, extra: tuple[str, ...]
) -> dict[str, str]:
    if type(attempt.get("pr_number")) is not int or attempt["pr_number"] <= 0:
        _fail(detail="initial pre-PR push requires canonical carrier-ref support")
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
    result = gh_read(
        args=["api", f"repos/{query['repository']}/pulls/{attempt['pr_number']}"], timeout=10
    )
    pr = mapping(value=json.loads(result.stdout))
    source, base = mapping(value=pr.get("head")), mapping(value=pr.get("base"))
    branch = source.get("ref")
    if (
        result.returncode != 0
        or pr.get("state") != "open"
        or pr.get("merged") is not False
        or type(pr.get("number")) is not int
        or pr.get("number") != attempt["pr_number"]
        or not isinstance(branch, str)
        or local != "refs/heads/" + branch
        or remote != local
        or source.get("sha") != previous
        or base.get("sha") != attempt["base"]
        or mapping(value=source.get("repo")).get("full_name") != query["repository"]
        or mapping(value=base.get("repo")).get("full_name") != query["repository"]
    ):
        _fail(detail="push update does not match the current canonical existing PR")
    return dict(local_ref=local, local_sha=head, remote_ref=remote, remote_sha=previous)


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
    hook, extra, stdin = call.hook, call.extra, call.stdin
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
        _push(query=query, attempt=attempt, stdin=stdin, extra=extra)
        if hook == "pre-push"
        else None
    )
    return dict(original_paths=sorted(paths), marker=marker, push_update=push)
