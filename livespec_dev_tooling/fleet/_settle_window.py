"""_settle_window — the NEVER-FIRED staleness class and the window that arms it.

`SPECIFICATION/contracts.md` section "Pin-currency severity policy"
partitions a STALE pin into exactly two classes and calls the partition
EXHAUSTIVE, "because a bump PR for the latest release either is open or
is not". Until v039 the code implemented only the milder half —
FIRED-AND-COULD-NOT-LAND, stale WITH an open bump PR — so the WORSE
state, stale with NO bump PR at all, could never enter the escalating
class whatever severity that class carried. Two fan-out outages (one of
seven hours, one of sixteen) ran in exactly that state, with every
pin-currency row firing correctly and nothing stopping.

This is a SIBLING module of both persisting-gap sites rather than a copy
inside either, because the contract requires the two to move together:
`_rows_files`'s own comment already says "both persisting-gap sites must
move together or the promotion is half-armed", and a second two-hour
window is how they drift apart.

THE WINDOW IS A RATIFIED CONSTANT. Nothing here reads an environment
variable, a flag, a config key, or a per-member exemption that
lengthens, shortens, or disables it — "a settable window is a severity
lever wearing a different name". The age comes from `published_at` on
the SAME `repos/<owner>/<repo>/releases/latest` payload both readers
already fetch for `tag_name`, so the predicate costs no additional API
call and is STATELESS: per-PR CI, the scheduled central sweep, and the
fan-out preflight derive the same verdict from the same bytes, with no
local-clock reading of when staleness was FIRST OBSERVED and no stored
history.

A can't-READ never escalates (`livespec-dev-tooling-6ge`). An absent,
malformed, or timezone-less `published_at` leaves the row at its lower
severity rather than assuming the release is old enough — the class is
still NEVER FIRED (the PR list WAS read), only its age is unknown, and
the clause says so instead of claiming a window it could not apply.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import cast

from livespec_dev_tooling.fleet._context import FleetContext

__all__: list[str] = [
    "SETTLE_WINDOW",
    "LatestRelease",
    "NeverFired",
    "never_fired_class",
    "read_latest_release",
    "utc_now",
]


SETTLE_WINDOW = timedelta(hours=2)
_SETTLE_WINDOW_LABEL = f"{int(SETTLE_WINDOW.total_seconds() // 3600)}h"


@dataclass(frozen=True, kw_only=True)
class LatestRelease:
    """A source repo's latest release: the tag, and when it published.

    Both fields come off ONE `releases/latest` payload. `published_at`
    was in hand and discarded at both read sites before v039 — the
    `unrecognized`-sentinel shape — which is why the settle window
    needed no new API call to become computable.
    """

    tag: str
    published_at: str | None


@dataclass(frozen=True, kw_only=True)
class NeverFired:
    """The NEVER-FIRED verdict for one stale pin: whether it escalates, and why.

    `escalates` is the CONDITION, never the severity: the caller still
    applies the ratified lane scoping (error only where the
    dispatch-matrix filter consumes per-member verdicts), so this class
    widens which conditions reach that scoping and moves no severity.
    """

    escalates: bool
    clause: str


def utc_now() -> datetime:
    """This instant in UTC — the only clock reading the predicate makes.

    It answers "how old is the release", never "when did I first see
    this pin go stale". The distinction is what keeps the predicate
    stateless: the same payload evaluated in any context yields the same
    verdict, so no evaluating lane needs stored history to agree.
    """
    return datetime.now(tz=timezone.utc)


def read_latest_release(*, ctx: FleetContext, repo: str) -> LatestRelease | None:
    """`repo`'s latest release, or None when the payload is unreadable or tagless.

    ONE reader for both persisting-gap sites, replacing the two private
    tag-only readers that fetched this payload and kept one field each.
    None keeps its established meaning at both call sites — freshness
    unverified, never a violation.
    """
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{repo}/releases/latest")
    if not isinstance(payload, dict):
        return None
    fields = cast("dict[str, object]", payload)
    tag = fields.get("tag_name")
    if not isinstance(tag, str):
        return None
    published_at = fields.get("published_at")
    return LatestRelease(
        tag=tag, published_at=published_at if isinstance(published_at, str) else None
    )


def never_fired_class(*, published_at: str | None, now: datetime) -> NeverFired:
    """The verdict for a stale pin whose bump PR was never opened.

    Escalates only when the release is READABLY older than the settle
    window. The clause names the class either way, so the diagnostic
    still tells an operator WHICH of the two states applies rather than
    reporting bare staleness.
    """
    instant = _published_instant(published_at=published_at)
    if instant is None:
        return NeverFired(
            escalates=False,
            clause=(
                "NEVER FIRED: no bump PR for the latest release is open, and the "
                "release's publish time is unreadable, so the "
                f"{_SETTLE_WINDOW_LABEL} settle window cannot be applied"
            ),
        )
    age = now - instant
    return NeverFired(
        escalates=age > SETTLE_WINDOW,
        clause=(
            "NEVER FIRED: no bump PR for the latest release is open; it published at "
            f"{published_at}, {_rendered_age(age=age)} ago "
            f"({_SETTLE_WINDOW_LABEL} settle window)"
        ),
    )


def _published_instant(*, published_at: str | None) -> datetime | None:
    """The publish instant, or None when it cannot be read as one.

    A timezone-LESS timestamp is refused rather than assumed UTC: the
    assumption would silently shift the window by the offset it guessed,
    and guessing in the escalating direction is the one thing the
    can't-read principle forbids.
    """
    if published_at is None:
        return None
    try:
        parsed = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return None if parsed.tzinfo is None else parsed


def _rendered_age(*, age: timedelta) -> str:
    """The release's age as `<hours>h<minutes>m`, for the operator-facing clause."""
    whole_minutes = int(age.total_seconds() // 60)
    return f"{whole_minutes // 60}h{whole_minutes % 60:02d}m"
