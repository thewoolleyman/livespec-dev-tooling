"""The row-finding value, and the EXCLUSION DISPOSITION it carries.

Split out of `_context` — the fleet package's front door, which sat at the
250-LLOC hard ceiling with no room for the one field this concern needs. The
cut is a cohesion cut rather than a line-count cut: `_context` owns the GitHub
SEAM and the per-run memo caches, while what a finding IS and how a consumer
must DISPOSE of it is a vocabulary of its own, with its own constant and its own
constructor. `_context` imports the value back and keeps re-exporting it, so
every row module's existing `from ..._context import RowFinding` is unchanged.

WHY A FINDING CARRIES A CLASS AT ALL, which is the whole reason this module
exists. `SPECIFICATION/contracts.md` section "Pin-currency severity policy"
(v093) makes the release fan-out's per-member filter treat ONE kind of
error-severity finding differently from every other: a pin-currency STALENESS
finding stays error severity and is named in the run's summary, but it MUST NOT
exclude its member from the `sibling-released` dispatch matrix — because that
dispatch is the remedy for a stale pin, and the bump pull request it opens
supersedes any stuck one, so excluding the member removes the cure. Measured
2026-10-22: livespec-console-beads-fabro last received a dispatch on 10-15 and
was excluded from every fan-out after it by ONE `compat-pin-currency` row whose
remedy was the dispatch it was being excluded from.

⛔ THE DISPOSITION IS NOT DERIVABLE FROM THE ROW ID, and that is why it rides on
the FINDING. The same `compat-pin-currency` row fails for staleness (which must
not exclude) and for an unparseable pin file (which must, "because the bump
rewrite cannot be applied to a pin file that does not parse"). A filter keyed on
the row id gets exactly one of those two right, and which one it gets wrong is
the fail-OPEN direction: dispatching to a member whose pin file cannot be
rewritten produces a green bump PR that changed nothing.

⛔ AND IT IS NOT THE SEVERITY. Severity and disposition are ORTHOGONAL by
ratified text — the staleness finding keeps error severity precisely so it stays
loud — so encoding "do not exclude" as a third severity value would make one
field answer two questions and silently re-tier the finding on every surface
that renders severity.

The DEFAULT is the empty class, so every row that says nothing about its
disposition excludes. Fail-closed is the correct default here: a new row whose
author never considered the fan-out blocks its member rather than quietly
riding through it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "PIN_STALENESS_FINDING_CLASS",
    "RowFinding",
    "pin_staleness_finding",
]


# The one non-excluding class the contract ratifies: a finding of either
# staleness class (NEVER FIRED, or FIRED AND COULD NOT LAND) on any of the four
# pin-currency rows — `dev-tooling-pin`, `compat-pin-currency`,
# `uses-pin-currency`, `fabro-pin-currency`. A single name rather than one per
# class, because the fan-out's decision is identical for both and the contract
# words the exception as "a finding of either staleness class"; WHICH class
# applies is already in the finding's own message.
PIN_STALENESS_FINDING_CLASS = "pin-staleness"


@dataclass(frozen=True, kw_only=True)
class RowFinding:
    """The member definitively violates the obligation row."""

    message: str
    severity: str = "error"
    finding_class: str = ""


def pin_staleness_finding(*, message: str, severity: str) -> RowFinding:
    """A staleness-class finding — error-severity where it escalates, never excluding.

    A named constructor rather than the keyword at each of the four call sites
    (two pin-currency staleness branches, two dev-tooling-pin staleness
    branches). The four must agree, and the shape of their disagreement is
    invisible: a site that forgot the class emits an ordinary error finding, the
    filter excludes its member, and the member silently stops receiving the very
    dispatch that would cure it — which is the defect this whole concern
    corrects, reintroduced one row at a time.

    `severity` stays the CALLER's, because the lane scoping is theirs: the same
    staleness finding is an error only in the filter-consuming fan-out
    preflight and a warning in per-PR CI and the scheduled sweep. Defaulting it
    here would hard-wire one lane's answer into all three.
    """
    return RowFinding(
        message=message,
        severity=severity,
        finding_class=PIN_STALENESS_FINDING_CLASS,
    )
