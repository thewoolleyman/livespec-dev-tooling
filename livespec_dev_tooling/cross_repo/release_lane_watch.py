"""Detect a persistently failing release lane from its own run history.

LIFTED, NOT REIMPLEMENTED. The body below is `livespec-overseer`'s
`overseer/release_lane_watch.py` (its work-item `overseer-hgq4wi.15`), moved here
so every governed repo can watch its own release lanes through
`reusable-release-lane-watch.yml` instead of each re-deriving the detector. Every
property it guarantees was earned by a MEASUREMENT taken in that repo, so a
re-derivation would have to pay for them again; the work-item for this move is
`livespec-dev-tooling-37p0`.

WHY IT EXISTS. In `livespec-overseer` the release lane failed 139 of 157 runs
between 2026-07-26 and 2026-08-20 and nobody knew. One block ran 123 consecutive
failed cuts across SIXTEEN DAYS (2026-08-03 to 2026-08-19); both times it was
noticed, it was noticed by luck while tracing something else.

THREE PROPERTIES THIS MODULE EXISTS TO GUARANTEE, each earned by a measurement
rather than chosen for tidiness:

- IT REPORTS STATE, NOT EDGES. At an 88.5% failure rate a transition-triggered
  alert fires three times in a month and is silent through the rest, because
  most of the lane's life IS the failure. So the answer is always "currently
  failing, N cuts, since T" rather than "it just broke".

- IT CARRIES THE ABSOLUTE LAST-GREEN TIMESTAMP. On this lane the last green can
  be sixteen days back. "failing since 2026-08-03T03:38:02Z" is actionable;
  "123 failures" invites the reader to assume recency and is not.

- IT KNOWS WHEN ITS OWN INPUT IS TRUNCATED. A failure block flush against the
  oldest run supplied is a LOWER BOUND, not a count: the same real block reads
  as 4 cuts at limit 20, 84 at limit 100 and 123 at limit 300. A caller that
  cannot see a green above the block has not measured its extent, and this
  module says so instead of reporting the short number as fact.

The lane state is a pure function of the run history, so the forge call lives
entirely in the caller (`release_lane_watch_runner`) and no network reaches the
enforcement aggregate.
"""

from __future__ import annotations

__all__: list[str] = ["lane_state", "notice_text"]

_SUCCESS = "success"
_FAILURE = "failure"

# A SINGLE failed cut is indistinguishable from a flake and must stay silent: a
# watcher that cries wolf on one transient is muted within a day, and the fleet's
# history records that outcome for gates that fire for the wrong reason. TWO
# consecutive means the lane did not recover on its own next cut, which is the
# cheapest evidence that something is actually wrong. Every measured block behind
# this module was far above it -- 7, 123 and 9 cuts -- so the threshold
# discriminates the transient without weakening detection of anything real.
_MIN_CONSECUTIVE = 2


def lane_state(*, runs: list[dict[str, str]]) -> dict[str, object]:
    """Summarise the newest run block, oldest-first or newest-first accepted.

    `runs` carries one mapping per run with a `conclusion` and a `created_at`.
    Conclusions other than success or failure (cancelled, skipped, a run still
    in flight) are IGNORED rather than treated as either: counting them as
    failures would inflate an outage and counting them as successes would end
    one that is still running.
    """
    decided = [
        r for r in runs if r.get("conclusion") in (_SUCCESS, _FAILURE) and r.get("created_at")
    ]
    ordered = sorted(decided, key=lambda r: str(r.get("created_at")))
    if not ordered:
        return {
            "healthy": True,
            "consecutive_failures": 0,
            "failing_since": None,
            "last_green": None,
            "truncated": False,
            "runs_considered": 0,
        }

    trailing: list[dict[str, str]] = []
    for run in reversed(ordered):
        if run.get("conclusion") != _FAILURE:
            break
        trailing.append(run)
    trailing.reverse()

    if not trailing:
        return {
            "healthy": True,
            "consecutive_failures": 0,
            "failing_since": None,
            "last_green": str(ordered[-1].get("created_at")),
            "truncated": False,
            "runs_considered": len(ordered),
        }

    green_above = ordered[: len(ordered) - len(trailing)]
    return {
        "healthy": False,
        "consecutive_failures": len(trailing),
        "failing_since": str(trailing[0].get("created_at")),
        "last_green": str(green_above[-1].get("created_at")) if green_above else None,
        "truncated": not green_above,
        "runs_considered": len(ordered),
    }


def notice_text(
    *, workflow: str, state: dict[str, object], min_consecutive: int = _MIN_CONSECUTIVE
) -> str:
    """Render the operator-facing line, or an empty string when healthy.

    A HEALTHY LANE IS SILENT. A watcher that speaks on every run is muted within
    a day, and the fleet's history records that outcome for gates that fire for
    the wrong reason.
    """
    if state.get("healthy"):
        return ""
    count = state.get("consecutive_failures")
    if isinstance(count, int) and count < min_consecutive:
        return ""
    since = state.get("failing_since")
    last_green = state.get("last_green")
    bound = "at least " if state.get("truncated") else ""
    tail = (
        f"last green {last_green}"
        if last_green
        else "NO GREEN in the history supplied — widen the query until one appears"
    )
    return f"{workflow}: FAILING — {bound}{count} consecutive runs since {since}; {tail}"
