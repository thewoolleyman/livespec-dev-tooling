"""Replay tests for the shared release-lane watcher.

Lifted from `livespec-overseer` (work-item overseer-hgq4wi.15) so every
publishing fleet repo can consume one implementation instead of forking it.
`lane_state` is a PURE function of run history, which is what makes these
replay tests possible: the lane's verdict is proven against RECORDED intervals
with both boundaries present, never against whatever the fleet happens to be
doing on the day the suite runs.

The window replayed below is livespec's own, and it is real: `Release tag`
failed on v0.34.2, v0.35.0, v0.35.1, v0.36.0 and v0.37.0 — five consecutive
cuts — then went green on v0.37.1 at 2026-08-21T22:57:27Z. Both boundaries are
present, so the transition is asserted in BOTH directions.

Three properties here were each earned by a measured failure and would be lost
by a from-scratch reimplementation:

- The verdict reports STATE, not an edge. At a high failure rate a
  transition-triggered alert is silent through most of the outage, because most
  of the lane's life IS the failure.
- It carries the absolute last-green timestamp, because "123 failures" invites
  the reader to assume recency while "failing since <date>" does not.
- It knows when its own input was TRUNCATED. The same real outage read as 4
  cuts at limit 20 and 123 at limit 300, so a block flush against the oldest
  supplied run is a LOWER BOUND and must say so.
"""

from __future__ import annotations

from livespec_dev_tooling.cross_repo.release_lane_watch import lane_state, notice_text

__all__: list[str] = []

# The real livespec release-tag window, oldest first.
_RED_STREAK: list[dict[str, str]] = [
    {"conclusion": "success", "created_at": "2026-08-16T10:00:00Z"},
    {"conclusion": "failure", "created_at": "2026-08-17T14:20:47Z"},
    {"conclusion": "failure", "created_at": "2026-08-18T13:37:08Z"},
    {"conclusion": "failure", "created_at": "2026-08-18T23:48:27Z"},
    {"conclusion": "failure", "created_at": "2026-08-19T15:53:59Z"},
    {"conclusion": "failure", "created_at": "2026-08-20T11:29:03Z"},
]
_RECOVERED = [*_RED_STREAK, {"conclusion": "success", "created_at": "2026-08-21T22:57:27Z"}]


def test_a_failing_lane_reports_the_streak_and_its_absolute_last_green() -> None:
    """Replay 2026-08-17..08-20: five consecutive failures, green boundary above."""
    state = lane_state(runs=_RED_STREAK)
    assert state["healthy"] is False
    assert state["consecutive_failures"] == 5
    assert state["failing_since"] == "2026-08-17T14:20:47Z"
    assert state["last_green"] == "2026-08-16T10:00:00Z"
    assert state["truncated"] is False


def test_the_same_lane_reads_healthy_once_the_green_cut_lands() -> None:
    """Replay the OTHER direction: v0.37.1 ends the streak."""
    state = lane_state(runs=_RECOVERED)
    assert state["healthy"] is True
    assert state["consecutive_failures"] == 0
    assert state["failing_since"] is None
    assert state["last_green"] == "2026-08-21T22:57:27Z"


def test_a_block_flush_against_the_oldest_run_is_reported_as_a_lower_bound() -> None:
    """No green above the block means the extent was never measured."""
    state = lane_state(runs=_RED_STREAK[1:])
    assert state["truncated"] is True
    assert state["last_green"] is None
    assert notice_text(workflow="release-tag.yml", state=state).startswith(
        "release-tag.yml: FAILING — at least 5 consecutive runs"
    )


def test_undecided_conclusions_neither_extend_nor_end_an_outage() -> None:
    """Cancelled, skipped and in-flight runs are IGNORED, not guessed at."""
    runs = [*_RED_STREAK, {"conclusion": "cancelled", "created_at": "2026-08-21T00:00:00Z"}]
    state = lane_state(runs=runs)
    assert state["healthy"] is False
    assert state["consecutive_failures"] == 5
    assert state["runs_considered"] == 6


def test_an_empty_history_is_healthy_and_says_it_considered_nothing() -> None:
    """No decided runs is not an outage."""
    state = lane_state(runs=[])
    assert state["healthy"] is True
    assert state["runs_considered"] == 0


def test_a_healthy_lane_is_silent() -> None:
    """A watcher that speaks on every run gets muted within a day."""
    assert notice_text(workflow="release-tag.yml", state=lane_state(runs=_RECOVERED)) == ""


def test_a_single_failure_is_below_the_threshold_and_stays_silent() -> None:
    """One failed cut is indistinguishable from a flake."""
    runs = [
        {"conclusion": "success", "created_at": "2026-08-16T10:00:00Z"},
        {"conclusion": "failure", "created_at": "2026-08-17T14:20:47Z"},
    ]
    state = lane_state(runs=runs)
    assert state["healthy"] is False
    assert notice_text(workflow="release-tag.yml", state=state) == ""
