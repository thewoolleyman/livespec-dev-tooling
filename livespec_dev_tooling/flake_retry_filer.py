"""File one root-fix work item for every untracked flake-retry node id.

Run this host-side command through ``/usr/local/bin/with-livespec-env.sh`` so
its ``bd`` calls reach the repository's live Beads tenant:

``with-livespec-env.sh -- uv run python -m livespec_dev_tooling.flake_retry_filer``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.result import Failure  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.gate_remote_invocation import (  # noqa: E402
    GateCommandResult,
    GateCommandRunner,
    default_gate_command_runner,
)

__all__: list[str] = ["file_root_fixes", "main", "registered_plugin_root"]

_RETRY_RECORDS_DIR = Path("tmp") / "flake-retries"
_ROOT_FIX_PREFIX = "root-fix: "
_DEFINITION_OF_DONE_REFERENCE = "## Testing approach"
_PLUGIN_NAME = "livespec-orchestrator-beads-fabro"
_PLUGIN_REGISTRY = Path(".claude") / "plugins" / "installed_plugins.json"
_READER_NAME = "flake-retry-filer"
_DEFAULT_STATE_DIR = Path("/var/lib/livespec/flake-retry-filer")
_DEFAULT_INTERVAL_SECONDS = 900
_COMPLETION_MARKER = "last-successful-pass"
_FILED_RECORDS_LEDGER = "filed-records"
# Runs inside the registered orchestrator build so stranded legacy items can be
# retried through the one shared intake Definition-of-Ready primitive.
_INTAKE_ROUTING_SNIPPET = """\
import sys
from pathlib import Path

plugin_root, item_id = sys.argv[1], sys.argv[2]
sys.path.insert(0, f"{plugin_root}/scripts")
sys.path.insert(0, f"{plugin_root}/scripts/_vendor")
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    apply_intake_dor,
)

routed = apply_intake_dor(
    path=resolve_store_config(cwd=Path.cwd(), work_items_arg=None),
    item_id=item_id,
    checklist=DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    ),
)
if not is_successful(routed):
    sys.stderr.write(f"{item_id}: {unsafe_perform_io(routed.failure())}\\n")
    sys.exit(1)
sys.stdout.write(f"{unsafe_perform_io(routed.unwrap())}\\n")
"""

# New filings use the capture seam, which creates through the claim-token-aware
# store path and routes through intake as one operation.  Root fixes satisfy all
# six gates: each is a coherent, autonomously verifiable, repo-targeted change.
_INTAKE_FILING_SNIPPET = """\
import sys
from datetime import datetime, timezone
from pathlib import Path

plugin_root, nodeid, description = sys.argv[1], sys.argv[2], sys.argv[3]
sys.path.insert(0, f"{plugin_root}/scripts")
sys.path.insert(0, f"{plugin_root}/scripts/_vendor")
from returns.pipeline import is_successful
from returns.unsafe import unsafe_perform_io
from livespec_runtime.work_items.rank import key_between
from livespec_orchestrator_beads_fabro._ids import new_work_item_id
from livespec_orchestrator_beads_fabro._beads_client import make_beads_client
from livespec_orchestrator_beads_fabro.commands._config import resolve_store_config
from livespec_orchestrator_beads_fabro.intake_dor import (
    DefinitionOfReadyChecklist,
    file_captured_work_item,
)
from livespec_orchestrator_beads_fabro.types import WorkItem

path = resolve_store_config(cwd=Path.cwd(), work_items_arg=None)
item = WorkItem(
    id=new_work_item_id(prefix=path.prefix),
    type="bug",
    status="pending-approval",
    title=f"root-fix: {nodeid}",
    description=description,
    origin="freeform",
    gap_id=None,
    rank=key_between(a=None, b=None),
    assignee=None,
    depends_on=(),
    captured_at=datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    resolution=None,
    reason=None,
    audit=None,
    superseded_by=None,
)
routed = file_captured_work_item(
    path=path,
    item=item,
    checklist=DefinitionOfReadyChecklist(
        single_coherent_done=True,
        autonomously_verifiable=True,
        autonomy_tiered=True,
        dependency_linked=True,
        repo_targeted=True,
        above_floor=True,
    ),
)
if not is_successful(routed):
    failure = unsafe_perform_io(routed.failure())
    if make_beads_client(config=path).exists(issue_id=item.id):
        sys.stderr.write(f"{item.id}: {failure}\\n")
    else:
        sys.stderr.write(f"{failure}\\n")
    sys.exit(1)
