"""The forge-free halves of the merge-queue rules of `branch_protection_alignment`.

Split from `_branch_protection_merge_queue.py` to keep it under the LLOC soft
ceiling. Nothing here talks to the forge: these functions grade answers the
reading module already holds, or read the repository's own workflow files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import structlog

from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.checks._merge_group_guard import routes_merge_group_to_self_hosted

__all__: list[str] = [
    "bypass_key_code",
    "bypass_mismatch",
    "parse_object",
    "queue_parameter_code",
    "restriction_state",
    "uses_guarded_merge_group",
]

_APP_ACTOR_TYPE = "Integration"
# The only bypass mode an incident-merge App may hold: it may merge a pull
# request around the queue, never push to the branch (contracts.md v246).
_INCIDENT_MERGE_BYPASS_MODE = "pull_request"
_OTHER_ACTOR = (
    "an active default-branch ruleset lets an actor other than the recovery App "
    "and the declared incident-merge App bypass the merge queue"
)
_INCIDENT_MERGE_MODE = (
    "the incident-merge App bypasses an active default-branch ruleset in a mode "
    "other than pull_request, so it could push to the branch directly"
)
_REBASE = "REBASE"
_CONCURRENCY_FLOOR = 2
# The built-in gating label `self_hosted_routing` always unions in.
_DEFAULT_GATING_LABELS = frozenset({"local-ci"})
_WORKFLOW_GLOBS = ("*.yml", "*.yaml")
# GitHub answers the classic push-restrictions read with this 404 message when
# the protected branch carries no push restrictions at all.
_RESTRICTIONS_NOT_ENABLED = "Push restrictions not enabled"
_RESTRICTION_HOLDERS = ("users", "teams", "apps")


def parse_object(*, completed: GhRead) -> dict[str, object] | None:
    """A successful read's JSON object; None for a failed read or a malformed body."""
    if completed.returncode != 0:
        return None
    try:
        parsed: object = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return None
    return cast("dict[str, object]", parsed) if isinstance(parsed, dict) else None


def restriction_state(*, completed: GhRead) -> str:
    """Classify the classic push-restrictions read: `none`, `exception` or `unreadable`.

    "none" needs `users`, `teams` and `apps` all PRESENT as empty lists; a
    non-empty one is an exception. A failed read other than GitHub's "not
    enabled" answer, a malformed body, or an object of any other shape is
    unreadable, never "no restrictions".
    """
    combined = f"{completed.stdout}\n{completed.stderr}"
    if completed.returncode != 0 and _RESTRICTIONS_NOT_ENABLED in combined:
        return "none"
    body = parse_object(completed=completed)
    if body is None:
        return "unreadable"
    holders = [body.get(key) for key in _RESTRICTION_HOLDERS]
    if not all(isinstance(holder, list) for holder in holders):
        return "unreadable"
    return "exception" if any(cast("list[list[object]]", holders)) else "none"


def uses_guarded_merge_group(*, workflows_dir: Path, gating_labels: tuple[str, ...]) -> bool:
    """Whether any workflow routes `merge_group` to gating self-hosted capacity."""
    labels = _DEFAULT_GATING_LABELS | frozenset(gating_labels)
    paths = sorted(p for glob in _WORKFLOW_GLOBS for p in workflows_dir.glob(glob))
    sources = (path.read_text(encoding="utf-8") for path in paths)
    return any(
        routes_merge_group_to_self_hosted(source=source, gating_labels=labels) for source in sources
    )


def queue_parameter_code(*, log: structlog.stdlib.BoundLogger, rule: dict[str, object]) -> int:
    """Grade one `merge_queue` rule's build concurrency and merge method."""
    raw = rule.get("parameters")
    params = cast("dict[str, object]", raw) if isinstance(raw, dict) else {}
    build = params.get("max_entries_to_build")
    code = 0
    if type(build) is not int or build < _CONCURRENCY_FLOOR:
        log.error(
            "the merge queue builds fewer than 2 entries at once",
            failure_mode="merge_queue_concurrency_below_floor",
            ruleset_id=rule.get("ruleset_id"),
            max_entries_to_build=build,
        )
        code = 4
    if params.get("merge_method") != _REBASE:
        log.error(
            "the merge queue does not rebase-merge; master accepts only rebase-merges",
            failure_mode="merge_queue_method_not_rebase",
            ruleset_id=rule.get("ruleset_id"),
            merge_method=params.get("merge_method"),
        )
        code = 4
    return code


def bypass_key_code(
    *, log: structlog.stdlib.BoundLogger, ids: tuple[int | None, int | None]
) -> int:
    """Grade the declared (recovery, incident-merge) App ids: `4` or `0`.

    An undeclared recovery id cannot tell the recovery App from any other App,
    and one App cannot hold both roles: the recovery principal stays the
    inverse-only principal (contracts.md v246).
    """
    recovery_app_id, incident_merge_app_id = ids
    if recovery_app_id is None:
        log.error(
            "recovery_bypass_integration_id is not declared, so the recovery App "
            "cannot be told from any other bypass actor",
            failure_mode="merge_queue_bypass_path",
            hint="declare recovery_bypass_integration_id in [tool.livespec_dev_tooling]",
        )
        return 4
    if incident_merge_app_id == recovery_app_id:
        log.error(
            "incident_merge_integration_id equals recovery_bypass_integration_id; "
            "the recovery App must stay the inverse-only principal",
            failure_mode="merge_queue_bypass_path",
            hint="declare a separate App as the incident-merge principal",
        )
        return 4
    return 0


def bypass_mismatch(
    *, actors: list[object], recovery_app_id: int, incident_merge_app_id: int | None
) -> str | None:
    """Why a ruleset's bypass list is not exactly the admitted Integrations, or None.

    The recovery `Integration` is required. The declared incident-merge
    `Integration` is optional: a declared key whose `Integration` is not yet on
    the ruleset is the not-yet-armed state, so declaring is the adoption and
    adding it to the ruleset is the arming (contracts.md v247). When present it
    must hold `pull_request` bypass mode, because that principal merges a pull
    request and must never be able to push to the branch. Any other actor, and
    any duplicate, is refused.
    """
    admitted = (
        {recovery_app_id}
        if incident_merge_app_id is None
        else {recovery_app_id, incident_merge_app_id}
    )
    apps = [
        cast("dict[str, object]", actor)
        for actor in actors
        if isinstance(actor, dict)
        and cast("dict[str, object]", actor).get("actor_type") == _APP_ACTOR_TYPE
    ]
    ids = [app.get("actor_id") for app in apps]
    if (
        len(apps) != len(actors)
        or len(set(ids)) != len(ids)
        or recovery_app_id not in ids
        or not set(ids) <= admitted
    ):
        return _OTHER_ACTOR
    modes = [app.get("bypass_mode") for app in apps if app.get("actor_id") == incident_merge_app_id]
    if any(mode != _INCIDENT_MERGE_BYPASS_MODE for mode in modes):
        return _INCIDENT_MERGE_MODE
    return None
