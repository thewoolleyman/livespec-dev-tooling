"""_row_outcome — the three answers an obligation row can give, and their vocabulary.

Split out of `_context.py` to keep that file under the 250-LLOC hard ceiling,
along a cohesion seam rather than an arbitrary cut: `_context.py` owns the
GITHUB-ACCESS SEAM every row reads the world through, while this module owns
the VALUE LANGUAGE every row answers in. The two concerns share no state — a
row outcome knows nothing about `gh`, and the context never constructs one —
so the only coupling is the import direction, and it runs one way.

`_context.py` re-exports every name here, exactly as it already re-exports
`GhResult`, `ReadFailure`, `SnapshotResult` and `TreeState` from their own
private siblings. It is the fleet package's front door by design (its own
docstring says so), so a row module keeps importing `RowFinding` from
`_context` and nothing about the existing call sites moves.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "EXCLUDED_NOTE_PREFIX",
    "PIN_STALENESS_FINDING_CLASS",
    "RowFinding",
    "RowOutcome",
    "RowPass",
    "RowSkip",
    "row_excluded",
]


@dataclass(frozen=True, kw_only=True)
class RowPass:
    """The member satisfies the obligation row."""

    note: str = ""


# The finding CLASS carried by the two ratified pin-currency staleness classes
# — NEVER FIRED and FIRED-AND-COULD-NOT-LAND (`SPECIFICATION/contracts.md`
# section "Pin-currency severity policy"). It exists because severity alone
# cannot answer the fan-out's question: a stale pin and an unparseable pin file
# are BOTH error-severity findings on the SAME `compat-pin-currency` row, and
# they have OPPOSITE dispatch consequences — the stale one must still be
# dispatched to, because the bump PR the dispatch opens is its remedy, while
# the unparseable one must be excluded, because no bump rewrite can be applied
# to a file that does not parse. The row id is therefore not a usable proxy,
# and the class travels with the finding instead.
PIN_STALENESS_FINDING_CLASS = "pin-staleness"


@dataclass(frozen=True, kw_only=True)
class RowFinding:
    """The member definitively violates the obligation row.

    `finding_class` is EMPTY for an ordinary obligation finding and carries
    `PIN_STALENESS_FINDING_CLASS` for one of the two ratified staleness
    classes. Defaulting to empty is the fail-closed spelling: a finding that
    does not declare itself a staleness finding keeps the exclusion behavior
    every row had before the class existed.
    """

    message: str
    severity: str = "error"
    finding_class: str = ""


@dataclass(frozen=True, kw_only=True)
class RowSkip:
    """The row could not be definitively evaluated (can't-read is not absent)."""

    reason: str


RowOutcome = RowPass | RowFinding | RowSkip

# The note prefix that marks a RowPass as INAPPLICABLE rather than satisfied.
# It lives here, beside the union, rather than privately in `_lanes.py`: a row
# module cannot import `_lanes` (that is an import cycle through
# `_contract_rows`), and both engines must render the same value the same way.
EXCLUDED_NOTE_PREFIX = "excluded-with-reason: "


def row_excluded(*, reason: str) -> RowPass:
    """The row does not APPLY to this member — a definitive non-obligation.

    ⛔ NOT `RowSkip`. `RowSkip` means the row could not be EVALUATED, and the
    central lane feeds every one of them into `blind_rows`, which fails the run
    with no lever and no opt-out. Spelling inapplicability as a skip therefore
    reds master fleet-wide the moment the applicable population reaches zero —
    for a condition that is not a failure at all.

    A constructor rather than a bare prefix so the correct spelling is a NAME
    both engines share, not a string concatenation each call site re-derives.
    """
    return RowPass(note=f"{EXCLUDED_NOTE_PREFIX}{reason}")
