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

Vantage: this module is the CENTRAL lane. It runs the rows answerable
under the fleet GitHub App installation token every automated context
authenticates with. The two ADMIN-scoped rows (`branch-protection`,
`secret-names`) are NOT run here — the App token deliberately lacks
admin scope — and are reported as out-of-vantage naming the lane that
does enforce them (`check-fleet-conformance-admin`, the pre-push world
gate in `fleet_conformance_admin.py`). The posture-gated adopter
currency leg (`_adopter_lane.run_adopter_rows`) gets the same
treatment for the same reason: the fleet App's installation MUST be
restricted to fleet repos only, so a private released adopter is
structurally unreadable here, and the leg is reported out-of-vantage
(owned by the admin lane) at zero API cost rather than evaluated
vacuously.

Blind rows: a `RowSkip` means "could not be evaluated", which is NOT
the same as "passed" — yet historically it was logged at `info` and
touched neither the exit code nor any summary, so a row skipped for
EVERY applicable member enforced nothing while the run reported
success. Every row this lane ATTEMPTS is now tallied (evaluated vs
skipped) over the members it actually applied to, and a row with skips
and zero evaluations is reported as blind, with a blind-row count in
the run summary. Severity is WARNING and never moves the exit code:
this is NEW signal rather than a demoted gate. There is no lever,
exemption list, or opt-out — every attempted row is always counted.

The two admin rows used to land in that blind tally on EVERY automated
run, since no automated context can ever read them. A permanent
warning nothing can clear is how a real signal gets tuned out, so they
are now accounted separately as out-of-vantage rather than suppressed:
blind still means "this lane should have read it and could not".
Escalating blind rows to error severity remains the recorded intended
end state, and is a follow-up to this split rather than part of it.

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
from pathlib import Path
from typing import cast

from livespec_dev_tooling.fleet._adopter_lane import run_adopter_rows
from livespec_dev_tooling.fleet._context import (
    FleetContext,
    default_gh_runner,
    resolve_owner,
)
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
    result = run_member_rows(ctx=ctx, manifest=manifest, log=log)
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
    out_of_vantage_rows = result.out_of_vantage_rows + adopters.out_of_vantage_rows
    if errors:
        log.error(
            "fleet conformance FAILED",
            error_findings=errors,
            blind_rows=result.blind_rows,
            out_of_vantage_rows=out_of_vantage_rows,
        )
        return 4
    log.info(
        "fleet conformance passed",
        members=len(manifest.members),
        blind_rows=result.blind_rows,
        out_of_vantage_rows=out_of_vantage_rows,
        owner=owner,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
