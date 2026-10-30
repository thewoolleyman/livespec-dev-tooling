"""Tests for `master_health_step` — the recorded-state-to-chosen-step adapter.

The carrier across the seam `master_health_state`'s docstring names: the
gathering lives in the reusable workflow, the decision is pure, and this module
is what hands one to the other. It makes NO judgement of its own, so these
tests are about two things only — that a well-formed recording reaches
`reconcile_step` intact, and that a malformed one FAILS CLOSED rather than
producing a step.

THE MALFORMED-REVERT CASE IS THE LOAD-BEARING ONE. A revert pull request that
fails to parse must not read as "no revert in flight": that is precisely the
state in which the decision table opens a revert, so a lenient parse here would
open a SECOND revert for an episode that already has one.

THE DRIFT ASSERTIONS ARE DRIVEN OFF THE DATACLASS FIELDS, NOT OFF A LITERAL
LIST, and that choice is paid for. An earlier cut of this adapter was authored
against the decision core's shapes of the day and went stale under it: child
C1's calibration slice (`livespec-dev-tooling-zdqnr2`) added
`ReconcileConfig.gating_workflow` and `.unrelated_lookback_commits`, added
`MasterCommit.ci_workflow` and `.subject`, and removed
`ReconcileState.unrelated_failure_signatures` — and the adapter that had been
green against the old shapes failed with ten `TypeError`s instead of being
caught by an assertion that noticed. So every field of `ReconcileConfig`, every
non-nullable field of `MasterCommit` and every field of `ReconcileStep` is
enumerated from `dataclasses.fields` here: a field added to the core without
being threaded through this carrier fails HERE, at the seam, rather than at a
red master nobody can heal.
"""

from __future__ import annotations

import json
from dataclasses import fields
from typing import TYPE_CHECKING

