"""Operator entry points: `incident-fleet-audit` and the one incident enablement step.

The audit prints one row per surface and consumer, the serving version read for each
consumer and capability, then findings and the ready list, and exits non-zero unless
every row is classified. The enablement step runs its own fresh audit against core's
current master and enables a repository only if that audit's ready list names it; it
accepts no ready list from its caller. No evidence source is steerable by the caller:
the owner, the claims, the clones and the account are fixed by this code and the
account database, and no argument or environment variable moves them.
"""

from __future__ import annotations

import sys
from argparse import ArgumentParser
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402

from livespec_dev_tooling import incident_enablement as enable  # noqa: E402
from livespec_dev_tooling._incident_fleet_command import (  # noqa: E402
    FleetReport,
    exit_code,
    render_report,
    run_fleet_audit,
)
from livespec_dev_tooling._incident_fleet_sources import (  # noqa: E402
    COMMITTED_CLAIMS,
    core_manifest_reader,
    load_claims,
)
from livespec_dev_tooling.fleet._local_context import CommandRunner  # noqa: E402
from livespec_dev_tooling.incident_fleet_host import (  # noqa: E402
    FLEET_OWNER,
    production_probe,
)
from livespec_dev_tooling.incident_fleet_runner import scrubbed_runner  # noqa: E402
from livespec_dev_tooling.incident_fleet_serving import (  # noqa: E402
    ServingReader,
    host_serving_reader,
)

__all__: list[str] = [
    "CliEnvironment",
    "EnablementWriter",
    "enable_repository",
    "main",
    "production_environment",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-qmuk7z
# The step's only durable output is the record the serving controller installation holds
# (incident_enablement.py); no dev-host file stands in for it.
EnablementWriter = Callable[[str, str], tuple[int, str]]


@dataclass(frozen=True, kw_only=True)
class _ControllerWriter:
    """The step's positional writer over the controller client's keyword-only one."""

    write: enable.EnablementWriter

    def __call__(self, repository: str, manifest_sha256: str) -> tuple[int, str]:
        return self.write(repository=repository, manifest_sha256=manifest_sha256)


@dataclass(frozen=True, kw_only=True)
class CliEnvironment:
    """Where the command reads from and writes to. Production fixes every location."""

    claims_path: Path
    write_enablement: EnablementWriter
    read_manifest: Callable[[], str | None]
    read_serving: ServingReader


def production_environment(*, run: CommandRunner = scrubbed_runner) -> CliEnvironment:
    """Core's manifest over git, this code's own claims, this host's installed state.

    Every subprocess goes through `scrubbed_runner`: fixed binaries and a scrubbed
    environment, so neither `PATH` nor `GIT_*` nor the caller's git config moves a read.
    The record is written only to the controller installation serving the repository.
    """
    probe = production_probe(run=run)
    return CliEnvironment(
        claims_path=COMMITTED_CLAIMS,
        write_enablement=_ControllerWriter(write=enable.controller_enablement_writer()),
        read_manifest=core_manifest_reader(owner=FLEET_OWNER, run=run),
        read_serving=host_serving_reader(probe=probe),
    )


def _missing_evidence(*, repository: str, report: FleetReport) -> str:
    audit = report.audit
    if not audit.rows:
        return "; ".join(audit.findings)
    named = [finding for finding in audit.findings if finding.startswith(f"{repository}:")]
    return "; ".join(named) or "no audited incident surface classifies it as a ready consumer"


def enable_repository(
    *, repository: str, report: FleetReport, write: EnablementWriter
) -> tuple[int, str]:
    """Enable only a ready repository; refuse by name with the audit's recorded evidence gap.

    The record goes to the serving controller, bound to the identity this audit read.
    """
    audit = report.audit
    if repository not in audit.ready_repositories:
        gap = _missing_evidence(repository=repository, report=report)
        return 1, f"refused\t{repository}: missing evidence: {gap}"
    return write(repository, audit.manifest_sha256)


def main(*, argv: Sequence[str], environment: CliEnvironment) -> int:
    """Run `audit` or `enable REPOSITORY`; the exit code is the command's verdict."""
    parser = ArgumentParser(prog="incident_fleet_cli")
    commands = parser.add_subparsers(dest="command", required=True)
    _ = commands.add_parser("audit")
    _ = commands.add_parser("enable").add_argument("repository")
    args = parser.parse_args(list(argv))
    claims = load_claims(path=environment.claims_path)
    report = run_fleet_audit(
        read_manifest=environment.read_manifest,
        claims=() if isinstance(claims, Failure) else claims.unwrap(),
        read_serving=environment.read_serving,
    )
    if args.command == "audit":
        notes = (
            (f"finding\tevidence claims: {claims.failure()}",)
            if isinstance(claims, Failure)
            else ()
        )
        _ = sys.stdout.write("\n".join((*render_report(report=report), *notes)) + "\n")
        return exit_code(report=report) or int(bool(notes))
    status, line = enable_repository(
        repository=str(args.repository), report=report, write=environment.write_enablement
    )
    _ = (sys.stdout if status == 0 else sys.stderr).write(line + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(main(argv=sys.argv[1:], environment=production_environment()))
