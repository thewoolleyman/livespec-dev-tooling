"""Incident CI inventory members are keyed by job and check slug (livespec-dev-tooling-yzr6ad).

livespec's workflow at a91c015d declares two checks both in a batch job and in
`release-gate-pre-tag`, a job whose `if:` names the triggering event and ref.
The released inventory keeps one member per declaring job; the entrance runs a
slug at most once, attributes it to every declaring job, and lists the members
of an event-conditioned job on a conditional-job line instead of running or
dropping them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling import incident_ci_inventory as module
from livespec_dev_tooling.incident_ci_policy import (
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
    Invocation,
    OperationIdentity,
)

_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE = _ROOT / "tests/fixtures/incident_ci_inventory_livespec_a91c015d"
_LABEL = "expedited-incident-response"
_NOT_RUN = "job not run on this event"


def _decoded(*, text: str) -> tuple[tuple[CiTarget, ...] | None, str | None]:
    try:
        return module.decode_inventory(text=text), None
    except ValueError as refused:
        return None, str(refused)


def _attribution(*, value: object) -> dict[str, tuple[str, ...]]:
    return dict(cast("tuple[tuple[str, tuple[str, ...]], ...]", getattr(value, "attribution", ())))


def _rows(*rows: dict[str, Any]) -> str:
    base = dict(classification="fast", needs=[], produces=[], consumes=[])
    return json.dumps(dict(schema=1, targets=[base | row for row in rows]))


def _event() -> CiEvent:
    return CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
        labels=(_LABEL,),
    )


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


def _plan(*, targets: tuple[CiTarget, ...]) -> object:
    return select_ci_plan(
        event=_event(),
        targets=targets,
        authority=_authority(),
        trust=CiTrust(current=lambda _a: True, observer=lambda _a, _e: True),
        environ={},
    )


def test_livespecs_release_gate_duplicate_renders_and_decodes_one_member_per_job():
    source = json.loads((_FIXTURE / "source.json").read_text())
    rendered = module.render_inventory(
        workflow=(_FIXTURE / "ci.yml").read_text(),
        inventory=(_FIXTURE / "check-targets.txt").read_text(),
        source=module.InventorySource(repository=source["repository"], commit=source["commit"]),
    )
    targets, refused = _decoded(text=rendered)
    assert refused is None, f"livespec's a91c015d inventory must decode, refused: {refused}"
    assert targets is not None
    jobs_by_slug: dict[str, set[str]] = {}
    for target in targets:
        jobs_by_slug.setdefault(target.name, set()).add(target.batch)
    assert jobs_by_slug["check-no-lloc-soft-warnings"] == {
        "check-python-batch",
        "release-gate-pre-tag",
    } or jobs_by_slug["check-no-lloc-soft-warnings"] == {
        "check-metadata-batch",
        "release-gate-pre-tag",
    }
    assert "release-gate-pre-tag" in jobs_by_slug["check-no-todo-registry"]
    assert len(jobs_by_slug["check-no-todo-registry"]) == 2
    gate = {t.name for t in targets if t.batch == "release-gate-pre-tag"}
    assert gate == {"check-mutation", "check-no-lloc-soft-warnings", "check-no-todo-registry"}
    assert all(
        json.loads(rendered)["targets"][i].get("conditional") is True
        for i, row in enumerate(json.loads(rendered)["targets"])
        if row["batch"] == "release-gate-pre-tag"
    ), "release-gate-pre-tag's if: names the event, so its members are conditional"


def test_a_slug_declared_in_two_jobs_runs_once_and_is_attributed_to_both():
    targets, refused = _decoded(
        text=_rows(
            dict(name="check-shared", batch="batch-a"),
            dict(name="check-shared", batch="batch-b"),
            dict(name="check-only-a", batch="batch-a"),
        )
    )
    assert refused is None, f"a slug in two jobs must decode, refused: {refused}"
    assert targets is not None
    plan = _plan(targets=targets)
    assert isinstance(plan, CiPlan), f"a duplicate slug must plan, got {plan!r}"
    assert [t.name for t in plan.selected].count("check-shared") == 1
    attribution = _attribution(value=plan)
    assert attribution.get("check-shared") == ("batch-a", "batch-b")
    aggregate = aggregate_ci_results(
        plan=plan,
        current_event=_event(),
        outcomes=tuple(
            CiOutcome(name=t.name, head_sha="b" * 40, scope=plan.scope, outcome="passed")
            for t in plan.selected
        ),
        targets=targets,
        observer_arm_admitted=lambda _a, _e: True,
    )
    assert _attribution(value=aggregate).get("check-shared") == (
        "batch-a",
        "batch-b",
    ), "the receipt attributes the slug's outcome to every declaring job"


def test_members_of_an_event_conditioned_job_are_listed_not_run_and_never_dropped():
    targets, refused = _decoded(
        text=_rows(
            dict(name="check-shared", batch="batch-a"),
            dict(name="check-shared", batch="release-gate", conditional=True),
            dict(name="check-gate-only", batch="release-gate", conditional=True),
        )
    )
    assert refused is None, f"a conditional member must decode, refused: {refused}"
    assert targets is not None
    plan = _plan(targets=targets)
    assert isinstance(plan, CiPlan), f"a conditional member must plan, got {plan!r}"
    assert [t.name for t in plan.selected] == ["check-shared"]
    assert "check-gate-only" not in {d.name for d in plan.deferred}
    conditional = getattr(plan, "conditional", ())
    assert [(line.job, line.names, line.reason.startswith(_NOT_RUN)) for line in conditional] == [
        ("release-gate", ("check-shared", "check-gate-only"), True)
    ]
    assert _attribution(value=plan).get("check-shared") == (
        "batch-a",
        "release-gate",
    )


def test_a_slug_whose_declaring_jobs_disagree_on_its_policy_is_refused():
    targets, refused = _decoded(
        text=_rows(
            dict(name="check-shared", batch="batch-a"),
            dict(name="check-shared", batch="batch-b", classification="slow"),
        )
    )
    assert refused is None, f"rows decode; the plan judges consistency, refused: {refused}"
    assert targets is not None
    plan = _plan(targets=targets)
    assert not isinstance(plan, CiPlan), "inconsistent duplicate members must refuse, fail closed"


def test_a_job_and_slug_pair_may_appear_only_once():
    _, refused = _decoded(
        text=_rows(
            dict(name="check-shared", batch="batch-a"),
            dict(name="check-shared", batch="batch-a"),
        )
    )
    assert refused == "duplicate or missing released incident CI dependency"


def test_a_conditional_flag_other_than_true_is_refused():
    _, refused = _decoded(text=_rows(dict(name="check-x", batch="batch-a", conditional=False)))
    assert refused == "invalid released incident CI target"


def test_this_repositorys_packaged_inventory_carries_no_conditional_member():
    packaged = json.loads(
        (_ROOT / "livespec_dev_tooling/data/incident-ci-inventory.json").read_text()
    )
    assert all("conditional" not in row for row in packaged["targets"])
    workflow = (_ROOT / ".github/workflows/ci.yml").read_text()
    rendered = module.render_inventory(
        workflow=workflow, inventory=(_ROOT / "check-targets.txt").read_text()
    )
    assert rendered == (_ROOT / "livespec_dev_tooling/data/incident-ci-inventory.json").read_text()
