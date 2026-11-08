"""File one root-fix work item for every untracked flake-retry node id.

Run this host-side command through ``/usr/local/bin/with-livespec-env.sh`` so
its ``bd`` calls reach the repository's live Beads tenant:

``with-livespec-env.sh -- uv run python -m livespec_dev_tooling.flake_retry_filer``.
"""

from __future__ import annotations

import argparse
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
# Runs inside the registered orchestrator build so the filer calls the one shared
# intake Definition-of-Ready primitive instead of copying its routing rules. Every
# gate answer is true: a root fix is one coherent, test-verified, repo-targeted fix.
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
    sys.exit(1)
sys.stdout.write(f"{unsafe_perform_io(routed.unwrap())}\\n")
"""


def _retry_nodeids(*, repo_root: Path) -> tuple[str, ...]:
    """Return each recorded node id once, in deterministic order."""
    nodeids: set[str] = set()
    for record_path in sorted((repo_root / _RETRY_RECORDS_DIR).glob("*.jsonl")):
        for line in record_path.read_text(encoding="utf-8").splitlines():
            record = cast("dict[str, str]", json.loads(line))
            nodeids.add(record["nodeid"])
    return tuple(sorted(nodeids))


def _command_result(
    *, argv: list[str], repo_root: Path, runner: GateCommandRunner
) -> GateCommandResult:
    """Run a required host ledger command, preserving an invocation failure."""
    outcome = runner(argv=argv, cwd=repo_root)
    if isinstance(outcome, Failure):
        raise OSError
    result = outcome.unwrap()
    if result.returncode != 0:
        raise OSError
    return result


def _open_root_fix_nodeids(*, repo_root: Path, runner: GateCommandRunner) -> set[str]:
    """Read node ids that already have a non-closed root-fix item."""
    result = _command_result(
        argv=["bd", "list", "--status", "all", "--json"],
        repo_root=repo_root,
        runner=runner,
    )
    parsed = cast("object", json.loads(result.stdout))
    if not isinstance(parsed, list):
        raise TypeError
    open_nodeids: set[str] = set()
    for item in cast("list[object]", parsed):
        if not isinstance(item, dict):
            continue
        item_record = cast("dict[str, object]", item)
        if item_record.get("status") == "closed":
            continue
        title = item_record.get("title")
        if isinstance(title, str) and title.startswith(_ROOT_FIX_PREFIX):
            open_nodeids.add(title.removeprefix(_ROOT_FIX_PREFIX))
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


def _created_item_id(*, stdout: str) -> str:
    """Read the server-assigned id out of a ``bd create --json`` body."""
    parsed = cast("object", json.loads(stdout))
    if isinstance(parsed, list):
        records = cast("list[object]", parsed)
        parsed = records[0] if records else None
    if isinstance(parsed, dict):
        item_id = cast("dict[str, object]", parsed).get("id")
        if isinstance(item_id, str):
            return item_id
    raise TypeError


def _create_root_fix(*, nodeid: str, repo_root: Path, runner: GateCommandRunner) -> str:
    """Create the root-fix item whose title is also the de-duplication key."""
    result = _command_result(
        argv=[
            "bd",
            "create",
            f"{_ROOT_FIX_PREFIX}{nodeid}",
            "--description",
            _root_fix_description(nodeid=nodeid),
            "--type",
            "bug",
            "--priority",
            "0",
            "--json",
        ],
        repo_root=repo_root,
        runner=runner,
    )
    return _created_item_id(stdout=result.stdout)


def _route_through_intake(
    *, item_id: str, plugin_root: Path, repo_root: Path, runner: GateCommandRunner
) -> None:
    """Triage the filed item so it rests in a dispatchable status, not raw ``backlog``."""
    _ = _command_result(
        argv=["python3", "-c", _INTAKE_ROUTING_SNIPPET, str(plugin_root), item_id],
        repo_root=repo_root,
        runner=runner,
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
    *, repo_root: Path, runner: GateCommandRunner, plugin_root: Path
) -> tuple[str, ...]:
    """File root fixes for retry records that have no open root-fix item."""
    nodeids = _retry_nodeids(repo_root=repo_root)
    existing = _open_root_fix_nodeids(repo_root=repo_root, runner=runner)
    filed: list[str] = []
    for nodeid in nodeids:
        if nodeid in existing:
            continue
        item_id = _create_root_fix(nodeid=nodeid, repo_root=repo_root, runner=runner)
        _route_through_intake(
            item_id=item_id, plugin_root=plugin_root, repo_root=repo_root, runner=runner
        )
        filed.append(nodeid)
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
    filed = file_root_fixes(
        repo_root=arguments.repo_root,
        runner=default_gate_command_runner,
        plugin_root=plugin_root,
    )
    _mark_successful_pass(state_dir=arguments.state_dir)
    _ = _logger().info("filed flake root fixes", nodeids=filed, count=len(filed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
