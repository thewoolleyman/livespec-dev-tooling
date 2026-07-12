"""wire_fleet_member — idempotent reconcile mode of the fleet contract.

Per livespec v108 §"Fleet membership contract" ("assert mode is CI;
reconcile mode is wiring"): walks the SAME obligation table as
`fleet_conformance` for ONE member, and for each violated row applies
the row's reconcile reference — secrets pushed from the 1Password-
wrapper environment (per livespec §"Fleet secrets — 1Password
Environment as canonical source"; values flow env→stdin only), branch
protection set from the member's ci.yml matrix, the topic applied,
ONE shim-workflow PR opened for missing shims — or surfaces the row's
`manual_hint` where no machine fix exists from this vantage point.
The secret source env vars are GITHUB_APP_ID and GITHUB_PRIVATE_KEY;
the destination Actions secret names remain APP_ID and APP_PRIVATE_KEY.

Operator-invoked, NOT CI (no run lever): the repo-birth procedure is
scaffold → register in the manifest FIRST → run this → fleet
conformance green. Invoke under the environment wrapper so the secret
projection is present:

    with-livespec-env.sh -- env PATH="$HOME/.local/bin:$PATH" uv run python -m \\
        livespec_dev_tooling.fleet.wire_fleet_member --repo <member>

Exit codes:

- `0` — every applicable row passes, was reconciled, or was actioned
  (an opened shim PR counts as actioned; merge completes it).
- `1` — precondition failure: owner unresolvable, manifest
  unavailable, or `--repo` NOT in the manifest (register-first: a
  repo is wired only after it is a declared member).
- `4` — unresolved error findings remain (a reconcile failed, or the
  row is manual-only — the log carries the manual_hint).

Output discipline matches sibling checks: structlog JSON to stderr;
no `print`, no `sys.stderr.write`. Secret VALUES never appear in any
stream.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowPass,
    RowSkip,
    default_gh_runner,
    resolve_owner,
)
from livespec_dev_tooling.fleet._contract_rows import ObligationRow, rows_for
from livespec_dev_tooling.fleet.fleet_conformance import fetch_manifest

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


def _reconcile_row(
    *,
    ctx: FleetContext,
    member: FleetMember,
    row: ObligationRow,
    log: structlog.stdlib.BoundLogger,
) -> int:
    """Apply one row's reconcile (or surface its hint); 1 = still unresolved."""
    if row.reconcile is None:
        log.error(
            "row is manual-only; operator action required",
            row=row.row_id,
            member=member.repo,
            hint=row.manual_hint,
        )
        return 1
    fixed = row.reconcile(ctx=ctx, member=member)
    if isinstance(fixed, RowPass):
        log.info(
            "row reconciled",
            row=row.row_id,
            member=member.repo,
            note=fixed.note,
        )
        return 0
    detail = fixed.message if isinstance(fixed, RowFinding) else fixed.reason
    log.error(
        "reconcile did not resolve the row",
        row=row.row_id,
        member=member.repo,
        detail=detail,
    )
    return 1


def reconcile_member(
    *, ctx: FleetContext, member: FleetMember, log: structlog.stdlib.BoundLogger
) -> int:
    """Assert-then-reconcile every applicable row; return the unresolved count."""
    unresolved = 0
    for row in rows_for(repo_class=member.repo_class):
        outcome = row.assert_member(ctx=ctx, member=member)
        if isinstance(outcome, RowSkip):
            log.info(
                "row not evaluable; nothing reconciled",
                row=row.row_id,
                member=member.repo,
                reason=outcome.reason,
            )
        elif isinstance(outcome, RowFinding):
            if outcome.severity == "warning":
                log.warning(
                    "row warning (not a wiring concern)",
                    row=row.row_id,
                    member=member.repo,
                    detail=outcome.message,
                )
            else:
                unresolved += _reconcile_row(ctx=ctx, member=member, row=row, log=log)
    return unresolved


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wire-fleet-member",
        description=(
            "Idempotent reconcile mode of the fleet-membership contract "
            '(livespec v108 §"Fleet membership contract").'
        ),
    )
    _ = parser.add_argument(
        "--repo",
        required=True,
        help="The member repo to wire (must already be registered in the manifest).",
    )
    _ = parser.add_argument(
        "--owner",
        default=None,
        help="GitHub owner override; defaults to the origin remote's owner.",
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
    log = structlog.get_logger("wire_fleet_member")
    args = _build_parser().parse_args()
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
            hint="the manifest on livespec master is the root fact; failing loud",
        )
        return 1
    repo = cast("str", args.repo)
    member = next((entry for entry in manifest.members if entry.repo == repo), None)
    if member is None:
        log.error(
            "repo is not a registered fleet member",
            repo=repo,
            hint=(
                "register it in livespec .livespec-fleet-manifest.jsonc FIRST (register-first "
                "repo birth procedure), then re-run wire-fleet-member"
            ),
        )
        return 1
    unresolved = reconcile_member(ctx=ctx, member=member, log=log)
    if unresolved:
        log.error("wiring incomplete", member=member.repo, unresolved_rows=unresolved)
        return 4
    log.info("member fully wired", member=member.repo, repo_class=member.repo_class)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
