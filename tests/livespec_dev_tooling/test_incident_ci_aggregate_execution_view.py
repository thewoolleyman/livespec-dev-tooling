"""The aggregate refuses a plan over an inventory with no runnable execution view.

`_aggregate_plan_valid` must not lean on its callers: a forged plan whose
selection is empty is invalid for an inventory that has no valid execution
view, or whose view runs nothing, on push and pull-request events alike
(livespec-dev-tooling-yzr6ad, coordinator grade fix 1). The aggregate receipt
carries the plan's conditional-job lines (grade fix 2).
"""

from __future__ import annotations

import pytest

from livespec_dev_tooling._incident_ci_plan import build_plan
from livespec_dev_tooling.incident_ci_policy import (
    CiAggregate,
    CiAuthority,
    CiEvent,
    CiOutcome,
    CiPlan,
    CiTarget,
    CiTrust,
    aggregate_ci_results,
    select_ci_plan,
)
from livespec_dev_tooling.incident_execution import (
    ExecutionContext,
    ExecutionMode,
    IncidentConfigurationRefusal,
    Invocation,
    OperationIdentity,
)

_LABEL = "expedited-incident-response"
_TRUST = CiTrust(current=lambda _a: True, observer=lambda _a, _e: True)


def _target(
    *, name: str, batch: str, classification: str = "fast", conditional: bool = False
) -> CiTarget:
    return CiTarget(name=name, classification=classification, batch=batch, conditional=conditional)


def _event(*, kind: str, labels: tuple[str, ...] = ()) -> CiEvent:
    return CiEvent(
        kind=kind,
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=None if kind == "push" else 7,
        labels=labels,
    )


_UNRUNNABLE = {
    "no targets": (),
    "a repeated job and slug pair": (
        _target(name="check-x", batch="a"),
        _target(name="check-x", batch="a"),
    ),
    "declaring jobs that disagree": (
        _target(name="check-x", batch="a"),
        _target(name="check-x", batch="b", classification="slow"),
    ),
    "only conditional members": (_target(name="check-x", batch="gate", conditional=True),),
}


@pytest.mark.parametrize("kind", ["push", "pull_request"])
@pytest.mark.parametrize("case", sorted(_UNRUNNABLE))
def test_a_forged_empty_selection_plan_is_refused_for_an_unrunnable_inventory(
    *, kind: str, case: str
) -> None:
    targets = _UNRUNNABLE[case]
    event = _event(kind=kind)
    forged = build_plan(
        event=event,
        targets=targets,
        selection=((), ()),
        authority=None,
        environ={},
        incident_label=_LABEL,
    )
    result = aggregate_ci_results(
        plan=forged,
        current_event=event,
        outcomes=(),
        targets=targets,
        observer_arm_admitted=lambda _a, _e: True,
    )
    assert isinstance(
        result, IncidentConfigurationRefusal
    ), f"a forged empty-selection plan over {case} must be refused, got {result!r}"
    assert result.code == "incident-ci-invalid-plan"


def _authority() -> CiAuthority:
    identity = OperationIdentity(
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        phase="repair",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        operation_id="repair-op",
    )
    return CiAuthority(
        context=ExecutionContext(
            mode=ExecutionMode.EXPEDITED_REPAIR, invocation=Invocation.ORDINARY, identity=identity
        ),
        generation=1,
        owner="operator:alice",
        pr_number=7,
        receipt_digest="d" * 64,
        observer_arm_id="arm-1",
    )


def test_the_aggregate_receipt_lists_the_conditional_job_members():
    targets = (
        _target(name="check-shared", batch="batch-a"),
        _target(name="check-shared", batch="release-gate", conditional=True),
        _target(name="check-gate-only", batch="release-gate", conditional=True),
    )
    event = _event(kind="pull_request", labels=(_LABEL,))
    plan = select_ci_plan(
        event=event, targets=targets, authority=_authority(), trust=_TRUST, environ={}
    )
    assert isinstance(plan, CiPlan)
    aggregate = aggregate_ci_results(
        plan=plan,
        current_event=event,
        outcomes=tuple(
            CiOutcome(name=t.name, head_sha="b" * 40, scope=plan.scope, outcome="passed")
            for t in plan.selected
        ),
        targets=targets,
        observer_arm_admitted=lambda _a, _e: True,
    )
    assert isinstance(aggregate, CiAggregate)
    assert aggregate.successful
    assert aggregate.conditional == plan.conditional
    assert [(line.job, line.names) for line in aggregate.conditional] == [
        ("release-gate", ("check-shared", "check-gate-only"))
    ]
