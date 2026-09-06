"""WHY a fleet row could not read its source, told apart by remedy.

`_read_failure.classify_gh_failure` has always distinguished `rate_limited`
from `forbidden`. Nothing downstream READ that distinction: a row that could
not answer became a `RowSkip` carrying prose, and the blind-row summary and
the run verdict reported only that the row "enforced NOTHING this run". So a
throttled read and a genuine permission gap rendered identically, and they
want OPPOSITE responses — retry-later versus an admin action.

That is not a hypothetical confusion. `livespec-dev-tooling-mmqe` was FILED as
a credential/vantage gap ("members unreadable to the CI credential ... needs a
GitHub App installation fix, an admin action outside any PR"), by an agent
holding the failing log. Direct measurement refuted it: the installation could
see all nine members and its primary pool read `limit=5000`. The information
that would have settled it was already in the run — one field down, discarded
by the summary.

This module is that field. It projects a run's preserved `ReadFailure` causes
into structured log fields naming the CLASS and its remedy, so the per-member
row and the overall verdict both state which of the two happened instead of
leaving a reader to infer it from a status code both share (GitHub answers a
throttle with HTTP 403, the same status as a permission denial).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_dev_tooling.fleet._read_failure import ReadFailure

__all__: list[str] = [
    "PERMISSION_DENIED_KIND",
    "RATE_LIMITED_KIND",
    "cause_fields",
]

# The two `classify_gh_failure` kinds this module exists to keep apart. They
# are spelled here as names rather than inlined at each comparison so the pair
# reads as one decision.
RATE_LIMITED_KIND = "rate_limited"
PERMISSION_DENIED_KIND = "forbidden"

_THROTTLED = "rate-limited"
_DENIED = "permission-denied"
_BOTH = "rate-limited-and-permission-denied"
_OTHER = "other-read-failure"
_NONE = "no-failed-read"

# The remedy is carried WITH the class, because the class alone still leaves
# the reader to know that a throttle clears on GitHub's clock while a denial
# never does. Every one of the four falsified models recorded on
# `livespec-dev-tooling-mmqe` chose the wrong remedy, not the wrong words.
_REMEDIES: dict[str, str] = {
    _THROTTLED: (
        "GitHub THROTTLED these reads (HTTP 403/429 'API rate limit exceeded'). "
        "This is NOT a permission gap and no admin action helps: the traversal "
        "must slow down, and a retry is worth spending only after the stated "
        "window"
    ),
    _DENIED: (
        "GitHub REFUSED these reads for the running credential (403/404 'not "
        "accessible'). This is NOT a throttle and retrying cannot clear it: the "
        "credential needs the missing scope or installation access"
    ),
    _BOTH: (
        "BOTH a throttled read and a permission-denied read occurred in this "
        "scope. They have opposite remedies, so read the per-row "
        "`read_failure_kinds` before choosing between slowing down and an admin "
        "action"
    ),
    _OTHER: (
        "no throttled and no permission-denied read was recorded in this scope; "
        "read `read_failure_kinds` for what did fail"
    ),
    _NONE: "no read failed in this scope",
}

# A member name must match a whole path SEGMENT. `livespec` is a PREFIX of
# `livespec-dev-tooling`, `livespec-driver-codex` and six more, so a substring
# test would attribute the manifest read — which every run makes against
# `livespec` — to every member whose name it happens to start.
_PATH_SEGMENTS = re.compile(r"[/:?&=]+")


def _scoped(*, failures: Sequence[ReadFailure], member: str | None) -> tuple[ReadFailure, ...]:
    """The failures belonging to `member`, or all of them when `member` is None."""
    if member is None:
        return tuple(failures)
    return tuple(failure for failure in failures if member in _PATH_SEGMENTS.split(failure.path))


def _cause_class(*, throttled: int, denied: int, total: int) -> str:
    """Name the class a reader must act on, refusing to collapse a mixed scope."""
    if throttled and denied:
        return _BOTH
    if throttled:
        return _THROTTLED
    if denied:
        return _DENIED
    if total:
        return _OTHER
    return _NONE


def cause_fields(
    *, failures: Sequence[ReadFailure], member: str | None = None
) -> dict[str, object]:
    """Structured log fields naming WHY reads failed in this scope.

    Emitted with `**` into an existing log call, so a row or a verdict gains
    the distinction without gaining a second record to correlate. The keys are
    always the same five, present even when nothing failed: a consumer reading
    `rate_limited_reads` must be able to tell "zero" from "this run does not
    report it", and an absent key cannot say the first.

    Pass `member` to scope the answer to one repository (the per-member row);
    omit it for the run-wide verdict.
    """
    scoped = _scoped(failures=failures, member=member)
    throttled = sum(1 for failure in scoped if failure.kind == RATE_LIMITED_KIND)
    denied = sum(1 for failure in scoped if failure.kind == PERMISSION_DENIED_KIND)
    cause = _cause_class(throttled=throttled, denied=denied, total=len(scoped))
    return {
        "read_failure_kinds": tuple(dict.fromkeys(failure.kind for failure in scoped)),
        "rate_limited_reads": throttled,
        "permission_denied_reads": denied,
        "read_failure_cause": cause,
        "read_failure_remedy": _REMEDIES[cause],
    }
