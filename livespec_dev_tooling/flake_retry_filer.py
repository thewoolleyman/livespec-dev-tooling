"""File one root-fix work item for every untracked flake-retry node id.

Run this host-side command through ``/usr/local/bin/with-livespec-env.sh`` so
its ``bd`` calls reach the repository's live Beads tenant:

``with-livespec-env.sh -- uv run python -m livespec_dev_tooling.flake_retry_filer``.
"""

from __future__ import annotations

import argparse
import json
import sys
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

__all__: list[str] = ["file_root_fixes", "main"]

_RETRY_RECORDS_DIR = Path("tmp") / "flake-retries"
_ROOT_FIX_PREFIX = "root-fix: "
_DEFINITION_OF_DONE_REFERENCE = "## Testing approach"


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


def _create_root_fix(*, nodeid: str, repo_root: Path, runner: GateCommandRunner) -> None:
    """Create the root-fix item whose title is also the de-duplication key."""
    _ = _command_result(
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
        ],
        repo_root=repo_root,
        runner=runner,
    )


def file_root_fixes(*, repo_root: Path, runner: GateCommandRunner) -> tuple[str, ...]:
    """File root fixes for retry records that have no open root-fix item."""
    nodeids = _retry_nodeids(repo_root=repo_root)
    existing = _open_root_fix_nodeids(repo_root=repo_root, runner=runner)
    filed: list[str] = []
    for nodeid in nodeids:
        if nodeid in existing:
            continue
        _create_root_fix(nodeid=nodeid, repo_root=repo_root, runner=runner)
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


def main(*, argv: Sequence[str] | None = None) -> int:
    """File missing root fixes from retry records below the selected repository root."""
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    arguments = parser.parse_args(argv)
    filed = file_root_fixes(repo_root=arguments.repo_root, runner=default_gate_command_runner)
    _ = _logger().info("filed flake root fixes", nodeids=filed, count=len(filed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
