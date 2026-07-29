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

This lane ALSO owns the posture-gated adopter currency leg
(`_adopter_lane.run_adopter_rows`, livespec-dev-tooling-453): the
manifest's `adopters` array iterated for exactly one concern —
`claude-plugin-currency`, only where `posture == "released"` — and
never for the per-class obligation rows, which the spec binds to the
`fleet` array alone. The leg is admin-vantage for the same structural
reason as the two member rows: the fleet App's installation MUST be
restricted to fleet repos only, so a private released adopter is
unreadable to every automated central-lane context, and a leg there
could only ever skip while reading as coverage. Adopter findings are
error-severity (fail loud, maintainer decision 2026-07-20); pinned /
none postures are reported as posture-excluded, a declared choice
honored by never reading the repo.

Scope discipline: it asserts ONLY the admin-vantage rows and the
adopter currency leg — nothing this lane cannot answer is read.
Measured against the live 9-member fleet the member rows are ~35 API
reads and ~18s, i.e. roughly 4 per member: the secrets list, the
protection payload, and (for branch-protection's ALIGNMENT leg) the
member's default branch plus its ci.yml. So this is proportionate, not
cheap; the honest comparison is that it costs about what the central
sweep costs, for two rows instead of sixteen, because those two rows are
individually read-heavy. Trimming further would mean dropping the
alignment comparison, which is the part of the row that actually catches
phantom required checks. The adopter leg adds ~3 reads per RELEASED
adopter (one today) and zero for excluded postures.

Credential CLASS precedes credential shortfall. The lane's own design
scopes it to the OPERATOR's pre-push under the operator's own admin gh
credentials — so a `ghs_`-class effective credential (a GitHub App
installation token: the dispatch credential a Fabro sandbox holds,
projected as GITHUB_TOKEN, whose commit hooks DO reach the `just check`
aggregate) is structurally NOT this lane's vantage. Admin scope is
DELIBERATELY withheld from that credential class (the ratified livespec
v045 capability boundary), so under it this lane's rows — both admin
member rows AND the adopter currency leg — are OUT-OF-VANTAGE in the
established `_lanes` sense: owned by the operator's pre-push context,
reported at info severity, exit 0, at ZERO API reads (the guard
short-circuits before even the manifest fetch, so an expired or revoked
dispatch token cannot turn classification into a precondition failure).
This is vantage classification via `holds_app_class_credential` — the
same shared credential-class rule `central_run_vantages` applies — NOT
a lever: no env var, exemption, or demotion path exists, and the
classification never widens beyond the `ghs_` class.

Within the lane's own vantage — ANY user-class credential — shortfall
is NOT silently tolerated. Running without admin scope makes both
member rows skip for every member — and an unreadable released adopter
makes the currency leg skip — which this lane reports as BLIND at ERROR
severity and FAILS on: this IS the lane that should have read them, so
a run that could not is a failed run, not a vacuous pass (the b02
escalation, shipped once the vantage model left no row structurally
blind in any healthy context; no lever, env var, or exemption can
demote it). That is the opposite of the central lane's treatment, where
the same two rows and the adopter leg are out-of-vantage: expected, and
owned by this recipe.

Exit codes:

- `0` — every admin row and adopter-leg evaluation passed, or partially
  skipped, with no error-severity finding and no blind row; or the run
  holds a dispatch-class (`ghs_`) credential, under which every row this
  lane owns is out-of-vantage (owned by the operator's pre-push).
- `1` — precondition failure: owner unresolvable, or the manifest
  unfetchable / unparseable (the manifest is the root fact; fail loud).
- `4` — one or more error-severity findings, or one or more blind rows
  (this lane owns a row it could not read anywhere).

Output discipline matches sibling checks: structlog JSON to stderr;
no `print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

from livespec_dev_tooling.fleet._adopter_lane import ADOPTER_CURRENCY_ROW_ID, run_adopter_rows
from livespec_dev_tooling.fleet._context import FleetContext, default_gh_runner, resolve_owner
from livespec_dev_tooling.fleet._contract_rows import ADMIN_VANTAGE, OBLIGATION_ROWS
from livespec_dev_tooling.fleet._credential_preflight import preflight_credential
from livespec_dev_tooling.fleet._lanes import (
    LANE_RECIPES,
    OUT_OF_VANTAGE_EVENT,
    configure_lane_logging,
    run_member_rows,
)
from livespec_dev_tooling.fleet.fleet_conformance import (
    MANIFEST_PATH,
    MANIFEST_REPO,
    fetch_manifest,
    holds_app_class_credential,
)

if TYPE_CHECKING:
    import structlog.stdlib

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


# Who enforces this lane's rows when a run holds the WRONG credential
# class: composed from the recipe registry (never a second copy of the
# recipe name) plus the credential context, mirroring the shape of the
# `central-app` LANE_RECIPES entry, so the out-of-vantage report names a
# context an operator can actually go run.
_OPERATOR_PRE_PUSH_CONTEXT = (
    f"{LANE_RECIPES[ADMIN_VANTAGE]} at the operator's own pre-push, under the "
    "operator's own admin gh credentials (a user-class token — never the "
    "dispatch App installation token, from which admin scope is deliberately "
    "withheld per the livespec v045 capability boundary)"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fleet-conformance-admin",
        description=(
            "Admin-vantage (world-gate) fleet-membership conformance lane: the "
            "secret-names and branch-protection rows plus the posture-gated "
            "adopter currency leg, under the operator's own admin gh credentials."
        ),
    )
    _ = parser.add_argument(
        "--owner",
        default=None,
        help="GitHub owner override; defaults to the origin remote's owner.",
    )
    return parser


def _dispatch_class_out_of_vantage(*, log: structlog.stdlib.BoundLogger) -> int:
    """Classify every row this lane owns out-of-vantage for a dispatch-class run.

    Reached when the effective gh credential is `ghs_`-class (a GitHub
    App installation token — the Fabro sandbox's dispatch credential,
    whose commit hooks reach the `just check` aggregate). Admin scope is
    deliberately withheld from that class (the livespec v045 capability
    boundary), so this run is structurally not the lane's vantage:
    treating it as a credential shortfall instead (blind, exit 4) killed
    every factory dispatch to this repo at the Red commit hook — the
    repo-wide outage journaled on livespec-dev-tooling-34t2.

    Mirrors the existing out-of-vantage path's economics: rows are
    classified BEFORE any assert runs, and the manifest itself is never
    fetched — zero API reads, and an expired or revoked dispatch token
    cannot turn classification into a precondition failure. The row set
    is derived from the obligation table (the admin-vantage rows) plus
    the adopter currency leg this lane owns; the owning context is named
    so the report stays actionable, exactly like `_lanes`' reporting.
    """
    admin_row_ids = tuple(row.row_id for row in OBLIGATION_ROWS if row.vantage == ADMIN_VANTAGE)
    for row_id in (*admin_row_ids, ADOPTER_CURRENCY_ROW_ID):
        log.info(
            OUT_OF_VANTAGE_EVENT,
            row=row_id,
            vantage=ADMIN_VANTAGE,
            owned_by=_OPERATOR_PRE_PUSH_CONTEXT,
        )
    log.info(
        "fleet admin conformance out-of-vantage under a dispatch-class credential",
        credential_class="GitHub App installation token (ghs_-prefixed; probe-only, never logged)",
        out_of_vantage_rows=len(admin_row_ids) + 1,
        blind_rows=0,
        owned_by=_OPERATOR_PRE_PUSH_CONTEXT,
    )
    return 0


def main() -> int:
    configure_lane_logging()
    log = structlog.get_logger("fleet_conformance_admin")
    args = _build_parser().parse_args()
    # The env pair `gh` itself consults, in `gh`'s own precedence order —
    # the Fabro dispatch sandbox projects its installation token as the
    # second. This lane's supervisor is where the read belongs: it is
    # already a deliberate side-effect boundary, and keeping it here is
    # what leaves `holds_app_class_credential` total under livespec v179
    # member 1 rather than disqualified by clause (c).
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if holds_app_class_credential(token=token):
        return _dispatch_class_out_of_vantage(log=log)
    owner = cast("str | None", args.owner) or resolve_owner()
    if owner is None:
        log.error(
            "owner unresolvable: no --owner and origin remote is not github.com",
            hint="pass --owner or run inside a github.com clone",
        )
        return 1
    ctx = FleetContext(owner=owner, run_gh=default_gh_runner)
    # ONE deliberate credential verdict, before any row runs. Without it a
    # single transient rejection surfaces as N blind rows and reds master on a
    # no-op commit (livespec-dev-tooling-z4qi). This does NOT relax the gate:
    # a genuinely unavailable credential still fails here, loudly, naming one
    # cause instead of N downstream symptoms.
    preflight = preflight_credential(ctx=ctx)
    if not preflight.usable:
        log.error(
            "github credential unusable — no obligation row can see anything",
            attempts=preflight.attempts,
            cause=None if preflight.cause is None else preflight.cause.as_dict(),
            hint=(
                "the credential was probed and rejected; this is one cause, not N "
                "blind rows. Fix the credential — do NOT demote blind rows"
            ),
        )
        return 1
    manifest = fetch_manifest(ctx=ctx)
    if manifest is None:
        log.error(
            "fleet manifest unavailable",
            source=f"{owner}/{MANIFEST_REPO}:{MANIFEST_PATH}",
            hint="the manifest on livespec master is the root fact; failing loud",
            # The CAUSES, not just the verdict. Without these a 403, a 404, a
            # rate-limit and a malformed manifest all read identically as
            # "unavailable", which is what made one transient credential
            # rejection indistinguishable from a real blind spot.
            causes=[failure.as_dict() for failure in ctx.read_failures],
        )
        return 1
    result = run_member_rows(
        ctx=ctx, manifest=manifest, log=log, vantages=frozenset({ADMIN_VANTAGE})
    )
    adopters = run_adopter_rows(ctx=ctx, manifest=manifest, log=log, vantage=ADMIN_VANTAGE)
    error_findings = result.error_findings + adopters.error_findings
    blind_rows = result.blind_rows + adopters.blind_rows
    if error_findings or blind_rows:
        log.error(
            "fleet admin conformance FAILED",
            error_findings=error_findings,
            blind_rows=blind_rows,
            hint=(
                "blind rows here mean the running gh credential lacks admin scope on "
                "those members (or cannot read a released adopter) — this lane is the "
                "one that SHOULD read them, so it fails rather than passing vacuously"
            ),
        )
        return 4
    log.info(
        "fleet admin conformance passed",
        members=len(manifest.members),
        adopters_evaluated=adopters.evaluated,
        adopters_posture_excluded=adopters.posture_excluded,
        blind_rows=blind_rows,
        vantage=ADMIN_VANTAGE,
        owner=owner,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
