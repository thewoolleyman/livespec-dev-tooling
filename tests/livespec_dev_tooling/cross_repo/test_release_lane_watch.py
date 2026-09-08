"""Replay tests for `release_lane_watch` — RECORDED history, not a live lane.

THE WINDOW, STATED BY DATE. Every fixture row below is `thewoolleyman/livespec`'s
own `release-tag.yml` run history as the forge returned it on 2026-09-08, from
`v0.28.5` (2026-08-09) through `v0.37.1` (2026-08-21), newest-first, verbatim.
It carries what a replay needs and a synthetic fixture would have to be trusted
to contain:

- a KNOWN-RED interval — 17 consecutive failed cuts, `v0.31.0` (2026-08-12) to
  `v0.37.0` (2026-08-20);
- a KNOWN-GREEN boundary BELOW it — `v0.30.3` (2026-08-12T01:04:02Z), the last
  green before the block;
- a KNOWN-GREEN boundary ABOVE it — `v0.37.1` (2026-08-21T22:57:27Z), the cut
  that ended it;
- and a second, shorter block below (`v0.29.0`..`v0.30.0`, 2026-08-10 to
  2026-08-11) bounded by greens on both sides.

Both transitions are asserted in BOTH directions: green→red (the history cut at
`v0.37.0` reports FAILING) and red→green (the same history with `v0.37.1`
appended reports healthy). The five-cut sub-window `v0.34.2`..`v0.37.0` named in
work-item `livespec-dev-tooling-37p0` is replayed as the TRUNCATION case, because
supplying only those five leaves the block flush against the oldest run and no
green above it — the state the detector must report as a lower bound rather than
as a count.
"""

from __future__ import annotations

from livespec_dev_tooling.cross_repo.release_lane_watch import lane_state, notice_text

_WORKFLOW = "release-tag.yml"

_RECORDED_RELEASE_TAG_RUNS: list[dict[str, str]] = [
    {"tag": "v0.37.1", "created_at": "2026-08-21T22:57:27Z", "conclusion": "success"},
    {"tag": "v0.37.0", "created_at": "2026-08-20T11:29:03Z", "conclusion": "failure"},
    {"tag": "v0.36.0", "created_at": "2026-08-19T15:53:59Z", "conclusion": "failure"},
    {"tag": "v0.35.1", "created_at": "2026-08-18T23:48:27Z", "conclusion": "failure"},
    {"tag": "v0.35.0", "created_at": "2026-08-18T13:37:08Z", "conclusion": "failure"},
    {"tag": "v0.34.2", "created_at": "2026-08-17T14:20:47Z", "conclusion": "failure"},
    {"tag": "v0.34.1", "created_at": "2026-08-17T07:29:13Z", "conclusion": "failure"},
    {"tag": "v0.34.0", "created_at": "2026-08-17T02:39:15Z", "conclusion": "failure"},
    {"tag": "v0.33.7", "created_at": "2026-08-17T01:09:53Z", "conclusion": "failure"},
    {"tag": "v0.33.6", "created_at": "2026-08-13T22:41:45Z", "conclusion": "failure"},
    {"tag": "v0.33.5", "created_at": "2026-08-13T08:00:07Z", "conclusion": "failure"},
    {"tag": "v0.33.4", "created_at": "2026-08-13T03:43:33Z", "conclusion": "failure"},
    {"tag": "v0.33.3", "created_at": "2026-08-12T11:03:31Z", "conclusion": "failure"},
    {"tag": "v0.33.2", "created_at": "2026-08-12T09:29:32Z", "conclusion": "failure"},
    {"tag": "v0.33.1", "created_at": "2026-08-12T06:38:06Z", "conclusion": "failure"},
    {"tag": "v0.33.0", "created_at": "2026-08-12T03:14:46Z", "conclusion": "failure"},
    {"tag": "v0.32.0", "created_at": "2026-08-12T02:55:18Z", "conclusion": "failure"},
    {"tag": "v0.31.0", "created_at": "2026-08-12T02:36:50Z", "conclusion": "failure"},
    {"tag": "v0.30.3", "created_at": "2026-08-12T01:04:02Z", "conclusion": "success"},
    {"tag": "v0.30.2", "created_at": "2026-08-11T07:53:05Z", "conclusion": "success"},
    {"tag": "v0.30.1", "created_at": "2026-08-11T06:55:21Z", "conclusion": "success"},
    {"tag": "v0.30.0", "created_at": "2026-08-11T06:16:51Z", "conclusion": "failure"},
    {"tag": "v0.29.2", "created_at": "2026-08-11T05:44:24Z", "conclusion": "failure"},
    {"tag": "v0.29.1", "created_at": "2026-08-11T04:49:33Z", "conclusion": "failure"},
    {"tag": "v0.29.0", "created_at": "2026-08-10T06:51:25Z", "conclusion": "failure"},
    {"tag": "v0.28.5", "created_at": "2026-08-09T13:46:25Z", "conclusion": "success"},
]

_OLDEST_RECORDED = "v0.28.5"


def _window(*, newest: str, oldest: str) -> list[dict[str, str]]:
    """Return the recorded runs between two release tags, inclusive, newest-first."""
    tags = [run["tag"] for run in _RECORDED_RELEASE_TAG_RUNS]
    return _RECORDED_RELEASE_TAG_RUNS[tags.index(newest) : tags.index(oldest) + 1]


