"""Tests for the fix-forward claim, progress/thrash state machine and hard cap.

Per `SPECIFICATION/contracts.md` section "Master-health reconciler" (work-item
`livespec-dev-tooling-joqff6`, child of plan `red-master-self-healing`).

EVERY SCENARIO IS REPLAYED THROUGH THE RECORDING. Each test builds the JSON
recording the reusable workflow's gatherer would write and hands it to
`master_health_step.main`, so the assertion is on the step the performing
workflow would read: claim validity, the stall clock, the thrash rules and the
hard cap are proven end to end through the parse seam, not against a hand-built
dataclass the gatherer could never produce.

THE CLOCK IS DATA. Every timestamp is epoch seconds in the recording and
`observed_at` is "now", so a replay is deterministic: the decision path holds no
clock. `_at(minutes=...)` places an instant that many minutes after the moment
`master` went red.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from livespec_dev_tooling.cross_repo.master_health_step import main

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = []


_RED_AT = 1_000_000
_MAINTAINER = "maintainer-login"
_OPENER = "culprit-opener"
_FIX = 50
_STRANGER = "someone-else"

_CONFIG: dict[str, object] = {
    "maintainer_login": _MAINTAINER,
    "hard_cap_minutes": 120,
    "stall_claim_to_fix_pr_minutes": 80,
    "stall_ci_in_flight_minutes": 20,
    "stall_fix_to_merge_minutes": 75,
    "stall_merged_to_green_minutes": 20,
}


def _at(*, minutes: int) -> int:
    """The instant `minutes` after `master` went red."""
    return _RED_AT + minutes * 60


def _commit(
    *,
    sha: str,
    parent: str,
    conclusion: str,
    pull_request: int | None,
    completed_at: int | None,
) -> dict[str, object]:
    return {
        "sha": sha,
        "parent_sha": parent,
        "pull_request": pull_request,
        "ci_workflow": "ci.yml",
        "ci_conclusion": conclusion,
        "failure_signature": "check-lint" if conclusion == "failure" else None,
        "subject": "feat(widget): an ordinary merge (#7)",
        "ci_completed_at": completed_at,
    }


def _claim(
    *, author: str = _MAINTAINER, body: str | None = None, minutes: int = 5
) -> dict[str, object]:
    return {
        "author": author,
        "body": f"Fix-Forward: #{_FIX}\n" if body is None else body,
        "posted_at": _at(minutes=minutes),
    }


def _fix_commit(
    *,
    sha: str = "f1",
    pushed: int = 10,
    conclusion: str = "pending",
    started: int | None = None,
    finished: int | None = None,
    failing: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "sha": sha,
        "pushed_at": _at(minutes=pushed),
        "ci_conclusion": conclusion,
        "ci_started_at": None if started is None else _at(minutes=started),
        "ci_finished_at": None if finished is None else _at(minutes=finished),
        "failing_checks": list(failing),
    }


def _fix(
    *,
    commits: list[dict[str, object]] | None = None,
    state: str = "open",
    number: int = _FIX,
    armed: int | None = None,
    merged: int | None = None,
    master_conclusion: str | None = None,
    master_started: int | None = None,
) -> dict[str, object]:
    return {
        "number": number,
        "state": state,
        "opened_at": _at(minutes=10),
        "commits": [_fix_commit(started=11)] if commits is None else commits,
        "auto_merge_armed_at": None if armed is None else _at(minutes=armed),
        "merged_at": None if merged is None else _at(minutes=merged),
        "master_ci_conclusion": master_conclusion,
        "master_ci_started_at": None if master_started is None else _at(minutes=master_started),
    }


def _revert(
    *,
    ci: str = "success",
    claims: list[dict[str, object]] | None = None,
    fixes: list[dict[str, object]] | None = None,
    opener: str | None = _OPENER,
) -> dict[str, object]:
    return {
        "number": 9,
        "reverts_pull_request": 7,
        "ci_conclusion": ci,
        "auto_merge_armed": False,
        "culprit_opened_by": opener,
        "claims": [_claim()] if claims is None else claims,
        "fix_pull_requests": [_fix()] if fixes is None else fixes,
    }


def _kind(
    *,
    tmp_path: Path,
    revert: dict[str, object],
    observed: int,
    config: dict[str, object] | None = None,
    red_completed_at: int | None = _RED_AT,
    observed_at_recorded: bool = True,
) -> str:
    """Replay one recording and return the chosen step kind."""
    record: dict[str, object] = {
        "target_branch": "master",
        "infra_outage_markers": [],
        "gating_workflow": "ci.yml",
        "unrelated_lookback_commits": 20,
        **(_CONFIG if config is None else config),
        "head_sha": "c2",
        "rerun_outcome": "still-red",
        "commits": [
            _commit(
                sha="c1",
                parent="c0",
                conclusion="success",
                pull_request=None,
                completed_at=_at(minutes=-10),
            ),
            _commit(
                sha="c2",
                parent="c1",
                conclusion="failure",
                pull_request=7,
                completed_at=red_completed_at,
            ),
        ],
        "revert_pull_request": revert,
        "needs_attention_issue_titles": [],
    }
    if observed_at_recorded:
        record["observed_at"] = _at(minutes=observed)
    state_path = tmp_path / "state.json"
    step_path = tmp_path / "step.json"
    _ = state_path.write_text(json.dumps(record), encoding="utf-8")
    assert main(argv=["--state", str(state_path), "--step-out", str(step_path)]) == 0
    step = json.loads(step_path.read_text(encoding="utf-8"))
    assert isinstance(step, dict)
    return str(step["kind"])


def _reason(*, tmp_path: Path) -> str:
    step = json.loads((tmp_path / "step.json").read_text(encoding="utf-8"))
    assert isinstance(step, dict)
    return str(step["reason"])


# ---------------------------------------------------------------------------
# Scenario: a valid fix-forward claim holds the revert while the fix progresses
# ---------------------------------------------------------------------------


def test_a_maintainer_claim_holds_the_revert_while_the_fix_makes_progress(
    *, tmp_path: Path
) -> None:
    kind = _kind(tmp_path=tmp_path, revert=_revert(), observed=20)

    assert kind == "none"
    assert "holds" in _reason(tmp_path=tmp_path)


def test_a_held_revert_with_a_failing_revert_ci_raises_nothing_while_the_claim_holds(
    *, tmp_path: Path
) -> None:
    assert _kind(tmp_path=tmp_path, revert=_revert(ci="failure"), observed=20) == "none"


def test_the_culprit_opener_s_claim_with_a_claimed_by_line_holds_the_revert(
    *, tmp_path: Path
) -> None:
    claim = _claim(author=_OPENER, body=f"Fix-Forward: #{_FIX}\nClaimed-By: session-abc\n")

    assert _kind(tmp_path=tmp_path, revert=_revert(claims=[claim]), observed=20) == "none"


def test_the_author_comparison_ignores_case_because_forge_logins_do(*, tmp_path: Path) -> None:
    claim = _claim(author=_MAINTAINER.upper())

    assert _kind(tmp_path=tmp_path, revert=_revert(claims=[claim]), observed=20) == "none"


def test_a_fix_with_fewer_failing_checks_on_a_new_commit_is_forward_progress(
    *, tmp_path: Path
) -> None:
    commits = [
        _fix_commit(
            sha="f1", pushed=10, conclusion="failure", started=11, finished=15, failing=("a", "b")
        ),
        _fix_commit(sha="f2", pushed=16, conclusion="pending", started=17),
    ]
    reduced = [
        commits[0],
        _fix_commit(
            sha="f2", pushed=16, conclusion="failure", started=17, finished=19, failing=("a",)
        ),
    ]

    held = _kind(tmp_path=tmp_path, revert=_revert(fixes=[_fix(commits=commits)]), observed=25)
    still = _kind(tmp_path=tmp_path, revert=_revert(fixes=[_fix(commits=reduced)]), observed=25)

    assert (held, still) == ("none", "none")


def test_a_cancelled_commit_is_undecided_and_not_compared_for_thrash(*, tmp_path: Path) -> None:
    commits = [
        _fix_commit(
            sha="f1", pushed=10, conclusion="failure", started=11, finished=15, failing=("a", "b")
        ),
        _fix_commit(sha="f2", pushed=16, conclusion="cancelled", started=17),
        _fix_commit(
            sha="f3", pushed=18, conclusion="failure", started=19, finished=21, failing=("a",)
        ),
    ]

    assert (
        _kind(tmp_path=tmp_path, revert=_revert(fixes=[_fix(commits=commits)]), observed=25)
        == "none"
    )


def test_a_claim_naming_a_fix_without_a_recorded_pull_request_holds_until_the_claim_stalls(
    *, tmp_path: Path
) -> None:
    within = _kind(tmp_path=tmp_path, revert=_revert(fixes=[]), observed=5 + 80)
    beyond = _kind(tmp_path=tmp_path, revert=_revert(fixes=[]), observed=5 + 81)

    assert (within, beyond) == ("none", "release-revert")


def test_a_second_claim_naming_the_same_fix_is_one_claim_not_a_contest(*, tmp_path: Path) -> None:
    claims = [_claim(minutes=5), _claim(minutes=6)]

    assert _kind(tmp_path=tmp_path, revert=_revert(claims=claims), observed=20) == "none"


def test_an_unclaimed_fix_pull_request_record_is_not_consulted(*, tmp_path: Path) -> None:
    fixes = [_fix(number=51, state="closed"), _fix()]

    assert _kind(tmp_path=tmp_path, revert=_revert(fixes=fixes), observed=20) == "none"


# ---------------------------------------------------------------------------
# Scenario: a thrashing fix-forward releases the held revert
# ---------------------------------------------------------------------------


def test_a_fix_failing_the_same_check_repeatedly_releases_the_revert(*, tmp_path: Path) -> None:
    repeated = _fix_commit(conclusion="failure", started=11, finished=15, failing=("lint", "lint"))

    kind = _kind(tmp_path=tmp_path, revert=_revert(fixes=[_fix(commits=[repeated])]), observed=20)

    assert kind == "release-revert"
    assert "repeatedly" in _reason(tmp_path=tmp_path)


def test_a_new_commit_that_does_not_reduce_the_failing_checks_releases_the_revert(
    *, tmp_path: Path
) -> None:
    commits = [
        _fix_commit(
            sha="f1", pushed=10, conclusion="failure", started=11, finished=15, failing=("a", "b")
        ),
        _fix_commit(
            sha="f2", pushed=16, conclusion="failure", started=17, finished=19, failing=("b", "a")
        ),
    ]

    kind = _kind(tmp_path=tmp_path, revert=_revert(fixes=[_fix(commits=commits)]), observed=25)

    assert kind == "release-revert"
    assert "reduce" in _reason(tmp_path=tmp_path)


def test_a_new_commit_failing_a_new_check_releases_the_revert(*, tmp_path: Path) -> None:
    commits = [
        _fix_commit(
            sha="f1", pushed=10, conclusion="failure", started=11, finished=15, failing=("a", "b")
        ),
        _fix_commit(
            sha="f2", pushed=16, conclusion="failure", started=17, finished=19, failing=("a", "c")
        ),
    ]

    kind = _kind(tmp_path=tmp_path, revert=_revert(fixes=[_fix(commits=commits)]), observed=25)

    assert kind == "release-revert"
    assert "new check" in _reason(tmp_path=tmp_path)


def test_a_check_failing_after_a_green_commit_is_a_new_failing_check(*, tmp_path: Path) -> None:
    commits = [
        _fix_commit(sha="f1", pushed=10, conclusion="success", started=11, finished=15),
        _fix_commit(
            sha="f2", pushed=16, conclusion="failure", started=17, finished=19, failing=("a",)
        ),
    ]

    assert (
        _kind(tmp_path=tmp_path, revert=_revert(fixes=[_fix(commits=commits)]), observed=25)
        == "release-revert"
    )


def test_a_fix_that_merged_while_master_stays_red_releases_the_revert(*, tmp_path: Path) -> None:
    merged = _fix(
        commits=[_fix_commit(conclusion="success", started=11, finished=14)],
        state="merged",
        merged=20,
        master_conclusion="failure",
        master_started=21,
    )

    kind = _kind(tmp_path=tmp_path, revert=_revert(fixes=[merged]), observed=30)

    assert kind == "release-revert"
    assert "merged" in _reason(tmp_path=tmp_path)


# ---------------------------------------------------------------------------
# Scenario: a stalled or contested fix-forward releases the held revert
# ---------------------------------------------------------------------------


def test_a_claim_with_no_fix_pull_request_stalls_after_the_claim_step_duration(
    *, tmp_path: Path
) -> None:
    kind = _kind(tmp_path=tmp_path, revert=_revert(fixes=[]), observed=5 + 81)

    assert kind == "release-revert"
    assert "no forward transition" in _reason(tmp_path=tmp_path)


def test_a_fix_whose_ci_is_in_flight_stalls_after_the_ci_step_duration(*, tmp_path: Path) -> None:
    fix = _fix(commits=[_fix_commit(pushed=10, started=11)])

    within = _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=11 + 20)
    beyond = _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=11 + 21)

    assert (within, beyond) == ("none", "release-revert")


def test_a_fix_commit_whose_ci_never_starts_stalls_on_the_ci_step_duration(
    *, tmp_path: Path
) -> None:
    fix = _fix(commits=[_fix_commit(pushed=10)])

    assert (
        _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=10 + 21) == "release-revert"
    )


def test_a_fix_pull_request_with_no_commits_is_waiting_on_ci(*, tmp_path: Path) -> None:
    fix = _fix(commits=[])

    within = _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=10 + 20)
    beyond = _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=10 + 21)

    assert (within, beyond) == ("none", "release-revert")


def test_a_green_fix_waiting_to_merge_stalls_after_the_merge_step_duration(
    *, tmp_path: Path
) -> None:
    fix = _fix(commits=[_fix_commit(conclusion="success", started=11, finished=14)])

    within = _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=14 + 75)
    beyond = _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=14 + 76)

    assert (within, beyond) == ("none", "release-revert")


def test_arming_auto_merge_restarts_the_step_clock(*, tmp_path: Path) -> None:
    fix = _fix(commits=[_fix_commit(conclusion="success", started=11, finished=14)], armed=40)

    assert _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=40 + 75) == "none"
    assert (
        _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=40 + 76) == "release-revert"
    )


def test_a_red_fix_awaiting_a_new_commit_waits_on_the_merge_step_duration(
    *, tmp_path: Path
) -> None:
    fix = _fix(commits=[_fix_commit(conclusion="failure", started=11, finished=14, failing=("a",))])

    assert _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=14 + 75) == "none"


def test_a_merged_fix_waiting_for_master_ci_stalls_after_the_merged_step_duration(
    *, tmp_path: Path
) -> None:
    fix = _fix(
        commits=[_fix_commit(conclusion="success", started=11, finished=14)],
        state="merged",
        merged=30,
    )

    within = _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=30 + 20)
    beyond = _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=30 + 21)

    assert (within, beyond) == ("none", "release-revert")


def test_master_ci_running_on_the_merged_fix_is_measured_against_the_ci_step_duration(
    *, tmp_path: Path
) -> None:
    fix = _fix(
        commits=[_fix_commit(conclusion="success", started=11, finished=14)],
        state="merged",
        merged=30,
        master_conclusion="pending",
        master_started=31,
    )

    assert _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=31 + 20) == "none"
    assert (
        _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=31 + 21) == "release-revert"
    )


def test_a_fix_pull_request_closed_without_merging_releases_the_revert(*, tmp_path: Path) -> None:
    kind = _kind(tmp_path=tmp_path, revert=_revert(fixes=[_fix(state="closed")]), observed=20)

    assert kind == "release-revert"
    assert "closed" in _reason(tmp_path=tmp_path)


def test_two_competing_fix_pull_requests_release_the_revert(*, tmp_path: Path) -> None:
    claims = [_claim(), _claim(body="Fix-Forward: #51\n", minutes=6)]

    kind = _kind(tmp_path=tmp_path, revert=_revert(claims=claims), observed=20)

    assert kind == "release-revert"
    assert "more than one" in _reason(tmp_path=tmp_path)


def test_one_claim_comment_naming_two_fix_pull_requests_is_contested(*, tmp_path: Path) -> None:
    claims = [_claim(body="Fix-Forward: #50\nFix-Forward: #51\n")]

    assert _kind(tmp_path=tmp_path, revert=_revert(claims=claims), observed=20) == "release-revert"


# ---------------------------------------------------------------------------
# Scenario: the hard cap, with and without green revert CI
# ---------------------------------------------------------------------------


def test_at_the_hard_cap_a_revert_with_green_ci_lands_despite_a_progressing_fix(
    *, tmp_path: Path
) -> None:
    fix = _fix(commits=[_fix_commit(pushed=119, started=120)])

    kind = _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=121)

    assert kind == "release-revert"
    assert "hard cap" in _reason(tmp_path=tmp_path)


def test_a_progressing_claim_still_holds_exactly_at_the_hard_cap(*, tmp_path: Path) -> None:
    fix = _fix(commits=[_fix_commit(pushed=119, started=120)])

    assert _kind(tmp_path=tmp_path, revert=_revert(fixes=[fix]), observed=120) == "none"


def test_at_the_hard_cap_a_revert_whose_ci_is_not_green_is_not_merged(*, tmp_path: Path) -> None:
    fix = _fix(commits=[_fix_commit(pushed=119, started=120)])

    for ci in ("failure", "pending", "cancelled"):
        kind = _kind(tmp_path=tmp_path, revert=_revert(ci=ci, fixes=[fix]), observed=121)

        assert kind == "needs-attention", ci
        assert "hard cap" in _reason(tmp_path=tmp_path)


# ---------------------------------------------------------------------------
# Scenario: a fix-forward claim from outside the claimant set is ignored
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("author", "body", "opener"),
    [
        (_STRANGER, f"Fix-Forward: #{_FIX}\nClaimed-By: session-abc\n", _OPENER),
        (_OPENER, f"Fix-Forward: #{_FIX}\n", _OPENER),
        (_OPENER, f"Fix-Forward: #{_FIX}\nClaimed-By:   \n", _OPENER),
        (_OPENER, f"Fix-Forward: #{_FIX}\nClaimed-By: session-abc\n", None),
        (_MAINTAINER, "I will fix this one forward, give me a while.", _OPENER),
    ],
)
def test_a_claim_outside_the_claimant_set_is_ignored_and_the_revert_is_released(
    *, tmp_path: Path, author: str, body: str, opener: str | None
) -> None:
    revert = _revert(claims=[_claim(author=author, body=body)], opener=opener)

    assert _kind(tmp_path=tmp_path, revert=revert, observed=20) == "release-revert"


def test_an_ignored_claim_does_not_contest_a_valid_one(*, tmp_path: Path) -> None:
    claims = [_claim(), _claim(author=_STRANGER, body="Fix-Forward: #51\n", minutes=6)]

    assert _kind(tmp_path=tmp_path, revert=_revert(claims=claims), observed=20) == "none"


def test_a_missing_maintainer_login_leaves_only_the_culprit_opener_as_a_claimant(
    *, tmp_path: Path
) -> None:
    config = {key: value for key, value in _CONFIG.items() if key != "maintainer_login"}

    ignored = _kind(tmp_path=tmp_path, revert=_revert(), observed=20, config=config)

    assert ignored == "release-revert"


# ---------------------------------------------------------------------------
# Scenario: missing or malformed configuration fails closed to revert-by-default
# ---------------------------------------------------------------------------


_MALFORMED_VALUES: tuple[object, ...] = ("120", 0, -5, True, 1.5, None, [120])


@pytest.mark.parametrize("key", [key for key in _CONFIG if key != "maintainer_login"])
def test_a_missing_hard_cap_or_stall_duration_does_not_hold_for_a_valid_claim(
    *, tmp_path: Path, key: str
) -> None:
    config = {name: value for name, value in _CONFIG.items() if name != key}

    kind = _kind(tmp_path=tmp_path, revert=_revert(), observed=20, config=config)

    assert kind == "release-revert"
    assert "fail" in _reason(tmp_path=tmp_path)


@pytest.mark.parametrize("key", [key for key in _CONFIG if key != "maintainer_login"])
def test_a_malformed_hard_cap_or_stall_duration_does_not_hold_for_a_valid_claim(
    *, tmp_path: Path, key: str
) -> None:
    for malformed in _MALFORMED_VALUES:
        config = {**_CONFIG, key: malformed}

        kind = _kind(tmp_path=tmp_path, revert=_revert(), observed=20, config=config)

        assert kind == "release-revert", f"{key}={malformed!r} still held the revert"


def test_failing_closed_still_merges_only_a_revert_whose_own_ci_is_green(*, tmp_path: Path) -> None:
    config = {name: value for name, value in _CONFIG.items() if name != "hard_cap_minutes"}

    kind = _kind(tmp_path=tmp_path, revert=_revert(ci="failure"), observed=20, config=config)

    assert kind == "needs-attention"


def test_a_missing_observation_time_fails_closed_to_revert_by_default(*, tmp_path: Path) -> None:
    kind = _kind(tmp_path=tmp_path, revert=_revert(), observed=20, observed_at_recorded=False)

    assert kind == "release-revert"


def test_an_unknown_red_since_time_fails_closed_to_revert_by_default(*, tmp_path: Path) -> None:
    kind = _kind(tmp_path=tmp_path, revert=_revert(), observed=20, red_completed_at=None)

    assert kind == "release-revert"


def test_a_malformed_claim_or_fix_record_fails_closed_loudly(*, tmp_path: Path) -> None:
    bad_reverts = (
        {**_revert(), "claims": "not a list"},
        {**_revert(), "claims": ["not an object"]},
        {**_revert(), "claims": [{"author": "x", "body": "y"}]},
        {**_revert(), "fix_pull_requests": "not a list"},
        {**_revert(), "fix_pull_requests": ["not an object"]},
        {**_revert(), "fix_pull_requests": [{**_fix(), "commits": "not a list"}]},
        {**_revert(), "fix_pull_requests": [{**_fix(), "commits": ["not an object"]}]},
        {**_revert(), "fix_pull_requests": [{**_fix(), "commits": [{"sha": "f1"}]}]},
        {
            **_revert(),
            "fix_pull_requests": [
                {**_fix(), "commits": [{**_fix_commit(), "failing_checks": "x"}]}
            ],
        },
        {**_revert(), "fix_pull_requests": [{**_fix(), "state": 3}]},
        {**_revert(), "fix_pull_requests": [{"number": _FIX}]},
        {**_revert(), "culprit_opened_by": 3},
    )
    for revert in bad_reverts:
        state_path = tmp_path / "state.json"
        step_path = tmp_path / "bad-step.json"
        record = {
            "target_branch": "master",
            "infra_outage_markers": [],
            "gating_workflow": "ci.yml",
            "unrelated_lookback_commits": 20,
            **_CONFIG,
            "head_sha": "c2",
            "rerun_outcome": "still-red",
            "observed_at": _at(minutes=20),
            "commits": [
                _commit(
                    sha="c1",
                    parent="c0",
                    conclusion="success",
                    pull_request=None,
                    completed_at=None,
                ),
                _commit(
                    sha="c2",
                    parent="c1",
                    conclusion="failure",
                    pull_request=7,
                    completed_at=_RED_AT,
                ),
            ],
            "revert_pull_request": revert,
            "needs_attention_issue_titles": [],
        }
        _ = state_path.write_text(json.dumps(record), encoding="utf-8")

        code = main(argv=["--state", str(state_path), "--step-out", str(step_path)])

        assert code == 1, f"{revert} did not fail closed"
        assert not step_path.is_file()
