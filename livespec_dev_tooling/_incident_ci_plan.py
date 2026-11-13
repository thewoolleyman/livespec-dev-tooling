"""Dependency closure and source-bound execution plans for incident CI policy."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import asdict

from livespec_dev_tooling._incident_ci_types import (
    CiAuthority,
    CiConditional,
    CiDeferral,
    CiEvent,
    CiPlan,
    CiTarget,
)
from livespec_dev_tooling.incident_execution import ExecutionContext, ExecutionMode, Invocation
from livespec_dev_tooling.incident_transport import child_environment

__all__: list[str] = [
    "NOT_RUN",
    "build_plan",
    "event_key",
    "execution_view",
    "select_incident_targets",
]

NOT_RUN = (
    "job not run on this event: its if: names the triggering event or ref,"
    " which the incident entrance does not evaluate"
)

_COVERAGE = ("check-coverage", "check-per-file-coverage", "check-check-coverage-incremental")
_SPEC = ("check-heading-coverage", "check-doctor", "check-spec-", "check-no-todo-registry")


def event_key(*, event: CiEvent, incident_label: str) -> tuple[object, ...]:
    return (
        event.kind,
        event.repository,
        event.base_sha,
        event.head_sha,
        event.pr_number,
        event.kind == "pull_request" and incident_label in event.labels,
    )


def execution_view(
    *, targets: tuple[CiTarget, ...]
) -> (
    tuple[
        tuple[CiTarget, ...],
        tuple[CiConditional, ...],
        tuple[tuple[str, tuple[str, ...]], ...],
    ]
    | None
):
    """One execution target per slug, the conditional-job lines, and every slug's jobs.

    A slug runs at most once however many unconditional jobs declare it, so
    those jobs must agree on its policy; a disagreement returns None and the
    caller refuses. Members of a conditional job are never executed: they are
    listed per job. Every declaring job, conditional or not, is attributed.
    """
    if len({(t.batch, t.name) for t in targets}) != len(targets):
        return None
    execution: dict[str, CiTarget] = {}
    jobs: dict[str, list[str]] = {}
    lines: dict[str, list[str]] = {}
    for target in targets:
        jobs.setdefault(target.name, []).append(target.batch)
        if target.conditional:
            lines.setdefault(target.batch, []).append(target.name)
            continue
        first = execution.setdefault(target.name, target)
        if (first.classification, first.needs, first.produces, first.consumes) != (
            target.classification,
            target.needs,
            target.produces,
            target.consumes,
        ):
            return None
    return (
        tuple(execution.values()),
        tuple(
            CiConditional(job=job, names=tuple(names), reason=NOT_RUN)
            for job, names in lines.items()
        ),
        tuple((name, tuple(declaring)) for name, declaring in jobs.items()),
    )


def _classification(*, target: CiTarget) -> str:
    if target.name.startswith(_COVERAGE):
        return "coverage"
    if target.name.startswith(_SPEC):
        return "spec"
    return target.classification


def _dependencies_ready(
    *, target: CiTarget, selected: set[str], targets: tuple[CiTarget, ...]
) -> bool:
    if any(name not in selected for name in target.needs):
        return False
    for artifact in target.consumes:
        producers = [t.name for t in targets if artifact in t.produces]
        if len(producers) != 1 or producers[0] not in selected:
            return False
    return True


def select_incident_targets(
    *, targets: tuple[CiTarget, ...]
) -> tuple[tuple[CiTarget, ...], tuple[CiDeferral, ...]]:
    selected = {t.name for t in targets if _classification(target=t) == "fast"}
    reasons = {
        t.name: f"incident-policy:{_classification(target=t)}"
        for t in targets
        if t.name not in selected
    }
    changed = True
    while changed:
        changed = False
        for target in targets:
            if target.name in selected and not _dependencies_ready(
                target=target, selected=selected, targets=targets
            ):
                selected.remove(target.name)
                reasons[target.name] = "incident-policy:deferred-dependency-or-artifact"
                changed = True
    return (
        tuple(t for t in targets if t.name in selected),
        tuple(
            CiDeferral(name=t.name, reason=reasons[t.name])
            for t in targets
            if t.name not in selected
        ),
    )


def build_plan(
    *,
    event: CiEvent,
    targets: tuple[CiTarget, ...],
    selection: tuple[tuple[CiTarget, ...], tuple[CiDeferral, ...]],
    authority: CiAuthority | None,
    environ: Mapping[str, str],
    incident_label: str,
) -> CiPlan:
    selected, deferred = selection
    context = (
        authority.context
        if authority is not None
        else ExecutionContext(
            mode=ExecutionMode.NORMAL,
            invocation=Invocation.NORMAL_MASTER if event.kind == "push" else Invocation.ORDINARY,
            identity=None,
        )
    )
    view = execution_view(targets=targets)
    conditional, attribution = ((), ()) if view is None else (view[1], view[2])
    # Environment values can contain secrets: they never enter the public scope digest.
    payload = {
        "schema": 1,
        "event": event_key(event=event, incident_label=incident_label),
        "mode": context.mode,
        "authority": None if authority is None else asdict(authority),
        "inventory": [asdict(t) for t in targets],
        "selected": [t.name for t in selected],
        "deferred": [asdict(t) for t in deferred],
    }
    scope = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # The canonical transport projects this already validated context.
    environment = child_environment(context=context, environ=environ).unwrap()
    return CiPlan(
        event=event,
        mode=context.mode,
        scope=scope,
        selected=selected,
        deferred=deferred,
        environment=tuple(sorted(environment.items())),
        authority=authority,
        incident_label=incident_label,
        attribution=attribution,
        conditional=conditional,
    )
