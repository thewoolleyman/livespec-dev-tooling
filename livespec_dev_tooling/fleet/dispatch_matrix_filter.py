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

`SPECIFICATION/contracts.md` section "Pin-currency severity policy" (v093)
then carved ONE exception out of criterion 2: a member whose only
error-severity findings are pin-currency STALENESS findings is RETAINED in
the matrix and still named, because the `sibling-released` dispatch is the
remedy for a stale pin and excluding the member removes its cure. A
can't-PARSE pin finding still excludes, and so does an error finding on any
other row. The disposition rides on the FINDING rather than on the row id
(`_row_finding`), so the two ways one `compat-pin-currency` row can fail part
ways here.

Inputs are the two artifacts `reusable-release-dispatch.yml` already
has in hand: the per-member verdict artifact
`fleet_conformance --emit-member-verdicts` writes
(`[{member, conformant, failing_rows, non_excluding_rows}]`) and the
discovered sibling matrix (`[{name}]`). Fail-closed rules: an unreadable or
unparseable input, a malformed entry, or a sibling with NO verdict entry
(manifest/verdict drift) exits 1 so the preflight job stays red — the
filter path engages only on a well-formed artifact. A verdict for a
member outside the sibling set (the publishing repo, excluded from the
fan-out) is surplus and ignored.

`--retained-out` is OPTIONAL, deliberately, and that is a compatibility
decision rather than a taste one: the fan-out workflow invoking this filter
is pinned at a RELEASE of this package, so a required new flag would make
every unbumped caller exit 2 and red the whole fan-out — the exact
no-circular-gating violation the filter exists to avoid. A caller that
requests no retained artifact still gets the retained member in the dispatch
matrix and still sees it named in the run's annotations.

The partition itself lives in the private sibling
`_dispatch_matrix_partition`; this module is the process entry point and owns
the reads, the writes and the workflow commands.

Output discipline matches sibling checks: structlog JSON to stderr.
The one deliberate stdout emission is the `::warning::` GitHub
annotation line per excluded or retained member — the Actions runner parses
workflow commands from stdout, and the caller captures nothing from
stdout (every result payload goes to an explicit `--*-out` file).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.result import Failure  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._dispatch_matrix_partition import (  # noqa: E402
    Exclusion,
    FilterError,
    FilterOutcome,
    RetainedFinding,
    filter_siblings,
)

__all__: list[str] = [
    "Exclusion",
    "FilterError",
    "FilterOutcome",
    "RetainedFinding",
    "filter_siblings",
    "main",
]


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
    _ = parser.add_argument("--retained-out", type=Path, default=None)
    return parser


def _write_findings(
    *, path: Path, findings: tuple[Exclusion, ...] | tuple[RetainedFinding, ...]
) -> None:
    """One disposition's per-member findings, as the JSON array the caller renders."""
    _ = path.write_text(
        json.dumps(
            [
                {"member": finding.member, "failing_rows": list(finding.failing_rows)}
                for finding in findings
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _announce(*, outcome: FilterOutcome, log: structlog.stdlib.BoundLogger) -> None:
    """Name every member on BOTH dispositions, loudly, before anything is written.

    stdout on purpose: the Actions runner parses workflow commands from stdout,
    making each line a visible run annotation; the caller captures nothing from
    stdout. The retained line says NOT EXCLUDED in so many words — the
    silent-omission hazard cuts both ways, and a member kept despite
    error-severity findings must say which findings it was kept despite.
    """
    for exclusion in outcome.excluded:
        rows = ", ".join(exclusion.failing_rows) or "(rows unavailable)"
        print(  # noqa: T201
            f"::warning::EXCLUDED from release dispatch: {exclusion.member} — "
            f"failing conformance rows: {rows}"
        )
        log.warning(
            "member excluded from dispatch matrix",
            member=exclusion.member,
            failing_rows=list(exclusion.failing_rows),
        )
    for retained in outcome.retained:
        rows = ", ".join(retained.failing_rows) or "(rows unavailable)"
        print(  # noqa: T201
            f"::warning::NOT EXCLUDED from release dispatch (pin-currency staleness only, "
            f"and the dispatch is the remedy): {retained.member} — "
            f"error-severity conformance rows: {rows}"
        )
        log.warning(
            "member retained in dispatch matrix despite error findings",
            member=retained.member,
            failing_rows=list(retained.failing_rows),
        )


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
    _write_findings(path=cast("Path", args.exclusions_out), findings=outcome.excluded)
    retained_out = cast("Path | None", args.retained_out)
    if retained_out is not None:
        _write_findings(path=retained_out, findings=outcome.retained)
    log.info(
        "dispatch matrix filtered",
        kept=len(outcome.filtered),
        excluded=len(outcome.excluded),
        retained=len(outcome.retained),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
