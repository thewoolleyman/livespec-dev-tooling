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

Inputs are the two artifacts `reusable-release-dispatch.yml` already
has in hand: the per-member verdict artifact
`fleet_conformance --emit-member-verdicts` writes
(`[{member, conformant, failing_rows}]`) and the discovered sibling
matrix (`[{name}]`). Fail-closed rules: an unreadable or unparseable
input, a malformed entry, or a sibling with NO verdict entry
(manifest/verdict drift) exits 1 so the preflight job stays red — the
filter path engages only on a well-formed artifact. A verdict for a
member outside the sibling set (the publishing repo, excluded from the
fan-out) is surplus and ignored.

Output discipline matches sibling checks: structlog JSON to stderr.
The one deliberate stdout emission is the `::warning::` GitHub
annotation line per excluded member — the Actions runner parses
workflow commands from stdout, and the caller captures nothing from
stdout (both result payloads go to explicit `--*-out` files).
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

__all__: list[str] = [
    "Exclusion",
    "FilterError",
    "FilterOutcome",
    "filter_siblings",
    "main",
]


@dataclass(frozen=True, kw_only=True)
class Exclusion:
    """One sibling excluded from the dispatch matrix, with its failing rows."""

    member: str
    failing_rows: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class FilterOutcome:
    """The filtered matrix plus the loud exclusion list."""

    filtered: tuple[dict[str, str], ...]
    excluded: tuple[Exclusion, ...]


@dataclass(frozen=True, kw_only=True)
class FilterError:
    """A structural failure that must keep the preflight job red."""

    reason: str


def filter_siblings(
    *,
    siblings: list[dict[str, str]],
    verdicts: list[dict[str, object]],
) -> FilterOutcome | FilterError:
    """Partition the sibling set by conformance verdict, preserving order.

    Every sibling MUST have a verdict entry (the artifact covers every
    manifest member and the sibling set is a subset); a missing entry is
    manifest/verdict drift and returns `FilterError` rather than
    guessing (fail-closed, criterion 5).
    """
    verdict_by_member: dict[str, tuple[bool, tuple[str, ...]]] = {}
    for verdict in verdicts:
        member = verdict.get("member")
        conformant = verdict.get("conformant")
        failing = verdict.get("failing_rows")
        if not isinstance(member, str) or not isinstance(conformant, bool):
            return FilterError(reason=f"malformed verdict entry: {verdict!r}")
        if not isinstance(failing, list):
            return FilterError(reason=f"malformed failing_rows for member {member}")
        failing_items = cast("list[object]", failing)
        rows = tuple(row for row in failing_items if isinstance(row, str))
        if len(rows) != len(failing_items):
            return FilterError(reason=f"non-string failing row in verdict for {member}")
        verdict_by_member[member] = (conformant, rows)
    filtered: list[dict[str, str]] = []
    excluded: list[Exclusion] = []
    for sibling in siblings:
        name = sibling.get("name")
        if not isinstance(name, str) or not name:
            return FilterError(reason=f"malformed sibling entry: {sibling!r}")
        if name not in verdict_by_member:
            return FilterError(
                reason=f"sibling {name} has no verdict entry (manifest/verdict drift)"
            )
        conformant, rows = verdict_by_member[name]
        if conformant:
            filtered.append({"name": name})
        else:
            excluded.append(Exclusion(member=name, failing_rows=rows))
    return FilterOutcome(filtered=tuple(filtered), excluded=tuple(excluded))


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
    outcome = filter_siblings(
        siblings=cast("list[dict[str, str]]", sibling_entries),
        verdicts=verdict_entries,
    )
    if isinstance(outcome, FilterError):
        log.error("dispatch-matrix filter failed closed", reason=outcome.reason)
        return 1
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
    _ = cast("Path", args.filtered_out).write_text(
        json.dumps(list(outcome.filtered)) + "\n", encoding="utf-8"
    )
    _ = cast("Path", args.exclusions_out).write_text(
        json.dumps(
            [
                {
                    "member": exclusion.member,
                    "failing_rows": list(exclusion.failing_rows),
                }
                for exclusion in outcome.excluded
            ]
        )
        + "\n",
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
