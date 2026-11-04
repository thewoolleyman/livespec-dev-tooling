"""Select incident PR work only after current authority and observer admission.

This library does not authorize workflow edits or install weaker CI. Callers must
obtain the event and attempt from authenticated boundaries and pass independent
current-attempt and observer-arm readers. Candidate labels and serialized records
alone never confer permission. Normal events keep the complete supplied graph.
"""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
from __future__ import annotations

from collections.abc import Callable, Mapping

from livespec_dev_tooling._incident_ci_plan import (
    build_plan as _plan,
)
from livespec_dev_tooling._incident_ci_plan import (
    event_key as _event_key,
)
from livespec_dev_tooling._incident_ci_plan import (
    select_incident_targets as _incident_selection,
)
from livespec_dev_tooling._incident_ci_types import (
    CiAggregate,
    CiAuthority,
    CiDeferral,
    CiEvent,
    CiOutcome,
    CiPlan,
    CiTarget,
    CiTrust,
)
from livespec_dev_tooling.incident_execution import (
    ExecutionMode,
    IncidentConfigurationRefusal,
    validate_execution_context,
)
from livespec_dev_tooling.incident_transport import normal_child_environment

__all__: list[str] = [
    "CiAggregate",
    "CiAuthority",
    "CiDeferral",
    "CiEvent",
    "CiOutcome",
    "CiPlan",
    "CiTarget",
    "CiTrust",
    "aggregate_ci_results",
    "select_ci_plan",
]


def _refuse(*, code: str, detail: str) -> IncidentConfigurationRefusal:
    return IncidentConfigurationRefusal(code=code, detail=detail)


def _authority_matches(*, event: CiEvent, authority: CiAuthority) -> bool:
    if not validate_execution_context(context=authority.context).is_successful:
        return False
    identity = authority.context.identity
    return (
        authority.context.mode == ExecutionMode.EXPEDITED_REPAIR
        and identity is not None
        and identity.phase == "repair"
        and (identity.repository, identity.base_sha, identity.head_sha)
        == (event.repository, event.base_sha, event.head_sha)
        and type(event.pr_number) is int
        and event.pr_number > 0
        and type(authority.pr_number) is int
        and authority.pr_number == event.pr_number
        and type(authority.generation) is int
        and authority.generation > 0
        and bool(authority.owner and authority.receipt_digest and authority.observer_arm_id)
    )


def _authorize(
    *, event: CiEvent, authority: CiAuthority | None, trust: CiTrust
) -> CiAuthority | IncidentConfigurationRefusal:
    if authority is None or not _authority_matches(event=event, authority=authority):
        return _refuse(
            code="incident-ci-identity-mismatch",
            detail="label requires the exact authenticated repair attempt and PR/head",
        )
    if trust.current(authority) is not True:
        return _refuse(
            code="incident-ci-authority-refused",
            detail="current incident generation could not be authenticated",
        )
    if trust.observer(authority, event) is not True:
        return _refuse(
            code="incident-ci-observer-unarmed",
            detail="independent premerge observer admission is required",
        )
    return authority


def select_ci_plan(
    *,
    event: CiEvent,
    targets: tuple[CiTarget, ...],
    authority: CiAuthority | None,
    trust: CiTrust,
    environ: Mapping[str, str],
) -> CiPlan | IncidentConfigurationRefusal:
    """Select members, preserving complete normal graphs and refusing untrusted repair."""
    if (
        not targets
        or any(not t.name for t in targets)
        or len({t.name for t in targets}) != len(targets)
    ):
        return _refuse(
            code="invalid-ci-inventory", detail="CI targets must be nonempty and uniquely named"
        )
    requested = event.kind == "pull_request" and trust.incident_label in event.labels
    if not requested:
        return _plan(
            event=event,
            targets=targets,
            selection=(targets, ()),
            authority=None,
            environ=normal_child_environment(environ=environ),
            incident_label=trust.incident_label,
        )
    authorized = _authorize(event=event, authority=authority, trust=trust)
    if isinstance(authorized, IncidentConfigurationRefusal):
        return authorized
    selected, deferred = _incident_selection(targets=targets)
    if not selected:
        return _refuse(
            code="incident-ci-no-retained-checks",
            detail="an empty expedited gate is not merge evidence",
        )
    return _plan(
        event=event,
        targets=targets,
        selection=(selected, deferred),
        authority=authorized,
        environ=environ,
        incident_label=trust.incident_label,
    )


def _aggregate_plan_valid(*, plan: CiPlan, event: CiEvent, targets: tuple[CiTarget, ...]) -> bool:
    requested = event.kind == "pull_request" and plan.incident_label in event.labels
    if requested and (
        plan.authority is None or not _authority_matches(event=event, authority=plan.authority)
    ):
        return False
    selection = _incident_selection(targets=targets) if requested else (targets, ())
    expected = _plan(
        event=event,
        targets=targets,
        selection=selection,
        authority=plan.authority if requested else None,
        environ={},
        incident_label=plan.incident_label,
    )
    return (plan.scope, plan.mode, plan.selected, plan.deferred) == (
        expected.scope,
        expected.mode,
        expected.selected,
        expected.deferred,
    )


def aggregate_ci_results(
    *,
    plan: CiPlan,
    current_event: CiEvent,
    outcomes: tuple[CiOutcome, ...],
    targets: tuple[CiTarget, ...],
    observer_arm_admitted: Callable[[CiAuthority, CiEvent], bool],
) -> CiAggregate | IncidentConfigurationRefusal:
    """Publish real member outcomes only for the current head/mode and independent fence."""
    if _event_key(event=plan.event, incident_label=plan.incident_label) != _event_key(
        event=current_event, incident_label=plan.incident_label
    ):
        return _refuse(
            code="incident-ci-stale-event",
            detail="head, PR, base, repository or projected mode changed",
        )
    if (
        plan.authority is not None
        and observer_arm_admitted(plan.authority, current_event) is not True
    ):
        return _refuse(
            code="incident-ci-observer-refused",
            detail="the independent attempt/arm fence is no longer current",
        )
    if not _aggregate_plan_valid(plan=plan, event=current_event, targets=targets):
        return _refuse(
            code="incident-ci-invalid-plan",
            detail="plan does not match the independently supplied released CI inventory",
        )
    expected = {target.name for target in plan.selected}
    if any(
        o.name not in expected or o.head_sha != current_event.head_sha or o.scope != plan.scope
        for o in outcomes
    ) or len({o.name for o in outcomes}) != len(outcomes):
        return _refuse(
            code="incident-ci-invalid-outcomes",
            detail="foreign, duplicate or stale evidence cannot satisfy this execution plan",
        )
    by_name = {o.name: o.outcome for o in outcomes}
    return CiAggregate(
        head_sha=current_event.head_sha,
        scope=plan.scope,
        passed=tuple(t.name for t in plan.selected if by_name.get(t.name) == "passed"),
        failed=tuple(
            t.name for t in plan.selected if t.name in by_name and by_name[t.name] != "passed"
        ),
        missing=tuple(t.name for t in plan.selected if t.name not in by_name),
        deferred=plan.deferred,
    )
