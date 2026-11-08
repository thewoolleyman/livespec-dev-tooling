"""Repository-local process work for the fleet test baseline collector."""

from __future__ import annotations

import json
import platform
import re
import socket
import subprocess
import time
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict

__all__: list[str] = ["measure_repositories", "run_command"]


class RepositoryRow(TypedDict):
    """One JSON-ready repository measurement."""

    name: str
    path: str
    ecosystem: str
    test_count: int
    count_command: str
    test_command: str
    runtime_seconds: float
    test_exit_status: int
    toolchain_versions: dict[str, str]


Runner = Callable[..., subprocess.CompletedProcess[str]]

_PYTEST_COUNT_COMMAND = (
    "pytest",
    "--collect-only",
    "-q",
    "-p",
    "no:cacheprovider",
)
_PYTEST_TEST_COMMAND = ("pytest", "-q")
_MISE_UV = ("mise", "exec", "--", "uv", "run")
_NEXTEST_LIST_COMMAND = ("cargo", "nextest", "list", "--message-format", "json")
_NEXTEST_TEST_COMMAND = ("cargo", "nextest", "run", "--workspace", "--all-features")
_PYTEST_COUNT = re.compile(r"(\d+) tests? collected")


def run_command(*, command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one repository-local tool command and retain its text result."""
    return subprocess.run(command, cwd=cwd, capture_output=True, check=True, text=True)


def _test_exit_status(*, command: tuple[str, ...], cwd: Path, runner: Runner) -> int:
    """Run one test-only command and return its exit status, keeping a red suite measurable."""
    try:
        return runner(command=command, cwd=cwd).returncode
    except subprocess.CalledProcessError as failed:
        return failed.returncode


def _command_text(*, command: tuple[str, ...]) -> str:
    """Render a report command exactly as the collector executes it."""
    return " ".join(command)


def _pytest_count(*, output: str) -> int:
    """Read pytest's exact collection total from its quiet collector output."""
    return int(_PYTEST_COUNT.findall(output)[0])


def _python_row(*, path: Path, runner: Runner) -> RepositoryRow:
    """Measure one Python repository using its pinned uv environment."""
    collected = runner(command=(*_MISE_UV, *_PYTEST_COUNT_COMMAND), cwd=path)
    started = time.perf_counter()
    exit_status = _test_exit_status(
        command=(*_MISE_UV, *_PYTEST_TEST_COMMAND), cwd=path, runner=runner
    )
    runtime_seconds = time.perf_counter() - started
    pytest_version = runner(command=(*_MISE_UV, "pytest", "--version"), cwd=path)
    python_version = runner(command=(*_MISE_UV, "python", "--version"), cwd=path)
    return {
        "name": path.name,
        "path": str(path),
        "ecosystem": "python",
        "test_count": _pytest_count(output=collected.stdout),
        "count_command": _command_text(command=(*_MISE_UV, *_PYTEST_COUNT_COMMAND)),
        "test_command": _command_text(command=(*_MISE_UV, *_PYTEST_TEST_COMMAND)),
        "runtime_seconds": runtime_seconds,
        "test_exit_status": exit_status,
        "toolchain_versions": {
            "pytest": pytest_version.stdout.strip(),
            "python": python_version.stdout.strip(),
        },
    }


def _nextest_count(*, output: str) -> int:
    """Count nextest's one-JSON-object-per-test-list-entry output."""
    return sum(
        1
        for line in output.splitlines()
        if isinstance(json.loads(line), dict) and json.loads(line).get("type") == "test"
    )


def _rust_row(*, path: Path, runner: Runner) -> RepositoryRow:
    """Measure a Rust workspace with cargo nextest."""
    collected = runner(command=_NEXTEST_LIST_COMMAND, cwd=path)
    started = time.perf_counter()
    exit_status = _test_exit_status(command=_NEXTEST_TEST_COMMAND, cwd=path, runner=runner)
    runtime_seconds = time.perf_counter() - started
    cargo_version = runner(command=("cargo", "--version"), cwd=path)
    return {
        "name": path.name,
        "path": str(path),
        "ecosystem": "rust",
        "test_count": _nextest_count(output=collected.stdout),
        "count_command": _command_text(command=_NEXTEST_LIST_COMMAND),
        "test_command": _command_text(command=_NEXTEST_TEST_COMMAND),
        "runtime_seconds": runtime_seconds,
        "test_exit_status": exit_status,
        "toolchain_versions": {"cargo": cargo_version.stdout.strip()},
    }


def _shell_scripts(*, path: Path) -> tuple[Path, ...]:
    """Return every shell test the shell-only repository will execute."""
    return tuple(sorted(path.rglob("*.test.sh")))


def _shell_row(*, path: Path, runner: Runner) -> RepositoryRow:
    """Measure a shell-tested repository one executable script at a time.

    Every script runs even after one fails; the row's exit status is the first non-zero one.
    """
    scripts = _shell_scripts(path=path)
    started = time.perf_counter()
    statuses = [
        _test_exit_status(command=("bash", str(script.relative_to(path))), cwd=path, runner=runner)
        for script in scripts
    ]
    runtime_seconds = time.perf_counter() - started
    bash_version = runner(command=("env", "bash", "--version"), cwd=path)
    return {
        "name": path.name,
        "path": str(path),
        "ecosystem": "shell",
        "test_count": len(scripts),
        "count_command": "one per executed *.test.sh script",
        "test_command": "; ".join(
            _command_text(command=("bash", str(script.relative_to(path)))) for script in scripts
        ),
        "runtime_seconds": runtime_seconds,
        "test_exit_status": next((status for status in statuses if status), 0),
        "toolchain_versions": {"bash": bash_version.stdout.splitlines()[0]},
    }


def _repository_row(*, path: Path, runner: Runner) -> RepositoryRow:
    """Select the stated counting method from a repository's test layout."""
    if path.joinpath("Cargo.toml").is_file():
        return _rust_row(path=path, runner=runner)
    if _shell_scripts(path=path):
        return _shell_row(path=path, runner=runner)
    return _python_row(path=path, runner=runner)


def measure_repositories(*, paths: tuple[Path, ...], runner: Runner) -> dict[str, object]:
    """Measure fleet repository baselines and return a JSON-ready report."""
    rows = [_repository_row(path=path, runner=runner) for path in paths]
    return {
        "host": {"hostname": socket.gethostname(), "platform": platform.platform()},
        "timing_method": "time.perf_counter around each repository test-only command",
        "repositories": rows,
        "fleet_totals": {
            "test_count": sum(row["test_count"] for row in rows),
            "runtime_seconds": sum(row["runtime_seconds"] for row in rows),
        },
    }
