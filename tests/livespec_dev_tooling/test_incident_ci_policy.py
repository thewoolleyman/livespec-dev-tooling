"""Trusted incident CI selection, current-head aggregate, and normal-master controls."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-egy3ri
from __future__ import annotations

from dataclasses import replace
from typing import Any, cast
from unittest.mock import Mock

import pytest

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
from livespec_dev_tooling.incident_transport import CONTEXT_ENV

LABEL = "expedited-incident-response"


def _event(**changes: Any) -> CiEvent:
    return CiEvent(
        **(
            dict(
                kind="pull_request",
                repository="owner/repo",
                base_sha="a" * 40,
                head_sha="b" * 40,
                pr_number=7,
                labels=(LABEL,),
            )
            | changes
        )
    )


def _authority(**changes: Any) -> CiAuthority:
    identity = OperationIdentity(
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        phase="repair",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        operation_id="repair-op",
    )
    context = ExecutionContext(
        mode=ExecutionMode.EXPEDITED_REPAIR, invocation=Invocation.ORDINARY, identity=identity
    )
    return CiAuthority(
        **(
            dict(
                context=context,
                generation=1,
                owner="operator:alice",
                pr_number=7,
                receipt_digest="d" * 64,
                observer_arm_id="arm-1",
            )
            | changes
        )
    )


def _trust(**changes: Any) -> CiTrust:
    return CiTrust(
        **(
            dict(current=lambda _authority: True, observer=lambda _authority, _event: True)
            | changes
        )
    )


def _targets() -> tuple[CiTarget, ...]:
    return (
        CiTarget(name="lint", classification="fast", batch="python", produces=("lint-proof",)),
        CiTarget(
            name="check-per-file-coverage",
            classification="fast",
            batch="python",
            produces=("coverage",),
        ),
        CiTarget(
            name="coverage-consumer", classification="fast", needs=("check-per-file-coverage",)
        ),
        CiTarget(name="artifact-consumer", classification="fast", consumes=("coverage",)),
        CiTarget(name="indirect", classification="fast", needs=("coverage-consumer",)),
        CiTarget(name="check-heading-coverage", classification="fast", batch="metadata"),
        CiTarget(name="pbt", classification="coverage"),
        CiTarget(name="unknown", classification="unclassified"),
        CiTarget(name="format", classification="fast", consumes=("lint-proof",)),
        CiTarget(name="spec-debt", classification="spec"),
    )


def _plan() -> CiPlan:
    result = select_ci_plan(
        event=_event(), targets=_targets(), authority=_authority(), trust=_trust(), environ={}
    )
    assert isinstance(result, CiPlan)
    return result


def _outcomes(plan: CiPlan, **changes: Any) -> tuple[CiOutcome, ...]:
    return tuple(
        CiOutcome(
            **(
                dict(name=t.name, head_sha=plan.event.head_sha, scope=plan.scope, outcome="passed")
                | changes
            )
        )
        for t in plan.selected
    )


def test_mixed_batches_retain_fast_members_and_explicitly_defer_producers_consumers_and_artifacts() -> (
    None
):
    plan = _plan()
    assert [(t.name, t.batch) for t in plan.selected] == [("lint", "python"), ("format", "direct")]
    deferred = {d.name: d.reason for d in plan.deferred}
    assert deferred["check-per-file-coverage"] == "incident-policy:coverage"
    assert deferred["check-heading-coverage"] == "incident-policy:spec"
    assert deferred["pbt"] == "incident-policy:coverage"
    assert deferred["spec-debt"] == "incident-policy:spec"
    assert deferred["unknown"] == "incident-policy:unclassified"
    for name in ("coverage-consumer", "artifact-consumer", "indirect"):
        assert deferred[name] == "incident-policy:deferred-dependency-or-artifact"
    assert all("coverage" not in t.produces + t.consumes for t in plan.selected)
    assert dict(plan.environment)["EXPEDITED_INCIDENT_RESPONSE"] == "1"
    assert "EXPEDITED_INCIDENT_RESPONSE_REVERT" not in dict(plan.environment)


@pytest.mark.parametrize(
    "kind", ["push", "merge_group", "workflow_dispatch", "pull_request_target"]
)
def test_normal_events_keep_the_complete_graph_and_clear_malformed_flags_before_any_reader(
    kind: str,
) -> None:
    current = Mock(side_effect=AssertionError("normal must not read incident authority"))
    observer = Mock(side_effect=AssertionError("normal must not read observer"))
    event = _event(kind=kind)
    environ = {
        "EXPEDITED_INCIDENT_RESPONSE": "malformed",
        "EXPEDITED_INCIDENT_RESPONSE_REVERT": "also malformed",
        CONTEXT_ENV: "{bad",
        "UNRELATED": "kept",
    }
    result = select_ci_plan(
        event=event,
        targets=_targets(),
        authority=None,
        trust=CiTrust(current=current, observer=observer),
        environ=environ,
    )
    assert isinstance(result, CiPlan)
    assert result.mode == ExecutionMode.NORMAL
    assert result.selected == _targets()
    assert result.deferred == ()
    assert dict(result.environment) == {"UNRELATED": "kept"}
    assert current.call_count == observer.call_count == 0
    other = select_ci_plan(
        event=replace(event, labels=()),
        targets=_targets(),
        authority=_authority(),
        trust=_trust(),
        environ={},
    )
    assert isinstance(other, CiPlan)
    assert other.scope == result.scope


def test_label_removal_selects_complete_normal_policy_despite_prior_incident_receipt() -> None:
    result = select_ci_plan(
        event=_event(labels=()),
        targets=_targets(),
        authority=_authority(),
        trust=_trust(),
        environ={},
    )
    assert isinstance(result, CiPlan)
    assert result.mode == ExecutionMode.NORMAL
    assert result.authority is None
    assert result.selected == _targets()


def test_label_alone_cannot_authorize_an_incident() -> None:
    result = select_ci_plan(
        event=_event(), targets=_targets(), authority=None, trust=_trust(), environ={}
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == "incident-ci-identity-mismatch"


@pytest.mark.parametrize(
    "changes",
    [
        {"repository": "other/repo"},
        {"head_sha": "c" * 40},
        {"base_sha": "c" * 40},
        {"pr_number": 8},
        {"pr_number": True},
    ],
)
def test_event_identity_must_match_current_authority(changes: dict[str, Any]) -> None:
    result = select_ci_plan(
        event=_event(**changes),
        targets=_targets(),
        authority=_authority(),
        trust=_trust(),
        environ={},
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == "incident-ci-identity-mismatch"


@pytest.mark.parametrize(
    "changes",
    [
        {"generation": 0},
        {"generation": True},
        {"pr_number": True},
        {"owner": ""},
        {"receipt_digest": ""},
        {"observer_arm_id": ""},
    ],
)
def test_incomplete_current_authority_is_refused(changes: dict[str, Any]) -> None:
    result = select_ci_plan(
        event=_event(),
        targets=_targets(),
        authority=_authority(**changes),
        trust=_trust(),
        environ={},
    )
    assert isinstance(result, IncidentConfigurationRefusal)


def test_normal_or_malformed_context_never_becomes_repair_permission() -> None:
    authority = _authority()
    assert authority.context.identity is not None
    for context in (
        ExecutionContext(
            mode="invalid", invocation=Invocation.ORDINARY, identity=authority.context.identity
        ),
        ExecutionContext(mode=ExecutionMode.NORMAL, invocation=Invocation.ORDINARY, identity=None),
        replace(
            authority.context,
            identity=replace(authority.context.identity, phase="repayment-active"),
        ),
    ):
        result = select_ci_plan(
            event=_event(),
            targets=_targets(),
            authority=replace(authority, context=context),
            trust=_trust(),
            environ={},
        )
        assert isinstance(result, IncidentConfigurationRefusal)


@pytest.mark.parametrize(
    ("trust", "code"),
    [
        (_trust(current=lambda _authority: False), "incident-ci-authority-refused"),
        (_trust(observer=lambda _authority, _event: False), "incident-ci-observer-unarmed"),
        (_trust(current=lambda _authority: cast(Any, 1)), "incident-ci-authority-refused"),
        (
            _trust(observer=lambda _authority, _event: cast(Any, "true")),
            "incident-ci-observer-unarmed",
        ),
    ],
)
def test_both_current_identity_and_independent_observer_admission_are_required(
    trust: CiTrust, code: str
) -> None:
    result = select_ci_plan(
        event=_event(), targets=_targets(), authority=_authority(), trust=trust, environ={}
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == code


@pytest.mark.parametrize(
    "targets",
    [
        (),
        (CiTarget(name="", classification="fast"),),
        (CiTarget(name="x", classification="fast"), CiTarget(name="x", classification="fast")),
    ],
)
def test_invalid_inventory_never_turns_into_a_successful_empty_gate(
    targets: tuple[CiTarget, ...],
) -> None:
    result = select_ci_plan(
        event=_event(), targets=targets, authority=_authority(), trust=_trust(), environ={}
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == "invalid-ci-inventory"


def test_no_fast_work_and_missing_or_ambiguous_artifact_sources_remain_explicit() -> None:
    result = select_ci_plan(
        event=_event(),
        targets=(CiTarget(name="slow", classification="coverage"),),
        authority=_authority(),
        trust=_trust(),
        environ={},
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == "incident-ci-no-retained-checks"
    targets = (
        CiTarget(name="first", classification="fast", produces=("ambiguous",)),
        CiTarget(name="second", classification="fast", produces=("ambiguous",)),
        CiTarget(name="consumer", classification="fast", consumes=("ambiguous",)),
        CiTarget(name="missing", classification="fast", consumes=("absent",)),
    )
    plan = select_ci_plan(
        event=_event(), targets=targets, authority=_authority(), trust=_trust(), environ={}
    )
    assert isinstance(plan, CiPlan)
    assert [d.name for d in plan.deferred] == ["consumer", "missing"]


def test_aggregate_preserves_real_pass_failure_missing_and_deferred_work() -> None:
    plan = _plan()
    passed = aggregate_ci_results(
        targets=_targets(),
        plan=plan,
        current_event=_event(),
        outcomes=_outcomes(plan),
        observer_arm_admitted=_trust().observer,
    )
    assert isinstance(passed, CiAggregate)
    assert passed.successful
    assert passed.context_name == "ci-green"
    assert passed.passed == ("lint", "format")
    assert passed.deferred == plan.deferred
    missing = aggregate_ci_results(
        targets=_targets(),
        plan=plan,
        current_event=_event(),
        outcomes=(),
        observer_arm_admitted=_trust().observer,
    )
    assert isinstance(missing, CiAggregate)
    assert not missing.successful
    assert missing.missing == ("lint", "format")
    partial = aggregate_ci_results(
        targets=_targets(),
        plan=plan,
        current_event=_event(),
        outcomes=_outcomes(plan)[:1],
        observer_arm_admitted=_trust().observer,
    )
    assert isinstance(partial, CiAggregate)
    assert partial.passed == ("lint",)
    assert partial.missing == ("format",)
    assert not partial.successful
    for outcome in ("failed", "skipped", "cancelled", "deferred", "unavailable"):
        failed = aggregate_ci_results(
            targets=_targets(),
            plan=plan,
            current_event=_event(),
            outcomes=_outcomes(plan, outcome=outcome),
            observer_arm_admitted=_trust().observer,
        )
        assert isinstance(failed, CiAggregate)
        assert not failed.successful
        assert failed.failed == ("lint", "format")


@pytest.mark.parametrize(
    "changes",
    [
        {"head_sha": "c" * 40},
        {"base_sha": "c" * 40},
        {"repository": "other/repo"},
        {"pr_number": 8},
        {"labels": ()},
    ],
)
def test_new_head_or_mode_invalidates_all_old_verdicts(changes: dict[str, Any]) -> None:
    plan = _plan()
    result = aggregate_ci_results(
        targets=_targets(),
        plan=plan,
        current_event=_event(**changes),
        outcomes=_outcomes(plan),
        observer_arm_admitted=_trust().observer,
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == "incident-ci-stale-event"


def test_unrelated_labels_do_not_change_head_mode_evidence() -> None:
    plan = _plan()
    result = aggregate_ci_results(
        targets=_targets(),
        plan=plan,
        current_event=_event(labels=(LABEL, "unrelated")),
        outcomes=_outcomes(plan),
        observer_arm_admitted=_trust().observer,
    )
    assert isinstance(result, CiAggregate)
    assert result.successful


def test_aggregate_rechecks_independent_arm_without_inventing_new_tenant_authority() -> None:
    plan = _plan()
    result = aggregate_ci_results(
        targets=_targets(),
        plan=plan,
        current_event=_event(),
        outcomes=_outcomes(plan),
        observer_arm_admitted=_trust(observer=lambda _a, _e: False).observer,
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == "incident-ci-observer-refused"


@pytest.mark.parametrize("changes", [{"name": "foreign"}, {"head_sha": "c" * 40}, {"scope": "old"}])
def test_foreign_or_stale_member_reports_cannot_satisfy_the_aggregate(
    changes: dict[str, Any],
) -> None:
    plan = _plan()
    result = aggregate_ci_results(
        targets=_targets(),
        plan=plan,
        current_event=_event(),
        outcomes=_outcomes(plan, **changes),
        observer_arm_admitted=_trust().observer,
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == "incident-ci-invalid-outcomes"


def test_duplicate_member_reports_are_refused_and_normal_master_aggregate_keeps_every_member() -> (
    None
):
    plan = _plan()
    reports = _outcomes(plan)
    result = aggregate_ci_results(
        targets=_targets(),
        plan=plan,
        current_event=_event(),
        outcomes=(*reports, reports[0]),
        observer_arm_admitted=_trust().observer,
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    normal = select_ci_plan(
        event=_event(kind="push"), targets=_targets(), authority=None, trust=_trust(), environ={}
    )
    assert isinstance(normal, CiPlan)
    complete = aggregate_ci_results(
        targets=_targets(),
        plan=normal,
        current_event=normal.event,
        outcomes=_outcomes(normal),
        observer_arm_admitted=Mock(side_effect=AssertionError("normal reader")),
    )
    assert isinstance(complete, CiAggregate)
    assert complete.successful
    assert len(complete.passed) == len(_targets())


@pytest.mark.parametrize(
    "changes",
    [{"mode": ExecutionMode.NORMAL}, {"scope": "forged"}, {"deferred": ()}, {"authority": None}],
)
def test_a_constructed_or_modified_plan_is_not_itself_merge_authority(
    changes: dict[str, Any],
) -> None:
    plan = _plan()
    result = aggregate_ci_results(
        plan=replace(plan, **changes),
        current_event=_event(),
        outcomes=_outcomes(plan),
        targets=_targets(),
        observer_arm_admitted=_trust().observer,
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == "incident-ci-invalid-plan"


def test_aggregate_uses_independent_inventory_rather_than_a_candidates_subset() -> None:
    plan = _plan()
    result = aggregate_ci_results(
        plan=plan,
        current_event=_event(),
        outcomes=_outcomes(plan),
        targets=tuple(t for t in _targets() if t.name != "pbt"),
        observer_arm_admitted=_trust().observer,
    )
    assert isinstance(result, IncidentConfigurationRefusal)
    assert result.code == "incident-ci-invalid-plan"
