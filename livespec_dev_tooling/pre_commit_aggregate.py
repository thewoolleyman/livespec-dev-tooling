"""Run a local pre-commit aggregate and record qualified same-tree evidence."""

from __future__ import annotations

import argparse
import datetime
import hashlib
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — shipped vendored dependency path.

from livespec_dev_tooling.green_token import write_pre_commit_evidence  # noqa: E402

__all__: list[str] = ["AggregateResult", "main", "run_aggregate"]


@dataclass(frozen=True, kw_only=True)
class AggregateResult:
    """The aggregate command's exit status and complete emitted output."""

    exit_status: int
    output: bytes


def _execute(*, command: list[str], cwd: Path) -> AggregateResult:
    """Run the named aggregate, preserving its stdout, stderr, and status."""
    completed = subprocess.run(  # noqa: S603  — the consumer owns the aggregate command.
        command,
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    _ = sys.stdout.buffer.write(completed.stdout)
    _ = sys.stderr.buffer.write(completed.stderr)
    return AggregateResult(
        exit_status=completed.returncode,
        output=completed.stdout + completed.stderr,
    )


def _git_answer(*, argv: list[str], cwd: Path) -> tuple[int, str]:
    """Return one git command's status and stdout, treating an unreadable tree as false."""
    try:
        completed = subprocess.run(  # noqa: S603  — caller supplies fixed git probes.
            argv, cwd=cwd, capture_output=True, check=False, text=True
        )
    except OSError:
        return (1, "")
    return (completed.returncode, completed.stdout)


def _record(*, cwd: Path, run_id: str, output_checksum: str, tree_hash: str) -> None:
    """Persist advisory pre-commit evidence without changing the aggregate's result."""
    _ = write_pre_commit_evidence(
        cwd=cwd,
        log=structlog.get_logger("pre_commit_aggregate"),
        run_id=run_id,
        output_checksum=output_checksum,
        tree_hash=tree_hash,
    )


def _tree_hash(*, cwd: Path, git_answer: Callable[..., tuple[int, str]]) -> str | None:
    """Read the index tree, or None when the repository cannot establish one."""
    status, output = git_answer(argv=["git", "write-tree"], cwd=cwd)
    tree_hash = output.strip()
    return tree_hash if status == 0 and tree_hash else None


def _qualifies(
    *,
    cwd: Path,
    before_tree: str | None,
    result: AggregateResult,
    git_answer: Callable[..., tuple[int, str]],
) -> bool:
    """Say whether this full aggregate may stand in for suite-green on its index tree."""
    if result.exit_status != 0 or before_tree is None:
        return False
    if git_answer(argv=["git", "diff", "--quiet"], cwd=cwd)[0] != 0:
        return False
    status, untracked = git_answer(
        argv=["git", "ls-files", "--others", "--exclude-standard"], cwd=cwd
    )
    if status != 0 or untracked.strip():
        return False
    return _tree_hash(cwd=cwd, git_answer=git_answer) == before_tree


def run_aggregate(
    *,
    command: list[str],
    cwd: Path,
    execute: Callable[..., AggregateResult] = _execute,
    git_answer: Callable[..., tuple[int, str]] = _git_answer,
    record: Callable[..., None] = _record,
) -> int:
    """Run a consumer's aggregate and record only a passing, clean, unchanged-tree verdict."""
    before_tree = _tree_hash(cwd=cwd, git_answer=git_answer)
    result = execute(command=command, cwd=cwd)
    if _qualifies(
        cwd=cwd,
        before_tree=before_tree,
        result=result,
        git_answer=git_answer,
    ):
        checksum = f"sha256:{hashlib.sha256(result.output).hexdigest()}"
        captured_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        record(
            cwd=cwd,
            run_id=f"pre-commit-aggregate:{captured_at}:{before_tree}",
            output_checksum=checksum,
            tree_hash=before_tree,
        )
    return result.exit_status


def main() -> int:
    """Run the aggregate command supplied after ``--`` from the current repository root."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("command", nargs=argparse.REMAINDER)
    parsed = parser.parse_args()
    command = list(parsed.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("an aggregate command is required after --")
    return run_aggregate(command=command, cwd=Path.cwd())


if __name__ == "__main__":
    raise SystemExit(main())
