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
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from livespec_dev_tooling.cross_repo.master_health_reconcile import (
    STEP_NEEDS_ATTENTION,
    STEP_NONE,
    STEP_OPEN_REVERT,
    STEP_RELEASE_REVERT,
)
from livespec_dev_tooling.cross_repo.master_health_step import (
    NEEDS_ATTENTION_TITLE_PREFIX,
    main,
    needs_attention_title,
    open_episode_keys,
)

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = []


_MARKERS = ["No runner matching the labels"]


def _commit(
    *,
    sha: str,
    parent: str,
    pull_request: int | None = None,
    conclusion: str = "success",
    signature: str | None = None,
) -> dict[str, object]:
    return {
        "sha": sha,
        "parent_sha": parent,
        "pull_request": pull_request,
        "ci_conclusion": conclusion,
        "failure_signature": signature,
    }


def _recording(**overrides: object) -> dict[str, object]:
    """A well-formed recording of a GREEN branch, with per-test overrides."""
    record: dict[str, object] = {
        "target_branch": "master",
        "infra_outage_markers": _MARKERS,
        "head_sha": "c2",
        "rerun_outcome": "not-attempted",
        "commits": [
            _commit(sha="c1", parent="c0"),
            _commit(sha="c2", parent="c1", pull_request=7),
        ],
        "revert_pull_request": None,
        "needs_attention_issue_titles": [],
        "unrelated_failure_signatures": [],
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
        record=_recording(
            head_sha="c2",
            rerun_outcome="still-red",
            commits=[
                _commit(sha="c1", parent="c0"),
                _commit(
                    sha="c2",
                    parent="c1",
                    pull_request=7,
                    conclusion="failure",
                    signature="check-lint",
                ),
            ],
        ),
    )

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_OPEN_REVERT
    assert step["culprit_pull_request"] == 7
    assert step["culprit_sha"] == "c2"
    assert step["auto_merge_held"] is True


def test_a_green_revert_with_no_claim_yields_the_release_step(*, tmp_path: Path) -> None:
    """A recorded revert parses whole — number, verdict, hold and claim."""
    code, step = _run(
        tmp_path=tmp_path,
        record=_recording(
            rerun_outcome="still-red",
            commits=[
                _commit(sha="c1", parent="c0"),
                _commit(
                    sha="c2",
                    parent="c1",
                    pull_request=7,
                    conclusion="failure",
                    signature="check-lint",
                ),
            ],
            revert_pull_request={
                "number": 9,
                "reverts_pull_request": 7,
                "ci_conclusion": "success",
                "auto_merge_armed": False,
                "fix_forward_claim": None,
            },
        ),
    )

    assert code == 0
    assert step is not None
    assert step["kind"] == STEP_RELEASE_REVERT
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
        tmp_path=tmp_path,
        record=_recording(
            rerun_outcome="passed",
            commits=[
                _commit(sha="c1", parent="c0"),
                _commit(
                    sha="c2",
                    parent="c1",
                    pull_request=7,
                    conclusion="failure",
                    signature="check-lint",
                ),
            ],
        ),
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


def test_a_recording_missing_a_required_field_fails_closed(*, tmp_path: Path) -> None:
    """Every field the decision reads is required; a missing one is not a default."""
    record = _recording()
    del record["head_sha"]

    code, step = _run(tmp_path=tmp_path, record=record)

    assert code == 1
    assert step is None


def test_a_recording_with_a_malformed_commit_fails_closed(*, tmp_path: Path) -> None:
    """A commit that will not parse truncates the window the culprit rule walks."""
    code, step = _run(tmp_path=tmp_path, record=_recording(commits=[{"sha": "c1"}]))

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


def test_a_recording_whose_config_is_malformed_fails_closed(*, tmp_path: Path) -> None:
    """The committed-configuration half is validated as strictly as the state half."""
    code, step = _run(tmp_path=tmp_path, record=_recording(infra_outage_markers="not a list"))

    assert code == 1
    assert step is None


def test_every_malformed_recording_shape_fails_closed(*, tmp_path: Path) -> None:
    """One table over every shape the parse rejects, so none is left unexercised.

    Each entry is a field holding something the decision cannot read: a marker
    list with a non-string in it, a commit window that is not a list, a commit
    that is not an object, a revert that is not an object, and an issue-title
    list that is not a list. Every one of them must write no step — a partial
    parse is the shape that reaches a confident wrong answer.
    """
    shapes: tuple[dict[str, object], ...] = (
        {"infra_outage_markers": ["a marker", 7]},
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
