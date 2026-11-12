"""Record scoped affected-tests gate evidence for a later suite-green replay."""

from __future__ import annotations

import argparse
import datetime
import json
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple, cast

from livespec_dev_tooling.gate_remote_invocation import Failure, default_gate_command_runner

__all__: list[str] = [
    "AffectedTestsEvidence",
    "read_affected_tests_evidence",
    "run_affected_tests_gate",
]

_RECORD_FILE = "livespec-affected-tests.json"


class AffectedTestsEvidence(NamedTuple):
    """A scoped gate's tree, result, selected tests, and stable producer name."""

    tree_hash: str
    outcome: str
    test_paths: tuple[str, ...]
    run_id: str


def _git_path(*, cwd: Path) -> Path:
    """Resolve the worktree-local Git path that stores scoped-gate evidence."""
    result = default_gate_command_runner(
        argv=["git", "rev-parse", "--git-path", _RECORD_FILE], cwd=cwd
    )
    if isinstance(result, Failure) or result.unwrap().returncode != 0:
        raise OSError
    return (cwd / result.unwrap().stdout.strip()).resolve()


def _tree_hash(*, cwd: Path) -> str | None:
    """Return the exact index tree the scoped gate starts against, if readable."""
    result = default_gate_command_runner(argv=["git", "write-tree"], cwd=cwd)
    if isinstance(result, Failure) or result.unwrap().returncode != 0:
        return None
    return result.unwrap().stdout.strip() or None


def _selected_paths(*, paths_file: Path) -> tuple[str, ...]:
    """Read the gate's actual selected test paths, preserving their order."""
    try:
        return tuple(path for path in paths_file.read_text(encoding="utf-8").splitlines() if path)
    except (OSError, UnicodeDecodeError):
        return ()


def _execute(*, command: list[str], cwd: Path) -> int:
    """Run the gate unchanged and return exactly its exit status."""
    result = default_gate_command_runner(argv=command, cwd=cwd, stream=True)
    if isinstance(result, Failure):
        return 127
    return result.unwrap().returncode


def _record(*, cwd: Path, tree_hash: str | None, outcome: str, test_paths: tuple[str, ...]) -> None:
    """Persist advisory evidence without changing the scoped gate's verdict."""
    if tree_hash is None:
        return
    captured_at = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_id = f"affected-tests:{captured_at}:{tree_hash}"
    payload = {
        "tree_hash": tree_hash,
        "outcome": outcome,
        "test_paths": list(test_paths),
        "run_id": run_id,
    }
    try:
        _ = _git_path(cwd=cwd).write_text(json.dumps(payload), encoding="utf-8")
    except OSError:
        return


def run_affected_tests_gate(
    *,
    command: list[str],
    cwd: Path,
    paths_file: Path,
    execute: Callable[..., int] = _execute,
    record: Callable[..., None] = _record,
    tree_hash: Callable[..., str | None] = _tree_hash,
) -> int:
    """Run one scoped gate and record the tree, outcome, and tests it selected."""
    tree = tree_hash(cwd=cwd)
    status = execute(command=command, cwd=cwd)
    record(
        cwd=cwd,
        tree_hash=tree,
        outcome="passed" if status == 0 else "failed",
        test_paths=_selected_paths(paths_file=paths_file),
    )
    return status


def read_affected_tests_evidence(*, cwd: Path) -> AffectedTestsEvidence | None:
    """Read a complete scoped record, rejecting malformed and empty evidence."""
    try:
        value = json.loads(_git_path(cwd=cwd).read_text(encoding="utf-8"))
        record = cast("dict[str, object]", value) if isinstance(value, dict) else {}
        tree_hash = record.get("tree_hash")
        outcome = record.get("outcome")
        paths_value = record.get("test_paths")
        run_id = record.get("run_id")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if (
        not isinstance(tree_hash, str)
        or not isinstance(outcome, str)
        or not isinstance(paths_value, list)
        or not isinstance(run_id, str)
        or not tree_hash
        or not run_id
        or any(not isinstance(path, str) or not path for path in cast("list[object]", paths_value))
    ):
        return None
    paths = cast("list[str]", paths_value)
    return AffectedTestsEvidence(tree_hash, outcome, tuple(paths), run_id)


def main() -> int:
    """Run the command after ``--`` and retain its scoped-gate evidence."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--paths-file", required=True, type=Path)
    _ = parser.add_argument("command", nargs=argparse.REMAINDER)
    parsed = parser.parse_args()
    command = list(parsed.command)
    if command[:1] == ["--"]:
        command = command[1:]
    if not command:
        parser.error("a scoped gate command is required after --")
    return run_affected_tests_gate(command=command, cwd=Path.cwd(), paths_file=parsed.paths_file)


if __name__ == "__main__":
    raise SystemExit(main())
