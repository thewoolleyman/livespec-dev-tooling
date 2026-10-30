"""Tests for the refusals that stop the reconciler opening an unsafe revert.

Per `SPECIFICATION/contracts.md` section "Master-health reconciler" (work-item
`livespec-dev-tooling-joqff6`): the reconciler MUST NOT create a revert that
would overwrite a later `master` commit's change to a culprit path, MUST NOT
revert a revert it created, and MUST revert a given culprit at most once per
episode. Each refusal raises needs-attention instead, and the obstructing
commit is named so a human can act on it.

Every case is replayed through the recording seam, `master_health_step.main`,
so the assertion is on the step the performing workflow would read.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from livespec_dev_tooling.cross_repo.master_health_step import main

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = []


_CULPRIT_SHA = "deadbeefcafe0123456789abcdef0123456789ab"
_ORDINARY = "feat(widget): an ordinary merge (#7)"


def _commit(
    *,
    sha: str,
    parent: str,
    conclusion: str,
    pull_request: int | None = None,
    subject: str = _ORDINARY,
    paths: list[str] | None = None,
) -> dict[str, object]:
    return {
        "sha": sha,
        "parent_sha": parent,
        "pull_request": pull_request,
        "ci_workflow": "ci.yml",
        "ci_conclusion": conclusion,
        "failure_signature": "check-lint" if conclusion == "failure" else None,
        "subject": subject,
        "changed_paths": paths,
    }


def _step(*, tmp_path: Path, commits: list[dict[str, object]]) -> dict[str, object]:
    """Replay a window whose head is the last commit and return the chosen step."""
    record: dict[str, object] = {
        "target_branch": "master",
        "infra_outage_markers": [],
        "gating_workflow": "ci.yml",
        "unrelated_lookback_commits": 20,
        "head_sha": commits[-1]["sha"],
        "rerun_outcome": "still-red",
        "commits": commits,
        "revert_pull_request": None,
        "needs_attention_issue_titles": [],
    }
    state_path = tmp_path / "state.json"
    step_path = tmp_path / "step.json"
    _ = state_path.write_text(json.dumps(record), encoding="utf-8")
    assert main(argv=["--state", str(state_path), "--step-out", str(step_path)]) == 0
    step = json.loads(step_path.read_text(encoding="utf-8"))
    assert isinstance(step, dict)
    return step


def _green() -> dict[str, object]:
    return _commit(sha="c1", parent="c0", conclusion="success")


def _culprit(*, paths: list[str] | None, subject: str = _ORDINARY) -> dict[str, object]:
    return _commit(
        sha=_CULPRIT_SHA,
        parent="c1",
        conclusion="failure",
        pull_request=7,
        paths=paths,
        subject=subject,
    )


def _later(
    *, paths: list[str] | None, subject: str = "fix(widget): a later merge (#8)"
) -> dict[str, object]:
    return _commit(
        sha="c3",
        parent=_CULPRIT_SHA,
        conclusion="failure",
        pull_request=8,
        paths=paths,
        subject=subject,
    )


def test_a_later_commit_touching_a_culprit_path_blocks_the_revert_and_is_named(
    *, tmp_path: Path
) -> None:
    step = _step(
        tmp_path=tmp_path,
        commits=[_green(), _culprit(paths=["a.py", "b.py"]), _later(paths=["b.py", "z.py"])],
    )

    assert step["kind"] == "needs-attention"
    assert step["culprit_sha"] is None
    assert "c3" in str(step["reason"])
    assert "b.py" in str(step["reason"])


def test_a_later_commit_touching_only_other_paths_does_not_block_the_revert(
    *, tmp_path: Path
) -> None:
    step = _step(
        tmp_path=tmp_path,
        commits=[_green(), _culprit(paths=["a.py"]), _later(paths=["z.py"])],
    )

    assert step["kind"] == "open-revert"
    assert step["culprit_sha"] == _CULPRIT_SHA


@pytest.mark.parametrize(
    ("culprit_paths", "later_paths"),
    [(None, ["z.py"]), (["a.py"], None)],
)
def test_unrecorded_paths_cannot_show_a_revert_is_safe_so_it_is_not_created(
    *, tmp_path: Path, culprit_paths: list[str] | None, later_paths: list[str] | None
) -> None:
    step = _step(
        tmp_path=tmp_path,
        commits=[_green(), _culprit(paths=culprit_paths), _later(paths=later_paths)],
    )

    assert step["kind"] == "needs-attention"
    assert "not recorded" in str(step["reason"])


def test_a_culprit_at_the_head_needs_no_recorded_paths_because_nothing_can_obstruct(
    *, tmp_path: Path
) -> None:
    step = _step(tmp_path=tmp_path, commits=[_green(), _culprit(paths=None)])

    assert step["kind"] == "open-revert"


@pytest.mark.parametrize(
    "subject",
    [
        "chore(revert): undo 0123456789ab to return master to green",
        'Revert "feat(widget): an ordinary merge (#7)"',
    ],
)
def test_the_reconciler_never_reverts_a_revert(*, tmp_path: Path, subject: str) -> None:
    step = _step(tmp_path=tmp_path, commits=[_green(), _culprit(paths=["a.py"], subject=subject)])

    assert step["kind"] == "needs-attention"
    assert "revert" in str(step["reason"])


def test_a_culprit_is_reverted_at_most_once_per_episode(*, tmp_path: Path) -> None:
    landed = f"chore(revert): undo {_CULPRIT_SHA[:12]} to return master to green (#9)"

    step = _step(
        tmp_path=tmp_path,
        commits=[_green(), _culprit(paths=["a.py"]), _later(paths=["a.py"], subject=landed)],
    )

    assert step["kind"] == "needs-attention"
    assert "already reverted" in str(step["reason"])


def test_a_revert_of_some_other_culprit_does_not_count_as_this_culprit_s_revert(
    *, tmp_path: Path
) -> None:
    other = "chore(revert): undo 111111111111 to return master to green (#9)"

    step = _step(
        tmp_path=tmp_path,
        commits=[_green(), _culprit(paths=["a.py"]), _later(paths=["z.py"], subject=other)],
    )

    assert step["kind"] == "open-revert"
