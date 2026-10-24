"""Filter the release-dispatch sibling matrix by per-member conformance verdicts.

Authority: livespec core work-item `livespec-f73t`, Slice 2b of the
maintainer-approved cut — the fan-out's fleet-conformance preflight
becomes a FILTER on the sibling set instead of a GATE on the whole
dispatch job. One member failing conformance must not prevent dispatch
to conformant members (criterion 1); the non-conformant member is
EXCLUDED from the matrix, not dispatched-and-failed (criterion 2);
every excluded member is named loudly with its failing rows
(criterion 3 — the `livespec-bmxs` silent-omission hazard); the
preflight stays BLOCKING for the members it covers — exclusion IS the
per-member blocking — and structural failures stay job-red with no
lever, no warn-only mode, no bypass (criterion 5).

STALENESS DOES NOT EXCLUDE (`SPECIFICATION/contracts.md` section
"Pin-currency severity policy", v093). A finding of either ratified
pin-currency staleness class stays error severity and is NAMED in the
run's summary, but MUST NOT take its member out of the matrix: the
`sibling-released` dispatch is the REMEDY for a stale pin, because the
bump pull request it opens supersedes any stuck one, so excluding the
member withholds the cure for the very condition it was excluded for.
Measured 2026-10-22 — livespec-console-beads-fabro received no dispatch
from any source for a week over one such row. The distinction cannot be
made from the row ID: a stale pin and an UNPARSEABLE pin file are both
error findings on the same `compat-pin-currency` row and have opposite
consequences, so the verdict artifact carries the staleness CLASS and
this filter reads it.

Inputs are the two artifacts `reusable-release-dispatch.yml` already
has in hand: the per-member verdict artifact
`fleet_conformance --emit-member-verdicts` writes
(`[{member, conformant, failing_rows, staleness_rows}]`) and the
discovered sibling matrix (`[{name}]`). Fail-closed rules: an unreadable or unparseable
input, a malformed entry, or a sibling with NO verdict entry
(manifest/verdict drift) exits 1 so the preflight job stays red — the
filter path engages only on a well-formed artifact. A verdict for a
member outside the sibling set (the publishing repo, excluded from the
fan-out) is surplus and ignored.

Output discipline matches sibling checks: structlog JSON to stderr.
The one deliberate stdout emission is the GitHub annotation line per
NAMED member — the Actions runner parses workflow commands from stdout,
and the caller captures nothing from stdout (both result payloads go to
explicit `--*-out` files).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.result import Failure, Result, Success  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "Exclusion",
    "FilterError",
    "FilterOutcome",
    "NamedFindings",
    "filter_siblings",
    "main",
]


@dataclass(frozen=True, kw_only=True)
class Exclusion:
    """One sibling excluded from the dispatch matrix, with its failing rows."""

    member: str
    failing_rows: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class NamedFindings:
    """One sibling KEPT in the matrix whose error findings are still named.

    ⛔ NOT an `Exclusion`. The member IS dispatched to; what it earns is a
    line in the run's summary naming the staleness findings that did not
    exclude it. Spelling it as an exclusion would make the two
    indistinguishable in the artifact, which is the `livespec-bmxs`
    silent-omission hazard wearing the opposite face: a reader could no
    longer tell a named keep from a withheld dispatch.
    """

    member: str
    failing_rows: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class FilterOutcome:
    """The filtered matrix, the loud exclusion list, and the loud keep list."""

    filtered: tuple[dict[str, str], ...]
    excluded: tuple[Exclusion, ...]
    named: tuple[NamedFindings, ...] = ()


@dataclass(frozen=True, kw_only=True)
class FilterError:
    """A structural failure that must keep the preflight job red."""

    reason: str


@dataclass(frozen=True, kw_only=True)
class _Verdict:
    """One parsed verdict entry's two row sets.

    The artifact's `conformant` boolean is VALIDATED (a non-boolean is a
    malformed entry) but not carried: it is `not failing_rows` by
    construction, and deciding the matrix from the rows themselves means a
    verdict claiming conformance while listing failing rows is read the
    fail-closed way round.
    """

    failing_rows: tuple[str, ...]
    staleness_rows: tuple[str, ...]


def filter_siblings(
    *,
    siblings: list[dict[str, str]],
    verdicts: list[dict[str, object]],
) -> Result[FilterOutcome, FilterError]:
    """Partition the sibling set by conformance verdict, preserving order.

    Every sibling MUST have a verdict entry (the artifact covers every
    manifest member and the sibling set is a subset); a missing entry is
    manifest/verdict drift and fails with `FilterError` rather than
    guessing (fail-closed, criterion 5).

    The two outcomes were previously a hand-rolled `FilterOutcome |
    FilterError` union — an Either encoded by hand, with `FilterError`
    already serving as the failure payload. Only the ENCODING moved onto
    the railway; the partition semantics, the fail-closed rules and every
    reason string are unchanged.

    Note what is NOT a failure: an EXCLUDED member. A non-conformant
    sibling is an ordinary result carried on the success track inside
    `FilterOutcome.excluded`, because excluding it is the filter working
    as designed (criterion 2). The failure track is reserved for
    STRUCTURAL problems that must keep the preflight job red — malformed
    entries and manifest/verdict drift. Collapsing the two would turn a
    routine exclusion into a red job and re-create the gate this filter
    exists to replace.

    And note what is no longer an exclusion at all: a member whose every
    error-severity row carries a ratified pin-currency STALENESS class. It
    stays in the matrix and is reported on the success track inside
    `FilterOutcome.named`, because the dispatch it would have been denied
    is the remedy for the staleness it was denied over.
    """
    parsed = _verdicts_by_member(verdicts=verdicts)
    if isinstance(parsed, Failure):
        return Failure(parsed.failure())
    verdict_by_member = parsed.unwrap()
    filtered: list[dict[str, str]] = []
    excluded: list[Exclusion] = []
    named: list[NamedFindings] = []
    for sibling in siblings:
        name = sibling.get("name")
        if not isinstance(name, str) or not name:
            return Failure(FilterError(reason=f"malformed sibling entry: {sibling!r}"))
        if name not in verdict_by_member:
            return Failure(
                FilterError(reason=f"sibling {name} has no verdict entry (manifest/verdict drift)")
            )
        verdict = verdict_by_member[name]
        excluding = tuple(row for row in verdict.failing_rows if row not in verdict.staleness_rows)
        if excluding:
            excluded.append(Exclusion(member=name, failing_rows=verdict.failing_rows))
            continue
        filtered.append({"name": name})
        if verdict.failing_rows:
            named.append(NamedFindings(member=name, failing_rows=verdict.failing_rows))
    return Success(
        FilterOutcome(filtered=tuple(filtered), excluded=tuple(excluded), named=tuple(named))
    )


def _verdicts_by_member(
    *, verdicts: list[dict[str, object]]
) -> Result[dict[str, _Verdict], FilterError]:
    """Index the verdict artifact by member, failing closed on a malformed entry."""
    indexed: dict[str, _Verdict] = {}
    for verdict in verdicts:
        member = verdict.get("member")
        conformant = verdict.get("conformant")
        if not isinstance(member, str) or not isinstance(conformant, bool):
            return Failure(FilterError(reason=f"malformed verdict entry: {verdict!r}"))
        failing = _row_set(value=verdict.get("failing_rows"), member=member, key="failing_rows")
        if isinstance(failing, Failure):
            return Failure(failing.failure())
        # An ABSENT `staleness_rows` key reads as "no row carries that class",
        # which is the pre-class behavior: every failing row excludes. That is
        # the fail-closed direction, so an older verdict artifact meeting a
        # newer filter withholds a dispatch rather than granting one on
        # evidence nobody wrote.
        staleness = _row_set(
            value=verdict.get("staleness_rows", []), member=member, key="staleness_rows"
        )
        if isinstance(staleness, Failure):
            return Failure(staleness.failure())
        indexed[member] = _Verdict(failing_rows=failing.unwrap(), staleness_rows=staleness.unwrap())
    return Success(indexed)


def _row_set(*, value: object, member: str, key: str) -> Result[tuple[str, ...], FilterError]:
    """One verdict field read as a tuple of row ids, or the structural failure it is."""
    if not isinstance(value, list):
        return Failure(FilterError(reason=f"malformed {key} for member {member}"))
    items = cast("list[object]", value)
    rows = tuple(row for row in items if isinstance(row, str))
    if len(rows) != len(items):
        return Failure(FilterError(reason=f"non-string row in {key} for {member}"))
    return Success(rows)


def _read_json_list(*, path: Path) -> list[object] | None:
    """Read a JSON array from `path`; None on any read or parse failure."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, list):
        return None
    return cast("list[object]", payload)


