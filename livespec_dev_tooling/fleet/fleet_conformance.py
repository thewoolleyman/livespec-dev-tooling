"""fleet_conformance — central assert mode of the fleet-membership contract.

Per livespec v108 §"Fleet membership contract": fetches the fleet
manifest from livespec master at run time, asserts every member's
per-class obligations from a central vantage point (the piece
repo-local CI cannot provide — a repo missing wiring never fails
checks it does not run), and runs the discovery sweep (any owner repo
matching `livespec-*` naming or carrying the `livespec-sibling` topic
but absent from the manifest is a finding).

Execution contexts: the dev-tooling `just check` aggregate (always
wired), the scheduled fleet workflow, and the BLOCKING preflight of
the release fan-out (`reusable-release-dispatch.yml`).

Env lever (the single self-documenting per-check lever, mirroring
`check_mutation`'s RUN/SKIP precedent for network-dependent checks):
`LIVESPEC_RUN_FLEET_CONFORMANCE` unset → the check logs "skipped" and
exits 0 (a per-commit local aggregate run does not fan ~35 GitHub API
reads); set to a non-empty value (the scheduled workflow, the release
fan-out preflight, and the CI job set it) → the full sweep runs. No
external gate, no silent skip.

Blind rows: a `RowSkip` means "could not be evaluated", which is NOT
the same as "passed" — yet historically it was logged at `info` and
touched neither the exit code nor any summary, so a row skipped for
EVERY applicable member enforced nothing while the run reported
success. Every row is now tallied (evaluated vs skipped) over the
members it actually applied to, and a row with skips and zero
evaluations is reported as blind, with a blind-row count in the run
summary. Severity is WARNING and never moves the exit code: this is
NEW signal rather than a demoted gate, and two rows
(`branch-protection`, `secret-names`) are structurally blind in CI
until their own repairs land. Escalating to error once those land is
the recorded intended end state, not an optional nicety. There is no
lever, exemption list, or opt-out — every row is always counted.

Exit codes:

- `0` — lever unset (logged skip), or every applicable row passed /
  skipped with no error-severity finding (blind rows included: they
  warn, they do not fail).
- `1` — precondition failure with the lever set: owner unresolvable,
  or the manifest unfetchable / unparseable (the manifest is the root
  fact; per the fail-fast decision the run is loud, not silent).
- `4` — one or more error-severity findings (member rows or the
  discovery sweep). Warning-severity findings (pin staleness) log but
  do not fail.

Output discipline matches sibling checks: structlog JSON to stderr;
no `print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    RowFinding,
    RowSkip,
    default_gh_runner,
    resolve_owner,
)
from livespec_dev_tooling.fleet._contract_rows import rows_for
from livespec_dev_tooling.fleet._rows_github import SIBLING_TOPIC
from livespec_dev_tooling.fleet.contract import Manifest, parse_manifest

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_RUN_ENV_VAR = "LIVESPEC_RUN_FLEET_CONFORMANCE"
_MANIFEST_REPO = "livespec"
_MANIFEST_PATH = ".livespec-fleet-manifest.jsonc"
_BLIND_ROW_EVENT = "obligation row enforced NOTHING this run (skipped for every applicable member)"


@dataclass(frozen=True, kw_only=True)
class MemberVerdict:
    """Machine-readable conformance result for one manifest member."""

    member: str
    failing_rows: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class MemberRowsResult:
    """What the member-row sweep found: error findings, plus rows that went blind.

    The counts and verdicts are deliberately SEPARATE. `error_findings` alone
    drives the exit code; `blind_rows` is reported so a green run that enforced
    nothing is visibly different from a green run that enforced everything.
    """

    error_findings: int
    blind_rows: int
    member_verdicts: tuple[MemberVerdict, ...]


def fetch_manifest(*, ctx: FleetContext) -> Manifest | None:
    """The fleet manifest from livespec master, or None when unavailable."""
    text = ctx.file_text(repo=_MANIFEST_REPO, path=_MANIFEST_PATH)
    if text is None:
        return None
    return parse_manifest(source=text)


def run_member_rows(
    *, ctx: FleetContext, manifest: Manifest, log: structlog.stdlib.BoundLogger
) -> MemberRowsResult:
    """Assert every member's applicable rows; report error findings and blind rows.

    Rows are selected PER MEMBER via `rows_for`, so different rows apply to
    different numbers of members; the tallies below therefore count only the
    members a row actually applied to, never the whole membership.
    """
    errors = 0
    evaluated: dict[str, int] = {}
    skips: dict[str, list[str]] = {}
    failing_rows_by_member: dict[str, list[str]] = {}
    for member in manifest.members:
        failing_rows_by_member[member.repo] = []
        for row in rows_for(repo_class=member.repo_class):
            outcome = row.assert_member(ctx=ctx, member=member)
            if isinstance(outcome, RowSkip):
                # Row functions prefix their reason with the member repo; the
                # blind-row warning reports the underlying CAUSES, and the
                # member is already implied by "every applicable member".
                skips.setdefault(row.row_id, []).append(
                    outcome.reason.removeprefix(f"{member.repo}: ")
                )
                log.info(
                    "fleet obligation not evaluable (can't-read is not absent)",
                    row=row.row_id,
                    member=member.repo,
                    reason=outcome.reason,
                )
                continue
            evaluated[row.row_id] = evaluated.get(row.row_id, 0) + 1
            if isinstance(outcome, RowFinding):
                if outcome.severity == "warning":
                    log.warning(
                        "fleet obligation warning",
                        row=row.row_id,
                        member=member.repo,
                        detail=outcome.message,
                    )
                else:
                    errors += 1
                    failing_rows_by_member[member.repo].append(row.row_id)
                    log.error(
                        "fleet obligation violated",
                        row=row.row_id,
                        member=member.repo,
                        detail=outcome.message,
                        hint=row.manual_hint or "run wire-fleet-member to reconcile",
                    )
    return MemberRowsResult(
        error_findings=errors,
        blind_rows=_report_blind_rows(evaluated=evaluated, skips=skips, log=log),
        member_verdicts=tuple(
            MemberVerdict(member=member, failing_rows=tuple(failing_rows))
            for member, failing_rows in failing_rows_by_member.items()
        ),
    )


def _member_verdict_payload(
    *, member_verdicts: tuple[MemberVerdict, ...]
) -> list[dict[str, object]]:
    """JSON-ready per-member verdict payload for workflow consumers."""
    return [
        {
            "member": verdict.member,
            "conformant": not verdict.failing_rows,
            "failing_rows": list(verdict.failing_rows),
        }
        for verdict in member_verdicts
    ]


def _write_member_verdicts(*, path: Path, member_verdicts: tuple[MemberVerdict, ...]) -> None:
    """Emit the per-member verdict artifact requested by the CLI caller."""
    _ = path.write_text(
        json.dumps(_member_verdict_payload(member_verdicts=member_verdicts), indent=2) + "\n",
        encoding="utf-8",
    )


def _report_blind_rows(
    *,
    evaluated: dict[str, int],
    skips: dict[str, list[str]],
    log: structlog.stdlib.BoundLogger,
) -> int:
    """Warn for each row evaluable on NO applicable member; return how many.

    A row present in `skips` but absent from `evaluated` applied to at least
    one member and answered for none of them, so it enforced nothing this
    run. `applicable` equals the skip count by construction — zero members
    were evaluated — and both are reported so the reader need not infer it.
    """
    blind = 0
    for row_id, reasons in skips.items():
        if evaluated.get(row_id, 0):
            continue
        blind += 1
        log.warning(
            _BLIND_ROW_EVENT,
            row=row_id,
            applicable=len(reasons),
            skipped=len(reasons),
            reasons=tuple(dict.fromkeys(reasons)),
        )
    return blind


def run_discovery_sweep(
    *, ctx: FleetContext, manifest: Manifest, log: structlog.stdlib.BoundLogger
) -> int:
    """Flag owner repos matching the fleet shape but absent from the manifest."""
    payload = ctx.api_object(path=f"users/{ctx.owner}/repos?per_page=100")
    if not isinstance(payload, list):
        log.warning(
            "discovery sweep skipped: owner repo list unreadable",
            owner=ctx.owner,
        )
        return 0
    known = manifest.member_names()
    errors = 0
    for entry in cast("list[object]", payload):
        if not isinstance(entry, dict):
            continue
        record = cast("dict[str, object]", entry)
        name = record.get("name")
        if not isinstance(name, str):
            continue
        topics_raw = record.get("topics")
        topics = cast("list[object]", topics_raw) if isinstance(topics_raw, list) else []
        fleet_shaped = name.startswith("livespec") or SIBLING_TOPIC in topics
        if fleet_shaped and name not in known:
            errors += 1
            log.error(
                "fleet-shaped repo is not registered in the fleet manifest",
                repo=name,
                hint=(
                    "register it in livespec .livespec-fleet-manifest.jsonc FIRST, then run "
                    "wire-fleet-member (register-first repo birth procedure)"
                ),
            )
    return errors


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fleet-conformance",
        description=(
            "Central fleet-membership conformance check (livespec v108 "
            '§"Fleet membership contract").'
        ),
    )
    _ = parser.add_argument(
        "--owner",
        default=None,
        help="GitHub owner override; defaults to the origin remote's owner.",
    )
    _ = parser.add_argument(
        "--emit-member-verdicts",
        type=Path,
        default=None,
        help="Write per-member conformance verdicts as JSON to this path.",
    )
    return parser


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("fleet_conformance")
    args = _build_parser().parse_args()
    if not os.environ.get(_RUN_ENV_VAR):
        log.info(
            "fleet-conformance skipped (run lever unset)",
            lever=_RUN_ENV_VAR,
            hint=(
                "set it to run the ~35-API-read central sweep; the scheduled fleet "
                "workflow, the release fan-out preflight, and the CI job set it"
            ),
        )
        return 0
    owner = cast("str | None", args.owner) or resolve_owner()
    if owner is None:
        log.error(
            "owner unresolvable: no --owner and origin remote is not github.com",
            hint="pass --owner or run inside a github.com clone",
        )
        return 1
    ctx = FleetContext(owner=owner, run_gh=default_gh_runner)
    manifest = fetch_manifest(ctx=ctx)
    if manifest is None:
        log.error(
            "fleet manifest unavailable",
            source=f"{owner}/{_MANIFEST_REPO}:{_MANIFEST_PATH}",
            hint="the manifest on livespec master is the root fact; failing loud",
        )
        return 1
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log)
    if args.emit_member_verdicts is not None:
        _write_member_verdicts(
            path=cast("Path", args.emit_member_verdicts),
            member_verdicts=result.member_verdicts,
        )
    errors = result.error_findings + run_discovery_sweep(ctx=ctx, manifest=manifest, log=log)
    if errors:
        log.error("fleet conformance FAILED", error_findings=errors, blind_rows=result.blind_rows)
        return 4
    log.info(
        "fleet conformance passed",
        members=len(manifest.members),
        blind_rows=result.blind_rows,
        owner=owner,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