sys.stdout.write(f"{item.id}\\n")
"""


def _retry_records(*, repo_root: Path) -> tuple[tuple[str, str], ...]:
    """Return each distinct record as a (digest, node id) pair, in deterministic order.

    The digest is the sha256 of the record line, so a record's identity is its
    own content: an unchanged record keeps its digest and a recurrence differs.
    """
    records: dict[str, str] = {}
    for record_path in sorted((repo_root / _RETRY_RECORDS_DIR).glob("*.jsonl")):
        for line in record_path.read_text(encoding="utf-8").splitlines():
            record = cast("dict[str, str]", json.loads(line))
            digest = hashlib.sha256(line.strip().encode("utf-8")).hexdigest()
            records[digest] = record["nodeid"]
    return tuple(sorted(records.items(), key=lambda pair: (pair[1], pair[0])))


def _filed_digests(*, state_dir: Path) -> set[str]:
    """Read the digests of every record an earlier pass already accounted for."""
    ledger = state_dir / _FILED_RECORDS_LEDGER
    if not ledger.is_file():
        return set()
    return set(ledger.read_text(encoding="utf-8").split())


def _remember_filed(*, state_dir: Path, digests: set[str]) -> None:
    """Persist the filed-record digests atomically so a restart keeps them."""
    _ = state_dir.mkdir(parents=True, exist_ok=True)
    ledger = state_dir / _FILED_RECORDS_LEDGER
    pending = ledger.with_name(f"{_FILED_RECORDS_LEDGER}.tmp")
    _ = pending.write_text("".join(f"{digest}\n" for digest in sorted(digests)), encoding="utf-8")
    _ = pending.replace(ledger)


def _command_result(
    *,
    argv: list[str],
    repo_root: Path,
    runner: GateCommandRunner,
    preserve_failure: bool = False,
) -> GateCommandResult:
    """Run a required host ledger command, preserving an invocation failure."""
    outcome = runner(argv=argv, cwd=repo_root)
    if isinstance(outcome, Failure):
        if preserve_failure:
            raise OSError(outcome.failure().detail)
        raise OSError
    result = outcome.unwrap()
    if result.returncode != 0:
        if preserve_failure:
            raise OSError(result.stderr.strip() or result.stdout.strip() or "command failed")
        raise OSError
    return result


def _open_root_fix_nodeids(
    *, repo_root: Path, runner: GateCommandRunner
) -> dict[str, tuple[str | None, bool]]:
    """Read every open root-fix id and whether intake has already triaged it."""
    result = _command_result(
        argv=["bd", "list", "--status", "all", "--json"],
        repo_root=repo_root,
        runner=runner,
    )
    parsed = cast("object", json.loads(result.stdout))
    if not isinstance(parsed, list):
        raise TypeError
    open_nodeids: dict[str, tuple[str | None, bool]] = {}
    for item in cast("list[object]", parsed):
        if not isinstance(item, dict):
            continue
        item_record = cast("dict[str, object]", item)
        if item_record.get("status") == "closed":
            continue
        title = item_record.get("title")
        if isinstance(title, str) and title.startswith(_ROOT_FIX_PREFIX):
            item_id = item_record.get("id")
            labels = item_record.get("labels")
            open_nodeids[title.removeprefix(_ROOT_FIX_PREFIX)] = (
                item_id if isinstance(item_id, str) else None,
                isinstance(labels, list) and "intake:triaged" in labels,
            )
    return open_nodeids


def _root_fix_description(*, nodeid: str) -> str:
    """Return a description whose Definition of Done lets the factory dispatch the item."""
    return (
        f"Root-cause fix for retried test node id: {nodeid}\n"
        "\n"
        "## Definition of Done\n"
        "\n"
        f"References: {_DEFINITION_OF_DONE_REFERENCE}\n"
        "\n"
        f"- Test node id `{nodeid}` passes on its first attempt in a run of the "
        "repository's test suite, with no flake-retry record written for it.\n"
    )


def _file_root_fix_through_intake(
    *, nodeid: str, plugin_root: Path, repo_root: Path, runner: GateCommandRunner
) -> str:
    """File and route one claim-token-aware root fix through the capture seam."""
    result = _command_result(
        argv=[
            "python3",
            "-c",
            _INTAKE_FILING_SNIPPET,
            str(plugin_root),
            nodeid,
            _root_fix_description(nodeid=nodeid),
        ],
        repo_root=repo_root,
        runner=runner,
        preserve_failure=True,
    )
    item_id = result.stdout.strip()
    if not item_id:
        raise TypeError
    return item_id


def _route_through_intake(
    *, item_id: str, plugin_root: Path, repo_root: Path, runner: GateCommandRunner
) -> None:
    """Triage the filed item so it rests in a dispatchable status, not raw ``backlog``."""
    _ = _command_result(
        argv=["python3", "-c", _INTAKE_ROUTING_SNIPPET, str(plugin_root), item_id],
        repo_root=repo_root,
        runner=runner,
        preserve_failure=True,
    )


def registered_plugin_root(*, repo_root: Path, registry: Path) -> Path:
    """Return the orchestrator build the host's plugin registry records for ``repo_root``."""
    parsed = cast("dict[str, object]", json.loads(registry.read_text(encoding="utf-8")))
    plugins = cast("dict[str, list[dict[str, str]]]", parsed["plugins"])
    for key, entries in plugins.items():
        if key.split("@", maxsplit=1)[0] != _PLUGIN_NAME:
            continue
        for entry in entries:
            if Path(entry["projectPath"]).resolve() == repo_root.resolve():
                return Path(entry["installPath"])
    raise OSError


