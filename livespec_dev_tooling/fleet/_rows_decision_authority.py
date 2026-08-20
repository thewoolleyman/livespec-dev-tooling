"""Decision-authority AGENTS.md obligation row — AUTHORED, SHIPPED DISARMED.

Every governed fleet member should tell its sessions what they are allowed to
decide. `AGENTS.md` is authored per repo and nothing propagates it, so the
guidance drifted: measured on 2026-08-20 it was real in part of the fleet and
absent from the rest, and the sessions in the rest were reading a file that
never told them. The measured cost was a track parked roughly sixteen hours on
a picker whose option 1 was its own recorded next action.

THIS ROW IS DELIBERATELY NOT REGISTERED IN `OBLIGATION_ROWS`. Registering it
is what ARMS it, and arming is a separate work-item that lands only after
every governed member has adopted the section. The precedent is expensive: the
Railway decoupling landed in `46c5dab`, turned five repos red, and was reverted
in `f4247110`; `plan/rop-railway-enforcement/` carries the standing constraint
"Do not arm the check anywhere" for exactly this reason. A check armed before
the repos it judges have adopted the shape writes verdicts into a fleet that
cannot satisfy them.

THE INSTRUMENT IS A PRESENCE TEST AND JUDGES NO PROSE. Three markers must all
appear in the member's `AGENTS.md`, read at the member's canonical ref through
the contents API — the remote default branch, never a working tree.

The markers are matched CASE-FOLDED and with WHITESPACE RUNS NORMALIZED, which
is a correctness fix rather than a loosening. A literal byte-for-byte test was
measured on 2026-08-20 against all ten governed members and scored every one of
them an offender — `livespec-dev-tooling` included, the repo that authored the
guidance. Two causes, both incidental to whether the prose is present:

- CASE. The canonical heading is "## Decision authority — when to ask, proceed,
  or self-resolve", lowercasing "when" because the marker sits mid-sentence
  after a dash. Demanding a capital there would be prose judgment by the back
  door — it forces awkward capitalization to satisfy a grep.
- LINE WRAPPING. An 80-column citation of the first marker wraps as
  ("When to ask,\nproceed, or self-resolve"). The marker is plainly present to
  a reader and absent to a substring test.

Per the fleet's can't-read-is-not-absent discipline, a member whose `AGENTS.md`
is unreadable yields a skip, never a false finding. A finding names the member
and every marker it is missing.
"""

from __future__ import annotations

import re

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)

__all__: list[str] = [
    "AGENTS_PATH",
    "DECISION_AUTHORITY_MARKERS",
    "assert_decision_authority_section",
    "missing_decision_authority_markers",
]

AGENTS_PATH = "AGENTS.md"

# The three markers, ALL of which must be present. Ordered as a reader meets
# them: the question the section answers, the rule that costs the most when
# absent, and the section's own name.
DECISION_AUTHORITY_MARKERS: tuple[str, ...] = (
    "When to ask, proceed, or self-resolve",
    "do not over-ask",
    "Decision authority",
)

_WHITESPACE_RUN = re.compile(r"\s+")


def _comparable(*, text: str) -> str:
    """`text` reduced to what the presence test actually compares.

    Whitespace runs — newlines included, which is the point — collapse to one
    space, then the result case-folds. Applied to BOTH sides so a marker and
    the file it is sought in are normalized identically.
    """
    return _WHITESPACE_RUN.sub(" ", text).casefold()


def missing_decision_authority_markers(*, agents_text: str) -> tuple[str, ...]:
    """The markers `agents_text` does not carry, in declaration order.

    Empty means the member carries the section. The markers are returned in
    their canonical spelling rather than their normalized form, because the
    tuple is read by a human deciding what to add.
    """
    haystack = _comparable(text=agents_text)
    return tuple(
        marker for marker in DECISION_AUTHORITY_MARKERS if _comparable(text=marker) not in haystack
    )


def assert_decision_authority_section(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member's `AGENTS.md` carries a decision-authority section.

    Skips a member whose `AGENTS.md` is unreadable or absent (can't-read is
    not absent). A finding names the member and every missing marker.
    """
    agents = ctx.file_text(repo=member.repo, path=AGENTS_PATH)
    if agents is None:
        return RowSkip(reason=f"{member.repo}: {AGENTS_PATH} unreadable or absent")
    missing = missing_decision_authority_markers(agents_text=agents)
    if missing:
        return RowFinding(
            message=(
                f"{member.repo}: {AGENTS_PATH} carries no decision-authority section — "
                f"missing {', '.join(missing)}"
            )
        )
    return RowPass()
