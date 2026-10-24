"""The pure three-way partition of the release-dispatch sibling matrix.

Split out of `dispatch_matrix_filter`, which is a PROCESS ENTRY POINT: its
`main()` owns the two JSON reads, the three JSON writes and the `::warning::`
workflow commands the Actions runner parses from stdout, while the decision
itself touches nothing. Separating them along that seam is what keeps the entry
module under the 250-LLOC hard ceiling when the partition grew its third
outcome, and it leaves the decision testable with no filesystem at all.

THE THIRD OUTCOME is `retained`, added by `SPECIFICATION/contracts.md` section
"Pin-currency severity policy" (v093): a member whose only error-severity
findings are pin-currency STALENESS findings stays in the dispatch matrix and is
still NAMED. It is neither of the other two and must not be folded into either.
Folded into `filtered` it would vanish from every summary — the
`livespec-bmxs` silent-omission hazard, now reached from the other side. Folded
into `excluded` it would keep the member out of the dispatch that is the remedy
for its stale pin, which is the defect the clause corrects.

The failure track stays reserved for STRUCTURAL problems that must keep the
preflight job red: a malformed entry, or a discovered sibling with no verdict
entry at all (manifest/verdict drift). An excluded member is not a failure —
excluding it is the filter working — and a retained member is not one either.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "Exclusion",
    "FilterError",
    "FilterOutcome",
    "MemberVerdictRows",
    "RetainedFinding",
    "filter_siblings",
]


@dataclass(frozen=True, kw_only=True)
class Exclusion:
    """One sibling excluded from the dispatch matrix, with its failing rows."""

    member: str
    failing_rows: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class RetainedFinding:
    """One sibling KEPT in the dispatch matrix whose error findings are still named.

    `failing_rows` is EVERY error-severity row of that member, not just the
    non-excluding ones — the contract has the preflight's summary "name every
    error finding per member", and a member retained over one finding has by
    construction no other kind.
    """

    member: str
    failing_rows: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class MemberVerdictRows:
    """One member's two row sets, already validated out of the verdict artifact."""

    failing_rows: tuple[str, ...]
    non_excluding_rows: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class FilterOutcome:
    """The filtered matrix plus both loud dispositions of the findings behind it."""

    filtered: tuple[dict[str, str], ...]
    excluded: tuple[Exclusion, ...]
    retained: tuple[RetainedFinding, ...]


@dataclass(frozen=True, kw_only=True)
class FilterError:
    """A structural failure that must keep the preflight job red."""

    reason: str


def filter_siblings(
    *,
    siblings: list[dict[str, str]],
    verdicts: list[dict[str, object]],
) -> Result[FilterOutcome, FilterError]:
    """Partition the sibling set by conformance verdict, preserving order.

    Every sibling MUST have a verdict entry (the artifact covers every
    manifest member and the sibling set is a subset); a missing entry is
    manifest/verdict drift and fails with `FilterError` rather than
    guessing (fail-closed).

    Note what is NOT a failure: an EXCLUDED member, and a RETAINED one. Both
    ride the success track, because both are the filter working as designed.
    The failure track is reserved for STRUCTURAL problems — malformed entries
    and manifest/verdict drift. Collapsing the two would turn a routine
    exclusion into a red job and re-create the gate this filter replaced.
    """
    parsed = _verdict_rows_by_member(verdicts=verdicts)
    if isinstance(parsed, Failure):
        return Failure(parsed.failure())
    verdict_by_member = parsed.unwrap()
    filtered: list[dict[str, str]] = []
    excluded: list[Exclusion] = []
    retained: list[RetainedFinding] = []
    for sibling in siblings:
        name = sibling.get("name")
        if not isinstance(name, str) or not name:
            return Failure(FilterError(reason=f"malformed sibling entry: {sibling!r}"))
        if name not in verdict_by_member:
            return Failure(
                FilterError(reason=f"sibling {name} has no verdict entry (manifest/verdict drift)")
            )
        rows = verdict_by_member[name]
        _place(name=name, rows=rows, filtered=filtered, excluded=excluded, retained=retained)
    return Success(
        FilterOutcome(filtered=tuple(filtered), excluded=tuple(excluded), retained=tuple(retained))
    )


def _place(
    *,
    name: str,
    rows: MemberVerdictRows,
    filtered: list[dict[str, str]],
    excluded: list[Exclusion],
    retained: list[RetainedFinding],
) -> None:
    """Put one sibling in exactly one of the three buckets.

    A member is excluded by its EXCLUDING rows — every error row the verdict did
    not mark non-excluding. "Only error findings are stale pins" is load-bearing
    in the scenario this implements: one can't-parse finding beside a staleness
    finding still excludes, because the staleness finding does not shelter it.
    """
    if not rows.failing_rows:
        filtered.append({"name": name})
        return
    if set(rows.failing_rows) - set(rows.non_excluding_rows):
        excluded.append(Exclusion(member=name, failing_rows=rows.failing_rows))
        return
    filtered.append({"name": name})
    retained.append(RetainedFinding(member=name, failing_rows=rows.failing_rows))


def _verdict_rows_by_member(
    *, verdicts: list[dict[str, object]]
) -> Result[dict[str, MemberVerdictRows], FilterError]:
    """Validate the verdict artifact into per-member row sets, or fail closed."""
    by_member: dict[str, MemberVerdictRows] = {}
    for verdict in verdicts:
        member = verdict.get("member")
        conformant = verdict.get("conformant")
        if not isinstance(member, str) or not isinstance(conformant, bool):
            return Failure(FilterError(reason=f"malformed verdict entry: {verdict!r}"))
        failing = _row_names(member=member, key="failing_rows", value=verdict.get("failing_rows"))
        if isinstance(failing, Failure):
            return Failure(failing.failure())
        # An ABSENT key reads as the empty set, not as a malformed verdict: the
        # artifact is produced by a PINNED release of this package, so a
        # preflight running an older emitter must still filter rather than red
        # the fan-out — and empty is the fail-closed reading, under which every
        # failing row excludes exactly as it did before this subset existed.
        non_excluding = _row_names(
            member=member, key="non_excluding_rows", value=verdict.get("non_excluding_rows", [])
        )
        if isinstance(non_excluding, Failure):
            return Failure(non_excluding.failure())
        by_member[member] = MemberVerdictRows(
            failing_rows=failing.unwrap(), non_excluding_rows=non_excluding.unwrap()
        )
    return Success(by_member)


def _row_names(*, member: str, key: str, value: object) -> Result[tuple[str, ...], FilterError]:
    """One verdict field as a tuple of row names, or why it is not one."""
    if not isinstance(value, list):
        return Failure(FilterError(reason=f"malformed {key} for member {member}"))
    items = cast("list[object]", value)
    rows = tuple(row for row in items if isinstance(row, str))
    if len(rows) != len(items):
        return Failure(FilterError(reason=f"non-string failing row in {key} for member {member}"))
    return Success(rows)
