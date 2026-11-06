"""Tests for the on-demand fleet test baseline collector."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "fleet_test_baseline.py"


def _baseline() -> ModuleType:
    """Import the collector after proving its shipped module exists."""
    assert _MODULE_PATH.is_file(), (
        "the fleet baseline collector must ship as " "livespec_dev_tooling/fleet_test_baseline.py"
    )
    return importlib.import_module("livespec_dev_tooling.fleet_test_baseline")


def test_python_repository_reports_exact_collection_and_test_only_timing(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pytest repository reports its collection, test-only command, and timing method."""
    repository = tmp_path / "pytest-suite"
    repository.mkdir()
    module = _baseline()

    def fake_run(*, command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        assert cwd == repository
        if "--collect-only" in command:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="5 tests collected in 0.01s\n",
                stderr="",
            )
        if "--version" in command:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="pytest 8.3.4\n",
                stderr="",
            )
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "_run", fake_run)

    report = module.measure_repositories(paths=(repository,))

    row = report["repositories"][0]
    assert row["test_count"] == 5
    assert row["count_command"] == "pytest --collect-only -q -p no:cacheprovider"
    assert row["test_command"] == "uv run pytest -q"
    assert row["runtime_seconds"] >= 0
    assert report["timing_method"] == "time.perf_counter around each repository test-only command"
    assert row["toolchain_versions"]["pytest"] == "pytest 8.3.4"


def test_repository_runner_executes_the_declared_command(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default runner uses a structured subprocess in the repository cwd."""
    _ = _baseline()
    runner = importlib.import_module("livespec_dev_tooling.fleet._test_baseline")
    observed: dict[str, object] = {}

    def fake_subprocess_run(
        command: tuple[str, ...], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        observed["command"] = command
        observed.update(kwargs)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_subprocess_run)

    result = runner.run_command(command=("mise", "exec", "--", "uv", "run", "pytest"), cwd=tmp_path)

    assert result.stdout == "ok"
    assert observed == {
        "command": ("mise", "exec", "--", "uv", "run", "pytest"),
        "cwd": tmp_path,
        "capture_output": True,
        "check": True,
        "text": True,
    }
