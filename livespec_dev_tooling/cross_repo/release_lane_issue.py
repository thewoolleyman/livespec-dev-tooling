"""Decide what to do with a repo's ONE durable `release-lane-red` issue.

The producer half of the release-lane loop. The reader already exists — the
one-call needs-attention screen reads each repo's OPEN issue labelled
`release-lane-red` — and until this module landed nothing wrote those issues, so
the screen showed a permanently-empty signal that was indistinguishable from a
fleet with no red lanes at all.

WHY AN ISSUE AND NOT AN ANNOTATION. The sibling `release_lane_watch` reports
lane state as an EXIT CODE, which the run that produced it carries and nothing
else does: reading it means knowing which workflow to open. An issue is DURABLE
and QUERYABLE from outside the run, which is the only shape a one-call screen can
consume.

ONE ISSUE PER REPO, REUSED. A watcher that opens a fresh issue per red run
produces one issue per cut — 123 of them on the outage that motivated the
sibling — and a screen counting open issues then reports the length of the
outage as its severity. So the decision below is a STATE TRANSITION over the
repo's single issue (open it, keep it current, close it) rather than an event
emitter.

CLOSING IS THE DANGEROUS DIRECTION, and it is the reason this decision is a pure
function taking `red_notices` rather than a lane verdict. A closed issue reads as
RECOVERED on the screen. An unmeasurable lane has not recovered — it has stopped
being observed — so the caller folds its cannot-measure notices into
`red_notices` alongside the failing ones, and the only input that can produce a
CLOSE is an EMPTY notice list: every watched lane measured, and every one
measured green. There is no other route to the recovered state, which is what
makes "an unmeasurable lane never reads as recovered" a property of the
transition table instead of a rule the caller has to remember.

No I/O reaches this module, so the whole transition table is replay-testable.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "ACTION_CLOSE",
    "ACTION_NOOP",
    "ACTION_OPEN",
    "ACTION_UPDATE",
    "ISSUE_LABEL",
    "ISSUE_TITLE",
    "IssueAction",
    "issue_action",
    "issue_body",
]

# The label the one-call needs-attention screen queries on. It is the JOIN
# between this producer and that reader: renaming it here silently empties the
# screen, because a query for a label nothing carries returns no rows rather
# than an error.
ISSUE_LABEL = "release-lane-red"
ISSUE_TITLE = "Release lane red"

ACTION_OPEN = "open"
ACTION_UPDATE = "update"
ACTION_CLOSE = "close"
ACTION_NOOP = "noop"

_PREAMBLE = (
    "This issue is written, kept current, and closed by the release-lane "
    "watcher. It stays open while any watched release lane is red or "
    "unmeasurable, and closes by itself once every watched lane measures "
    "green. Closing it by hand does not fix a lane -- the next watcher run "
    "reopens it. An UNMEASURABLE lane is listed here too, and never closes "
    "the issue: a lane that stopped being observed has not recovered."
)


@dataclass(frozen=True, kw_only=True)
class IssueAction:
    """One transition over the repo's single `release-lane-red` issue.

    `kind` is one of the four `ACTION_*` constants. `issue_number` is the
    existing issue the transition acts on, and is `None` exactly for the two
    kinds that have no existing issue to act on (`ACTION_OPEN`, `ACTION_NOOP`).
    `body` is the rendered issue body, and is `None` for the two kinds that
    write no body (`ACTION_CLOSE`, `ACTION_NOOP`).
    """

    kind: str
    issue_number: int | None
    body: str | None


def issue_body(*, red_notices: list[str]) -> str:
    """Render the issue body from the red lanes' notice lines.

    Each notice is the sibling `notice_text` line for one lane, already
    carrying its cut count, its failing-since timestamp and its last green --
    so the body is actionable on its own, without opening the run that wrote
    it. Cannot-measure lanes are rendered by the same mechanism, because a
    reader who has to tell "red" from "unobserved" apart needs BOTH lines in
    the same list.
    """
    lines = [_PREAMBLE, "", "Currently red or unmeasurable:", ""]
    lines.extend(f"- {notice}" for notice in red_notices)
    return "\n".join(lines)


def issue_action(*, red_notices: list[str], open_issue_number: int | None) -> IssueAction:
    """Choose the transition for this run, from the notices and the open issue.

    The table is total over the two inputs, and CLOSE is reachable only from an
    empty `red_notices` -- see this module's docstring for why that is the
    load-bearing property rather than an implementation detail.
    """
    if red_notices:
        body = issue_body(red_notices=red_notices)
        if open_issue_number is None:
            return IssueAction(kind=ACTION_OPEN, issue_number=None, body=body)
        return IssueAction(kind=ACTION_UPDATE, issue_number=open_issue_number, body=body)
    if open_issue_number is None:
        return IssueAction(kind=ACTION_NOOP, issue_number=None, body=None)
    return IssueAction(kind=ACTION_CLOSE, issue_number=open_issue_number, body=None)
