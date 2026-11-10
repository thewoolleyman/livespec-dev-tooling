"""Operator entry points: `incident-fleet-audit` and the one incident enablement step.

The audit prints one row per surface and consumer, then findings, then the ready
list, and exits non-zero unless every row is classified. The enablement step runs
its own fresh audit against core's current master and enables a repository only if
that audit's ready list names it; it accepts no ready list from its caller.
"""

from __future__ import annotations

import json
import os
import sys
from argparse import ArgumentParser
from collections.abc import Callable, Sequence
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402

from livespec_dev_tooling._incident_fleet_types import FleetAudit  # noqa: E402
from livespec_dev_tooling.fleet._manifest_git import default_git_reader  # noqa: E402
from livespec_dev_tooling.incident_fleet_command import (  # noqa: E402
    exit_code,
    render_report,
    run_fleet_audit,
)
from livespec_dev_tooling.incident_fleet_sources import (  # noqa: E402
    CLAIMS_RELATIVE_PATH,
    core_manifest_reader,
    host_serving_reader,
    installed_controller,
    load_claims,
)

__all__: list[str] = ["enable_repository", "main"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
_DEFAULT_OWNER = "thewoolleyman"


def enable_repository(*, repository: str, audit: FleetAudit, state_dir: Path) -> tuple[int, str]:
    """Enable only a ready repository; refuse by name with the audit's recorded evidence gap."""
    if repository not in audit.ready_repositories:
        gaps = [f for f in audit.findings if f.startswith(f"{repository}:")] or [
            "no audited serving-version evidence classifies it (or the manifest is unauthenticated)"
        ]
        return 1, f"refused\t{repository}: missing evidence: {'; '.join(gaps)}"
    state_dir.mkdir(parents=True, exist_ok=True)
    record = state_dir / f"{repository.replace('/', '__')}.json"
    _ = record.write_text(
        json.dumps({"repository": repository, "manifest_sha256": audit.manifest_sha256}) + "\n",
        encoding="utf-8",
    )
    return 0, f"enabled\t{repository}"


def _fresh_audit(
    *,
    owner: str,
    root: Path,
    projects_root: Path,
    read_manifest: Callable[[], str | None] | None,
    read_serving: Callable[[str, str], str | None] | None,
) -> tuple[FleetAudit, tuple[str, ...]]:
    claims = load_claims(path=root / CLAIMS_RELATIVE_PATH)
    controllers = os.environ.get("LIVESPEC_INCIDENT_CONTROLLER_CONFIG_ROOT")
    audit = run_fleet_audit(
        read_manifest=read_manifest or core_manifest_reader(owner=owner, run=default_git_reader),
        claims=() if isinstance(claims, Failure) else claims.unwrap(),
        read_serving=read_serving
        or host_serving_reader(
            projects_root=projects_root,
            controller_config_root=None if controllers is None else Path(controllers),
            run=default_git_reader,
            load_controller=lambda config: installed_controller(config=config),
        ),
    )
    notes = (
        (f"finding\tevidence claims: {claims.failure()}",) if isinstance(claims, Failure) else ()
    )
    return audit, notes


def main(
    *,
    argv: Sequence[str],
    root: Path,
    projects_root: Path,
    state_dir: Path,
    read_manifest: Callable[[], str | None] | None = None,
    read_serving: Callable[[str, str], str | None] | None = None,
) -> int:
    """Run `audit` or `enable REPOSITORY`; the exit code is the command's verdict."""
    parser = ArgumentParser(prog="incident_fleet_cli")
    _ = parser.add_argument("--owner", default=_DEFAULT_OWNER)
    commands = parser.add_subparsers(dest="command", required=True)
    _ = commands.add_parser("audit")
    _ = commands.add_parser("enable").add_argument("repository")
    args = parser.parse_args(list(argv))
    audit, notes = _fresh_audit(
        owner=args.owner,
        root=root,
        projects_root=projects_root,
        read_manifest=read_manifest,
        read_serving=read_serving,
    )
    if args.command == "audit":
        lines = (*render_report(audit=audit), *notes)
        _ = sys.stdout.write("\n".join(lines) + "\n")
        return exit_code(audit=audit) or int(bool(notes))
    status, line = enable_repository(
        repository=str(args.repository), audit=audit, state_dir=state_dir
    )
    _ = (sys.stdout if status == 0 else sys.stderr).write(line + "\n")
    return status


if __name__ == "__main__":
    raise SystemExit(
        main(
            argv=sys.argv[1:],
            root=Path.cwd(),
            projects_root=Path(os.environ.get("LIVESPEC_FLEET_PROJECTS_ROOT", "/data/projects")),
            state_dir=Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
            / "livespec"
            / "incident-enabled",
        )
    )