from livespec_dev_tooling.cross_repo.master_health_commit_shape import (
    HOLD_REBUMP_LABEL_PREFIX,
)
from livespec_dev_tooling.cross_repo.master_health_reconcile import (
    STEP_CLOSE_REVERT,
    STEP_NEEDS_ATTENTION,
    STEP_NONE,
    STEP_OPEN_REVERT,
    STEP_RELEASE_REVERT,
    ReconcileStep,
)
from livespec_dev_tooling.cross_repo.master_health_state import (
    MasterCommit,
    ReconcileConfig,
)
from livespec_dev_tooling.cross_repo.master_health_step import (
    NEEDS_ATTENTION_TITLE_PREFIX,
    main,
    needs_attention_title,
    open_episode_keys,
    step_payload,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = []


_MARKERS = ["No runner matching the labels"]

# The gating workflow every recording below is projected onto, and a second
# workflow name that runs on the same branch without gating a single merge.
_GATING = "ci.yml"
_NON_GATING = "nightly-drill.yml"

# The fields that are legitimately `null` in a recording: a direct push has no
# pull request, and a commit that is not red has no failure signature. Every
# OTHER field of `MasterCommit` is required, and the table-driven fail-closed
# assertion below enumerates them from the dataclass rather than restating them.
_NULLABLE_COMMIT_FIELDS = frozenset({"pull_request", "failure_signature", "ci_completed_at"})


# The committed-configuration fields whose absence does NOT red the job: the hard cap,
# the stall durations and the maintainer login fail closed to revert-by-default instead
# (`test_master_health_fix_forward` proves that), so a missing one is not a malformed
# recording.
_FAIL_CLOSED_CONFIG_FIELDS = frozenset(
    {
        "maintainer_login",
        "hard_cap_minutes",
        "stall_claim_to_fix_pr_minutes",
        "stall_ci_in_flight_minutes",
        "stall_fix_to_merge_minutes",
        "stall_merged_to_green_minutes",
    }
)


def _commit(
    *,
    sha: str,
    parent: str,
    pull_request: int | None = None,
    conclusion: str = "success",
    signature: str | None = None,
    workflow: str = _GATING,
    subject: str = "feat(widget): an ordinary merge (#7)",
) -> dict[str, object]:
    return {
        "sha": sha,
        "parent_sha": parent,
        "pull_request": pull_request,
        "ci_workflow": workflow,
        "ci_conclusion": conclusion,
        "failure_signature": signature,
        "subject": subject,
    }


def _red_window(
    *,
    subject: str = "feat(widget): an ordinary merge (#7)",
    workflow: str = _GATING,
) -> list[dict[str, object]]:
    """A window whose head is red and whose parent is green — one culprit, proven."""
    return [
        _commit(sha="c1", parent="c0"),
        _commit(
            sha="c2",
            parent="c1",
            pull_request=7,
            conclusion="failure",
            signature="check-lint",
            workflow=workflow,
            subject=subject,
        ),
    ]


def _recording(**overrides: object) -> dict[str, object]:
    """A well-formed recording of a GREEN branch, with per-test overrides."""
    record: dict[str, object] = {
        "target_branch": "master",
        "infra_outage_markers": _MARKERS,
        "gating_workflow": _GATING,
        "unrelated_lookback_commits": 20,
        "head_sha": "c2",
        "rerun_outcome": "not-attempted",
        "commits": [
            _commit(sha="c1", parent="c0"),
            _commit(sha="c2", parent="c1", pull_request=7),
        ],
        "revert_pull_request": None,
        "needs_attention_issue_titles": [],
    }
    record.update(overrides)
    return record


def _run(*, tmp_path: Path, record: object) -> tuple[int, dict[str, object] | None]:
    """Invoke the CLI over `record`; return its exit code and the step it wrote."""
    state_path = tmp_path / "state.json"
    step_path = tmp_path / "step.json"
    _ = state_path.write_text(json.dumps(record), encoding="utf-8")
    code = main(argv=["--state", str(state_path), "--step-out", str(step_path)])
    if not step_path.is_file():
        return (code, None)
    parsed: object = json.loads(step_path.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    return (code, parsed)


def test_a_green_recording_yields_the_do_nothing_step(*, tmp_path: Path) -> None:
    """The pass-through case: the adapter adds nothing to what the core decided."""
    code, step = _run(tmp_path=tmp_path, record=_recording())

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_NONE
    assert step["target_branch"] == "master"
    assert step["reason"]


def test_the_step_payload_carries_every_field_the_chosen_step_holds() -> None:
    """The carrier may not DROP a field, and this is the assertion that says so.

    `step_payload` is the whole of what the performing workflow step can see, so
    a field the decision core adds and this payload omits is an argument the
    step silently performs without — which is how a held auto-merge or a
    hold-rebump label goes missing with nothing failing. Enumerated from
    `ReconcileStep`'s own fields so a later field inherits the assertion.
    """
    payload = step_payload(
        step=ReconcileStep(kind=STEP_NONE, target_branch="master", reason="nothing owed")
    )

    assert set(payload) == {field.name for field in fields(ReconcileStep)} | {
        "needs_attention_title"
    }


def test_a_regression_recording_yields_the_open_revert_step_with_the_hold(
    *, tmp_path: Path
) -> None:
    """The step the workflow performs carries the culprit AND the held auto-merge.

    `auto_merge_held` travels as DATA rather than as an implicit convention for
    the reason `ReconcileStep` records: the caller that opens the pull request
    must not be able to arm auto-merge by omission.
    """
    code, step = _run(
        tmp_path=tmp_path,
        record=_recording(head_sha="c2", rerun_outcome="still-red", commits=_red_window()),
    )

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_OPEN_REVERT
    assert step["culprit_pull_request"] == 7
    assert step["culprit_sha"] == "c2"
    assert step["auto_merge_held"] is True
    assert step["hold_rebump_label"] is None


def test_the_recorded_subject_reaches_the_rules_that_read_it(*, tmp_path: Path) -> None:
    """`subject` is carried RAW, and two live rules read nothing else.

    A pin-bump culprit's revert must carry the hold-rebump label, or the bump
    shim re-bumps the pin the reconciler just reverted; and a release-please
    release commit may not be reverted at all. Both answers are read off the
    subject alone, so a recording whose subjects were dropped would reach the
    plain-revert branch for both — silently, because an ordinary merge is
    exactly what an unrecorded subject looks like.
    """
    bump = _recording(
        rerun_outcome="still-red",
        commits=_red_window(subject="chore(deps): bump livespec-dev-tooling pin to v1.101.2"),
    )
    code, step = _run(tmp_path=tmp_path, record=bump)

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_OPEN_REVERT
    assert step["hold_rebump_label"] == f"{HOLD_REBUMP_LABEL_PREFIX}:v1.101.2"

    release = _recording(
        rerun_outcome="still-red", commits=_red_window(subject="chore(master): release 1.101.2")
    )
    code, step = _run(tmp_path=tmp_path, record=release)

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_NEEDS_ATTENTION
    assert step["culprit_pull_request"] is None


def test_a_non_gating_workflow_s_failure_is_not_a_red_branch(*, tmp_path: Path) -> None:
    """`ci_workflow` travels, so the projection can drop what does not gate.

    One workflow decides whether the branch is red — the one branch protection
    reads. A scheduled drill can fail for days without blocking a merge, and a
    reconciler that reverted for it would revert a commit whose own gating CI
    never failed. The projection lives in the core; what this asserts is that
    the record reaches it still carrying the workflow it came from.
    """
    code, step = _run(
        tmp_path=tmp_path,
        record=_recording(rerun_outcome="still-red", commits=_red_window(workflow=_NON_GATING)),
    )

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_NONE


def test_the_lookback_bound_travels_so_a_recurring_failure_reads_as_infra(
    *, tmp_path: Path
) -> None:
    """`unrelated_lookback_commits` bounds the already-failing read, and is required.

    A check that was failing BELOW this episode is not this merge's fault, and
    the bound is what stops that exoneration from being unlimited. The bound is
    committed configuration, so the adapter must carry it: at zero the same
    window is a regression, and at a wider bound it is infra.
    """
    window = [
        _commit(sha="c0", parent="cx", conclusion="failure", signature="check-lint"),
        _commit(sha="c1", parent="c0"),
        _commit(
            sha="c2",
            parent="c1",
            pull_request=7,
            conclusion="failure",
            signature="check-lint",
        ),
    ]
    code, step = _run(
        tmp_path=tmp_path,
        record=_recording(rerun_outcome="still-red", commits=window, unrelated_lookback_commits=5),
    )

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_NEEDS_ATTENTION

    code, step = _run(
        tmp_path=tmp_path,
        record=_recording(rerun_outcome="still-red", commits=window, unrelated_lookback_commits=0),
    )

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_OPEN_REVERT


def test_a_green_revert_with_no_claim_yields_the_release_step(*, tmp_path: Path) -> None:
    """A recorded revert parses whole — number, verdict, hold and claim."""
    code, step = _run(
        tmp_path=tmp_path,
        record=_recording(
            rerun_outcome="still-red",
            commits=_red_window(),
            revert_pull_request={
                "number": 9,
                "reverts_pull_request": 7,
                "ci_conclusion": "success",
                "auto_merge_armed": False,
                "culprit_opened_by": None,
                "claims": [],
                "fix_pull_requests": [],
            },
        ),
    )

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_RELEASE_REVERT
    assert step["revert_pull_request"] == 9


def test_a_revert_a_later_green_commit_superseded_yields_the_close_step(*, tmp_path: Path) -> None:
    """The commonest ending the plan measured, and the step that carries it.

    25% of measured episodes ended with a later unrelated commit coming back
    green and no fix landing at all, which leaves a revert of someone's work
    parked on a healthy branch. `STEP_CLOSE_REVERT` is what the core answers
    there, so the adapter must be able to carry it: a step kind the payload
    could not express would reach the workflow as something it refuses.
    """
    code, step = _run(
        tmp_path=tmp_path,
        record=_recording(
            revert_pull_request={
                "number": 9,
                "reverts_pull_request": 7,
                "ci_conclusion": "success",
                "auto_merge_armed": False,
                "culprit_opened_by": None,
                "claims": [],
                "fix_pull_requests": [],
            }
        ),
    )

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_CLOSE_REVERT
    assert step["revert_pull_request"] == 9


def test_the_needs_attention_step_carries_the_issue_title_this_module_owns(
    *, tmp_path: Path
) -> None:
    """One issue per EPISODE, and the title convention lives in ONE place.

    The workflow hands over the titles it found and reads the title to write
    back off this same step, so "does this episode already have an issue?" and
    "what is a new one called?" are answered by one implementation. Splitting
    that across a shell script and this module is how a second issue per
    episode gets opened.
    """
    code, step = _run(
        tmp_path=tmp_path, record=_recording(rerun_outcome="passed", commits=_red_window())
    )

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_NEEDS_ATTENTION
    assert step["needs_attention_title"] == needs_attention_title(episode_key="master@c2")


def test_recorded_open_episodes_are_read_off_the_issue_titles(*, tmp_path: Path) -> None:
    """The titles the workflow found become the episode keys the core consumes."""
    assert open_episode_keys(
        titles=(f"{NEEDS_ATTENTION_TITLE_PREFIX}master@c2", "an unrelated issue")
    ) == ("master@c2",)

    code, step = _run(
        tmp_path=tmp_path,
        record=_recording(
            needs_attention_issue_titles=[f"{NEEDS_ATTENTION_TITLE_PREFIX}master@c2"]
        ),
    )

    assert code == 0
    assert step is not None


def test_an_unreadable_recording_writes_no_step_and_fails_closed(*, tmp_path: Path) -> None:
    """Fail-closed on a state this run could not read: no step is better than a guess."""
    step_path = tmp_path / "step.json"

    code = main(
        argv=["--state", str(tmp_path / "absent.json"), "--step-out", str(step_path)],
    )

    assert code == 1
    assert not step_path.is_file()


def test_a_recording_that_is_not_an_object_fails_closed(*, tmp_path: Path) -> None:
    """A JSON array, or any non-object payload, is not a recorded state."""
    code, step = _run(tmp_path=tmp_path, record=["not", "a", "state"])

    assert code == 1
    assert step is None


def test_every_field_of_the_committed_configuration_is_required(*, tmp_path: Path) -> None:
    """Each `ReconcileConfig` field, enumerated from the dataclass, fails closed.

    This is the drift guard the module docstring records: a field the core adds
    to its configuration and this adapter never learned to read would otherwise
    reach the constructor as a missing argument at RUN time — a `TypeError` on a
    live red master — instead of as a failing assertion here.
    """
    for field in fields(ReconcileConfig):
        if field.name in _FAIL_CLOSED_CONFIG_FIELDS:
            continue
        record = _recording()
        del record[field.name]

        code, step = _run(tmp_path=tmp_path, record=record)

        assert code == 1, f"a recording with no {field.name} did not fail closed"
        assert step is None, f"a recording with no {field.name} wrote a step"


def test_every_required_field_of_a_recorded_commit_is_required(*, tmp_path: Path) -> None:
    """Each non-nullable `MasterCommit` field, enumerated, truncates the window.

    A commit that will not parse is a hole in the parent chain the culprit rule
    walks, so the whole window is refused rather than silently shortened. The
    two nullable fields are excluded by name and by reason: a direct push has no
    pull request, and a commit that is not red has no failure signature.
    """
    for field in fields(MasterCommit):
        if field.name in _NULLABLE_COMMIT_FIELDS:
            continue
        commit = _commit(sha="c1", parent="c0")
        del commit[field.name]

        code, step = _run(tmp_path=tmp_path, record=_recording(commits=[commit]))

        assert code == 1, f"a commit with no {field.name} did not fail closed"
        assert step is None, f"a commit with no {field.name} wrote a step"


def test_a_recording_missing_a_required_state_field_fails_closed(*, tmp_path: Path) -> None:
    """Every field the decision reads is required; a missing one is not a default."""
    record = _recording()
    del record["head_sha"]

    code, step = _run(tmp_path=tmp_path, record=record)

    assert code == 1
    assert step is None


def test_a_recording_with_a_malformed_revert_fails_closed(*, tmp_path: Path) -> None:
    """THE LOAD-BEARING FAILURE: a revert that will not parse is NOT "no revert".

    Reading it as absent would send the decision table down the branch that
    OPENS a revert, for an episode that already has one in flight. There is no
    lenient reading of this field that is safe.
    """
    code, step = _run(
        tmp_path=tmp_path,
        record=_recording(revert_pull_request={"number": 9, "ci_conclusion": "success"}),
    )

    assert code == 1
    assert step is None


def test_every_malformed_recording_shape_fails_closed(*, tmp_path: Path) -> None:
    """One table over every shape the parse rejects, so none is left unexercised.

    Each entry is a field holding something the decision cannot read: a marker
    list with a non-string in it, a lookback that is not a number, a lookback
    recorded as a bool (an `int` subclass in Python, so the one shape a naive
    check admits), a commit window that is not a list, a commit that is not an
    object, a revert that is not an object, and an issue-title list that is not
    a list. Every one of them must write no step — a partial parse is the shape
    that reaches a confident wrong answer.
    """
    shapes: tuple[dict[str, object], ...] = (
        {"infra_outage_markers": "not a list"},
        {"infra_outage_markers": ["a marker", 7]},
        {"unrelated_lookback_commits": "not a number"},
        {"unrelated_lookback_commits": True},
        {"commits": "not a list"},
        {"commits": ["not an object"]},
        {"revert_pull_request": "not an object"},
        {"needs_attention_issue_titles": "not a list"},
    )
    for shape in shapes:
        code, step = _run(tmp_path=tmp_path, record=_recording(**shape))

        assert code == 1, f"{shape} did not fail closed"
        assert step is None, f"{shape} wrote a step"


def test_a_recording_that_is_not_json_at_all_fails_closed(*, tmp_path: Path) -> None:
    """Unparseable bytes are read as unreadable, never as an empty recording."""
    state_path = tmp_path / "state.json"
    step_path = tmp_path / "step.json"
    _ = state_path.write_text("{ this is not json", encoding="utf-8")

    code = main(argv=["--state", str(state_path), "--step-out", str(step_path)])

    assert code == 1
    assert not step_path.is_file()