def file_root_fixes(
    *, repo_root: Path, runner: GateCommandRunner, plugin_root: Path, state_dir: Path
) -> tuple[str, ...]:
    """File one root fix per node id with a retry record no earlier pass accounted for.

    A record is accounted for only after its root fix has been routed through
    intake. The memory lives under ``state_dir`` so a closed item never re-files
    an unchanged record, while a new record for the same node id is a recurrence.
    """
    records = _retry_records(repo_root=repo_root)
    filed_digests = _filed_digests(state_dir=state_dir)
    existing = _open_root_fix_nodeids(repo_root=repo_root, runner=runner)
    filed: list[str] = []
    refusals: list[str] = []
    for nodeid in sorted({nodeid for _, nodeid in records}):
        new_digests = {
            digest for digest, record_nodeid in records if record_nodeid == nodeid
        } - filed_digests
        if not new_digests:
            continue
        try:
            if nodeid not in existing:
                _ = _file_root_fix_through_intake(
                    nodeid=nodeid,
                    plugin_root=plugin_root,
                    repo_root=repo_root,
                    runner=runner,
                )
                filed.append(nodeid)
            else:
                item_id, triaged = existing[nodeid]
                if item_id is not None and not triaged:
                    _route_through_intake(
                        item_id=item_id,
                        plugin_root=plugin_root,
                        repo_root=repo_root,
                        runner=runner,
                    )
                    filed.append(nodeid)
        except OSError as failure:
            refusals.append(str(failure))
            continue
        filed_digests |= new_digests
        _remember_filed(state_dir=state_dir, digests=filed_digests)
    if refusals:
        raise OSError("; ".join(refusals))
    return tuple(filed)


def _logger() -> structlog.stdlib.BoundLogger:
    _ = structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("flake_retry_filer")


def _last_successful_pass(*, state_dir: Path) -> Path:
    """Return the durable completion marker for the host-side reader."""
    return state_dir / _COMPLETION_MARKER


def _mark_successful_pass(*, state_dir: Path) -> None:
    """Record a completed pass only after every required filing action succeeds."""
    _ = state_dir.mkdir(parents=True, exist_ok=True)
    _ = _last_successful_pass(state_dir=state_dir).touch()


def _last_pass_age_seconds(*, state_dir: Path) -> int:
    """Return the age of the last completed pass for the operator health check."""
    completed_at = _last_successful_pass(state_dir=state_dir).stat().st_mtime
    return max(0, int(time.time() - completed_at))


def main(*, argv: Sequence[str] | None = None) -> int:
    """File missing root fixes from retry records below the selected repository root."""
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    _ = parser.add_argument("--state-dir", type=Path, default=_DEFAULT_STATE_DIR)
    _ = parser.add_argument("--interval-seconds", type=int, default=_DEFAULT_INTERVAL_SECONDS)
    _ = parser.add_argument("--check-staleness", action="store_true")
    arguments = parser.parse_args(argv)
    if arguments.check_staleness:
        age_seconds = _last_pass_age_seconds(state_dir=arguments.state_dir)
        stale = age_seconds > arguments.interval_seconds
        _ = _logger().warning(
            "flake retry filer staleness",
            reader=_READER_NAME,
            age_seconds=age_seconds,
            stale=stale,
        )
        return int(stale)
    plugin_root = registered_plugin_root(
        repo_root=arguments.repo_root, registry=Path.home() / _PLUGIN_REGISTRY
    )
    try:
        filed = file_root_fixes(
            repo_root=arguments.repo_root,
            runner=default_gate_command_runner,
            plugin_root=plugin_root,
            state_dir=arguments.state_dir,
        )
    except OSError as failure:
        _ = _logger().error("failed to file flake root fixes", error=str(failure))
        return 1
    _mark_successful_pass(state_dir=arguments.state_dir)
    _ = _logger().info("filed flake root fixes", nodeids=filed, count=len(filed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