def _as_dict_list(*, payload: list[object]) -> list[dict[str, object]] | None:
    entries: list[dict[str, object]] = []
    for entry in payload:
        if not isinstance(entry, dict):
            return None
        entries.append(cast("dict[str, object]", entry))
    return entries


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="dispatch_matrix_filter",
        description=(
            "Filter the release-dispatch sibling matrix by the per-member "
            "conformance verdict artifact (livespec-f73t Slice 2b)."
        ),
    )
    _ = parser.add_argument("--verdicts", type=Path, required=True)
    _ = parser.add_argument("--siblings", type=Path, required=True)
    _ = parser.add_argument("--filtered-out", type=Path, required=True)
    _ = parser.add_argument("--exclusions-out", type=Path, required=True)
    return parser


def _announce(*, outcome: FilterOutcome, log: structlog.stdlib.BoundLogger) -> None:
    """Make every error finding visible on the run, excluded or not.

    Both halves are loud on purpose. Excluding a member silently is the
    `livespec-bmxs` omission hazard; KEEPING one silently is the same hazard
    inverted — a release that dispatched to a member with error-severity
    findings and said nothing reads as a release with no findings at all.
    """
    for exclusion in outcome.excluded:
        rows = ", ".join(exclusion.failing_rows) or "(rows unavailable)"
        # stdout on purpose: the Actions runner parses workflow commands
        # from stdout, making the exclusion a visible run annotation
        # (criterion 3); the caller captures nothing from stdout.
        print(  # noqa: T201
            f"::warning::EXCLUDED from release dispatch: {exclusion.member} — "
            f"failing conformance rows: {rows}"
        )
        log.warning(
            "member excluded from dispatch matrix",
            member=exclusion.member,
            failing_rows=list(exclusion.failing_rows),
        )
    for keep in outcome.named:
        rows = ", ".join(keep.failing_rows) or "(rows unavailable)"
        print(  # noqa: T201
            f"::warning::DISPATCHED DESPITE findings: {keep.member} — "
            f"pin-currency staleness rows: {rows} — the sibling-released dispatch is "
            f"the remedy for a stale pin, so it is not withheld over one"
        )
        log.warning(
            "member kept in dispatch matrix despite staleness findings",
            member=keep.member,
            failing_rows=list(keep.failing_rows),
        )


