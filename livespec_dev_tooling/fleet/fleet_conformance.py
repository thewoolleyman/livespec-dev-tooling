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

Vantage: this module is the CENTRAL lane. Its rows partition further
by credential class: the plain `central` rows are answerable under
whatever GitHub credential the lane runs with, while the `central-app`
row (`app-installation`) answers only under the fleet GitHub App
installation token itself — which exactly the automated contexts hold,
each minting one into GH_TOKEN. `central_run_vantages` reads the
run's credential class from that token's prefix, so an automated run
evaluates the row and a local operator run reports it out-of-vantage
naming the owning contexts, not blind. The two ADMIN-scoped rows
(`branch-protection`, `secret-names`) are NOT run here — the App token
deliberately lacks admin scope — and are reported as out-of-vantage
naming the lane that does enforce them (`check-fleet-conformance-admin`,
the pre-push world gate in `fleet_conformance_admin.py`). The
posture-gated adopter currency leg (`_adopter_lane.run_adopter_rows`)
gets the same treatment for the same reason: the fleet App's
installation MUST be restricted to fleet repos only, so a private
released adopter is structurally unreadable here, and the leg is
reported out-of-vantage (owned by the admin lane) at zero API cost
rather than evaluated vacuously.

Blind rows: a `RowSkip` means "could not be evaluated", which is NOT
the same as "passed" — historically it was logged at `info` and a row
skipped for EVERY applicable member enforced nothing while the run
reported success. Every row this lane ATTEMPTS is tallied (evaluated
vs skipped) over the members it actually applied to, and a row with
skips and zero evaluations is reported as BLIND at ERROR severity,
failing the run: a lane that OWNS a row and could not read its source
fails loud rather than passing vacuously. The warning-severity interim
recorded here previously (while the two admin rows, and locally the
app-installation row, were structurally blind) ended when the vantage
model was completed: every row is now owned by a context that can
answer it, so `blind_rows` is structurally 0 in EVERY context when
nothing is actually wrong, and the escalation reddens no healthy run.
There is no lever, env var, exemption list, or opt-out — every
attempted row is always counted.

Exit codes:

- `0` — lever unset (logged skip), or every applicable row passed /
  partially skipped with no error-severity finding and no blind row.
- `1` — precondition failure with the lever set: owner unresolvable,
  or the manifest unfetchable / unparseable (the manifest is the root
  fact; per the fail-fast decision the run is loud, not silent).
- `4` — one or more error-severity findings (member rows, the adopter
  leg, or the discovery sweep), or one or more blind rows (an owned
  row that enforced nothing). Warning-severity findings (pin
  staleness) log but do not fail.

Output discipline matches sibling checks: structlog JSON to stderr;
no `print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._adopter_lane import run_adopter_rows
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    default_gh_runner,
    resolve_owner,
)
from livespec_dev_tooling.fleet._contract_rows import CENTRAL_APP_VANTAGE, CENTRAL_VANTAGE
from livespec_dev_tooling.fleet._lanes import (
    MemberVerdict,
    configure_lane_logging,
    run_member_rows,
)
from livespec_dev_tooling.fleet._rows_github import SIBLING_TOPIC
from livespec_dev_tooling.fleet.contract import Manifest, parse_manifest

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_RUN_ENV_VAR = "LIVESPEC_RUN_FLEET_CONFORMANCE"
MANIFEST_REPO = "livespec"
MANIFEST_PATH = ".livespec-fleet-manifest.jsonc"
# GitHub App installation tokens are `ghs_`-prefixed (server-to-server);
# the automated contexts mint one into GH_TOKEN via
# actions/create-github-app-token, and the Fabro dispatch sandbox
# projects one as GITHUB_TOKEN. The prefix is inspected, never logged
# or echoed (secrets are probe-only).
_APP_TOKEN_PREFIX = "ghs_"


def holds_app_class_credential() -> bool:
    """True when the run's effective gh credential is an App installation token.

    The ONE implementation of the credential-class rule both lanes share
    (the bounded-parser convention: a rule with two copies drifts). The
    token is read from the same env pair `gh` itself consults, `GH_TOKEN`
    first then `GITHUB_TOKEN` (the Fabro dispatch sandbox projects the
    latter); the `ghs_` prefix marks GitHub's server-to-server
    (installation) class. The central lane uses this to claim the
    `central-app` vantage; the admin lane uses it to classify itself
    out-of-vantage under a dispatch-class credential. This is a fact
    about the credential, not a lever — changing it changes which reads
    can actually answer.
    """
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    return token.startswith(_APP_TOKEN_PREFIX)


def central_run_vantages() -> frozenset[str]:
    """The credential-class vantages this central-lane run holds.

    Every central run holds the plain `central` vantage (contents, topics,
    and the other reads any GitHub credential the lane runs with can
    answer). The `central-app` vantage is held exactly when the run's
    token is a GitHub App installation token — the only credential class
    under which `GET /installation/repositories` answers — so the
    `app-installation` row is evaluated in the automated contexts that
    mint one and reported out-of-vantage (naming them) in a local
    operator run.
    """
    if holds_app_class_credential():
        return frozenset({CENTRAL_VANTAGE, CENTRAL_APP_VANTAGE})
    return frozenset({CENTRAL_VANTAGE})


def fetch_manifest(*, ctx: FleetContext) -> Manifest | None:
    """The fleet manifest from livespec master, or None when unavailable."""
    text = ctx.file_text(repo=MANIFEST_REPO, path=MANIFEST_PATH)
    if text is None:
        return None
    return parse_manifest(source=text)


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
    configure_lane_logging()
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
            source=f"{owner}/{MANIFEST_REPO}:{MANIFEST_PATH}",
            hint="the manifest on livespec master is the root fact; failing loud",
        )
        return 1
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log, vantages=central_run_vantages())
    adopters = run_adopter_rows(ctx=ctx, manifest=manifest, log=log)
    if args.emit_member_verdicts is not None:
        _write_member_verdicts(
            path=cast("Path", args.emit_member_verdicts),
            member_verdicts=result.member_verdicts,
        )
    errors = (
        result.error_findings
        + adopters.error_findings
        + run_discovery_sweep(ctx=ctx, manifest=manifest, log=log)
    )
    blind_rows = result.blind_rows + adopters.blind_rows
    out_of_vantage_rows = result.out_of_vantage_rows + adopters.out_of_vantage_rows
    if errors or blind_rows:
        log.error(
            "fleet conformance FAILED",
            error_findings=errors,
            blind_rows=blind_rows,
            out_of_vantage_rows=out_of_vantage_rows,
        )
        return 4
    log.info(
        "fleet conformance passed",
        members=len(manifest.members),
        blind_rows=blind_rows,
        out_of_vantage_rows=out_of_vantage_rows,
        owner=owner,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
