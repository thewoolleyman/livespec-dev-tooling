"""Repository-local process work for the fleet test baseline collector."""

from __future__ import annotations

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
_PYTEST_COUNT = re.compile(r"(\d+) tests? collected")


def run_command(*, command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one repository-local tool command and retain its text result."""
    return subprocess.run(command, cwd=cwd, capture_output=True, check=True, text=True)


def _command_text(*, command: tuple[str, ...]) -> str:
    """Render a report command without its repository toolchain launcher."""
    return " ".join(command)


def _pytest_count(*, output: str) -> int:
    """Read pytest's exact collection total from its quiet collector output."""
    return int(_PYTEST_COUNT.findall(output)[0])


def _python_row(*, path: Path, runner: Runner) -> RepositoryRow:
    """Measure one Python repository using its pinned uv environment."""
    collected = runner(command=(*_MISE_UV, *_PYTEST_COUNT_COMMAND), cwd=path)
    started = time.perf_counter()
    _ = runner(command=(*_MISE_UV, *_PYTEST_TEST_COMMAND), cwd=path)
    runtime_seconds = time.perf_counter() - started
    pytest_version = runner(command=(*_MISE_UV, "pytest", "--version"), cwd=path)
    python_version = runner(command=(*_MISE_UV, "python", "--version"), cwd=path)
    return {
        "name": path.name,
        "path": str(path),
        "ecosystem": "python",
        "test_count": _pytest_count(output=collected.stdout),
        "count_command": _command_text(command=_PYTEST_COUNT_COMMAND),
        "test_command": _command_text(command=("uv", "run", *_PYTEST_TEST_COMMAND)),
        "runtime_seconds": runtime_seconds,
        "toolchain_versions": {
            "pytest": pytest_version.stdout.strip(),
            "python": python_version.stdout.strip(),
        },
    }


def measure_repositories(*, paths: tuple[Path, ...], runner: Runner) -> dict[str, object]:
    """Measure Python repository baselines and return a JSON-ready fleet report."""
    rows = [_python_row(path=path, runner=runner) for path in paths]
    return {
        "host": {"hostname": socket.gethostname(), "platform": platform.platform()},
        "timing_method": "time.perf_counter around each repository test-only command",
        "repositories": rows,
        "fleet_totals": {
            "test_count": sum(row["test_count"] for row in rows),
            "runtime_seconds": sum(row["runtime_seconds"] for row in rows),
        },
    }