def _run(*, tag: str) -> dict[str, str]:
    """Return one recorded run by its release tag."""
    return _window(newest=tag, oldest=tag)[0]


def test_replay_red_interval_through_v0_37_0_reports_state_not_an_edge() -> None:
    """Green→red: the history cut at 2026-08-20 is FAILING, with the block measured.

    The block runs `v0.31.0` (2026-08-12T02:36:50Z) through `v0.37.0`
    (2026-08-20T11:29:03Z) and the last green above it is `v0.30.3`
    (2026-08-12T01:04:02Z). The answer is the lane's STATE, not a transition: a
    reader arriving on any day of those eight gets the same verdict.
    """
    state = lane_state(runs=_window(newest="v0.37.0", oldest=_OLDEST_RECORDED))

    assert state["healthy"] is False
    assert state["consecutive_failures"] == 17
    assert state["failing_since"] == "2026-08-12T02:36:50Z"
    assert state["last_green"] == "2026-08-12T01:04:02Z"
    assert state["truncated"] is False
    assert state["runs_considered"] == 25


def test_replay_green_boundary_v0_37_1_on_2026_08_21_clears_the_lane() -> None:
    """Red→green: appending the 2026-08-21 success ends the block and goes silent."""
    state = lane_state(runs=_window(newest="v0.37.1", oldest=_OLDEST_RECORDED))

    assert state["healthy"] is True
    assert state["consecutive_failures"] == 0
    assert state["failing_since"] is None
    assert state["last_green"] == "2026-08-21T22:57:27Z"
    assert state["truncated"] is False
    assert notice_text(workflow=_WORKFLOW, state=state) == ""


def test_replay_verdict_does_not_depend_on_the_order_runs_arrive_in() -> None:
    """The forge returns newest-first; a hand-collected list may not. Same answer."""
    newest_first = _window(newest="v0.37.0", oldest=_OLDEST_RECORDED)

    assert lane_state(runs=list(reversed(newest_first))) == lane_state(runs=newest_first)


def test_truncated_block_flush_against_the_oldest_run_is_a_lower_bound() -> None:
    """The five cuts `v0.34.2`..`v0.37.0` (2026-08-17..2026-08-20) with nothing above.

    Supplied alone, the block reaches the oldest run in the history, so its extent
    was never measured. Reporting `5` as a count would be a claim the input cannot
    support — the same real outage read as 4 cuts at limit 20 and 123 at limit 300.
    """
    state = lane_state(runs=_window(newest="v0.37.0", oldest="v0.34.2"))

    assert state["healthy"] is False
    assert state["consecutive_failures"] == 5
    assert state["truncated"] is True
    assert state["last_green"] is None

    notice = notice_text(workflow=_WORKFLOW, state=state)
    assert "at least 5 consecutive runs since 2026-08-17T14:20:47Z" in notice
    assert "NO GREEN in the history supplied" in notice


def test_untruncated_block_is_reported_as_an_exact_count_with_its_last_green() -> None:
    """The same lane, measured: no `at least`, and the absolute last-green instant."""
    state = lane_state(runs=_window(newest="v0.37.0", oldest=_OLDEST_RECORDED))

    notice = notice_text(workflow=_WORKFLOW, state=state)
    assert notice.startswith(f"{_WORKFLOW}: FAILING — 17 consecutive runs since ")
    assert "at least" not in notice
    assert notice.endswith("last green 2026-08-12T01:04:02Z")


def test_undecided_conclusions_are_ignored_rather_than_counted_either_way() -> None:
    """A cancelled cut and one still in flight neither end the block nor extend it."""
    runs = [
        {"tag": "v0.37.0-rerun", "created_at": "2026-08-20T12:00:00Z", "conclusion": ""},
        {"tag": "v0.37.0-cancel", "created_at": "2026-08-20T11:45:00Z", "conclusion": "cancelled"},
        *_window(newest="v0.37.0", oldest=_OLDEST_RECORDED),
    ]

    assert lane_state(runs=runs) == lane_state(runs=_window(newest="v0.37.0", oldest="v0.28.5"))


def test_a_single_failed_cut_stays_silent_below_the_transient_threshold() -> None:
    """One red cut is indistinguishable from a flake; a watcher that cries wolf is muted.

    Two RECORDED runs, selected to isolate a single trailing failure: the
    `v0.30.0` cut of 2026-08-11 over the `v0.28.5` green of 2026-08-09. The state
    still says the lane is not healthy — the SILENCE is the notice's judgement
    about a transient, not a claim that the cut succeeded.
    """
    state = lane_state(runs=[_run(tag="v0.30.0"), _run(tag=_OLDEST_RECORDED)])

    assert state["healthy"] is False
    assert state["consecutive_failures"] == 1
    assert state["last_green"] == "2026-08-09T13:46:25Z"
    assert notice_text(workflow=_WORKFLOW, state=state) == ""


def test_empty_history_reports_no_lane_state_rather_than_a_failure() -> None:
    """A lane with no decided runs has nothing to report — and nothing to alarm on."""
    state = lane_state(runs=[])

    assert state == {
        "healthy": True,
        "consecutive_failures": 0,
        "failing_since": None,
        "last_green": None,
        "truncated": False,
        "runs_considered": 0,
    }