def _summary_payload(*, outcome: FilterOutcome) -> list[dict[str, object]]:
    """The run's exclusion summary: every named member, and whether it was excluded.

    One array rather than two, because the step summary renders one section
    and a reader comparing two files is a reader who can mistake a keep for
    an exclusion. `excluded` is the discriminator.
    """
    entries: list[dict[str, object]] = []
    for exclusion in outcome.excluded:
        entries.append(
            {
                "member": exclusion.member,
                "failing_rows": list(exclusion.failing_rows),
                "excluded": True,
            }
        )
    for keep in outcome.named:
        entries.append(
            {
                "member": keep.member,
                "failing_rows": list(keep.failing_rows),
                "excluded": False,
            }
        )
    return entries


def main(*, argv: list[str] | None = None) -> int:
    log = structlog.get_logger("dispatch_matrix_filter")
    args = _build_parser().parse_args(argv)
    verdicts_payload = _read_json_list(path=cast("Path", args.verdicts))
    siblings_payload = _read_json_list(path=cast("Path", args.siblings))
    if verdicts_payload is None or siblings_payload is None:
        log.error(
            "filter input unreadable or not a JSON array (fail-closed)",
            verdicts=str(cast("Path", args.verdicts)),
            siblings=str(cast("Path", args.siblings)),
        )
        return 1
    verdict_entries = _as_dict_list(payload=verdicts_payload)
    sibling_entries = _as_dict_list(payload=siblings_payload)
    if verdict_entries is None or sibling_entries is None:
        log.error("filter input entry is not an object (fail-closed)")
        return 1
    filtered_result = filter_siblings(
        siblings=cast("list[dict[str, str]]", sibling_entries),
        verdicts=verdict_entries,
    )
    if isinstance(filtered_result, Failure):
        log.error("dispatch-matrix filter failed closed", reason=filtered_result.failure().reason)
        return 1
    outcome = filtered_result.unwrap()
    _announce(outcome=outcome, log=log)
    _ = cast("Path", args.filtered_out).write_text(
        json.dumps(list(outcome.filtered)) + "\n", encoding="utf-8"
    )
    _ = cast("Path", args.exclusions_out).write_text(
        json.dumps(_summary_payload(outcome=outcome)) + "\n",
        encoding="utf-8",
    )
    log.info(
        "dispatch matrix filtered",
        kept=len(outcome.filtered),
        excluded=len(outcome.excluded),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
