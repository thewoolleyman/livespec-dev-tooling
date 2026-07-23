"""fleet_conformance_admin — the ADMIN-vantage (world-gate) lane of the fleet contract.

Two obligation rows need GitHub ADMIN scope on each member: `secret-names`
(the Actions-secrets list) and `branch-protection` (the branch-protection
endpoints). Every AUTOMATED context that runs the central sweep — the per-PR
CI job, the scheduled `fleet-conformance.yml`, and the release fan-out
preflight — authenticates with the fleet GitHub App installation token, which
deliberately lacks admin scope (least privilege, livespec
`non-functional-requirements.md`). Operator-local `just check` does not set
`LIVESPEC_RUN_FLEET_CONFORMANCE`, so it skips the central sweep entirely.
Both rows were therefore enforced in ZERO contexts, while
`fleet-conformance.yml`'s header claimed operator-local runs covered them.

This module is that missing lane. It is a WORLD GATE in the established
sense of `branch_protection_alignment` and `master_ci_green`: it inspects
live world state under the OPERATOR's own admin `gh` credentials, is wired
into the `just check` aggregate so it reaches pre-push, and is deliberately
NOT mirrored into the per-PR CI matrix, where the App token would make it
always-skip and the job would be pointless. Widening the App's permissions
was considered and rejected (least privilege); so was deleting the rows.

Scope discipline: it asserts ONLY the admin-vantage rows — nothing this
lane cannot answer is read. Measured against the live 9-member fleet that
is ~35 API reads and ~18s, i.e. roughly 4 per member: the secrets list,
the protection payload, and (for branch-protection's ALIGNMENT leg) the
member's default branch plus its ci.yml. So this is proportionate, not
cheap; the honest comparison is that it costs about what the central
sweep costs, for two rows instead of sixteen, because those two rows are
individually read-heavy. Trimming further would mean dropping the
alignment comparison, which is the part of the row that actually catches
phantom required checks.

Credential shortfall is NOT silently tolerated. Running without admin scope
makes both rows skip for every member, which this lane reports as BLIND —
the b02 signal, loud — because this IS the lane that should have read them.
That is the opposite of the central lane's treatment, where the same two
rows are out-of-vantage: expected, and owned by this recipe.

Exit codes:

- `0` — every admin row passed, or skipped without an error-severity
  finding (blind rows warn; they do not fail, matching the central lane).
- `1` — precondition failure: owner unresolvable, or the manifest
  unfetchable / unparseable (the manifest is the root fact; fail loud).
- `4` — one or more error-severity findings.

Output discipline matches sibling checks: structlog JSON to stderr;
no `print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._context import FleetContext, default_gh_runner, resolve_owner
from livespec_dev_tooling.fleet._contract_rows import ADMIN_VANTAGE
from livespec_dev_tooling.fleet._lanes import configure_lane_logging, run_member_rows
from livespec_dev_tooling.fleet.fleet_conformance import (
    MANIFEST_PATH,
    MANIFEST_REPO,
    fetch_manifest,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fleet-conformance-admin",
        description=(
            "Admin-vantage (world-gate) fleet-membership conformance lane: the "
            "secret-names and branch-protection rows, under the operator's own "
            "admin gh credentials."
        ),
    )
    _ = parser.add_argument(
        "--owner",
        default=None,
        help="GitHub owner override; defaults to the origin remote's owner.",
    )
    return parser


def main() -> int:
    configure_lane_logging()
    log = structlog.get_logger("fleet_conformance_admin")
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
            source=f"{owner}/{MANIFEST_REPO}:{MANIFEST_PATH}",
            hint="the manifest on livespec master is the root fact; failing loud",
        )
        return 1
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log, vantage=ADMIN_VANTAGE)
    if result.error_findings:
        log.error(
            "fleet admin conformance FAILED",
            error_findings=result.error_findings,
            blind_rows=result.blind_rows,
        )
        return 4
    log.info(
        "fleet admin conformance passed",
        members=len(manifest.members),
        blind_rows=result.blind_rows,
        vantage=ADMIN_VANTAGE,
        owner=owner,
        hint=(
            "blind rows here mean the running gh credential lacks admin scope on those "
            "members — this lane is the one that SHOULD read them"
        ),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
