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
    assert (
        row["count_command"] == "mise exec -- uv run pytest --collect-only -q -p no:cacheprovider"
    )
    assert row["test_command"] == "mise exec -- uv run pytest -q"
    assert row["runtime_seconds"] >= 0
    assert report["timing_method"] == "time.perf_counter around each repository test-only command"
    assert row["toolchain_versions"]["pytest"] == "pytest 8.3.4"


def test_rust_and_shell_repositories_join_python_in_one_fleet_total(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rust nextest and shell scripts use their stated counting methods."""
    python_repository = tmp_path / "pytest-suite"
    rust_repository = tmp_path / "rust-suite"
    shell_repository = tmp_path / "shell-suite"
    python_repository.mkdir()
    rust_repository.mkdir()
    shell_repository.mkdir()
    _ = rust_repository.joinpath("Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    for name in ("first.test.sh", "second.test.sh"):
        _ = shell_repository.joinpath(name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    module = _baseline()

    def fake_run(*, command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        assert cwd in {python_repository, rust_repository, shell_repository}
        if command[:3] == ("cargo", "nextest", "list"):
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=(
                    '{"type":"test","test_name":"one"}\n'
                    '{"type":"test","test_name":"two"}\n'
                    '{"type":"test","test_name":"three"}\n'
                ),
                stderr="",
            )
        if command[:3] == ("cargo", "nextest", "run"):
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
        if command[0] == "bash":
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
        if "--collect-only" in command:
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout="5 tests collected in 0.01s\n",
                stderr="",
            )
        if "--version" in command:
            versions = {
                "cargo": "cargo 1.82.0",
                "bash": "GNU bash, version 5.2.37",
                "pytest": "pytest 8.3.4",
                "python": "Python 3.12.7",
            }
            return subprocess.CompletedProcess(
                args=command,
                returncode=0,
                stdout=f"{versions[command[-2] if command[-1] == '--version' else command[0]]}\n",
                stderr="",
            )
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module, "_run", fake_run)

    report = module.measure_repositories(
        paths=(python_repository, rust_repository, shell_repository)
    )

    rows = {row["name"]: row for row in report["repositories"]}
    assert rows["pytest-suite"]["test_count"] == 5
    assert rows["rust-suite"]["test_count"] == 3
    assert rows["rust-suite"]["count_command"] == "cargo nextest list --message-format json"
    assert rows["rust-suite"]["test_command"] == "cargo nextest run --workspace --all-features"
    assert rows["shell-suite"]["test_count"] == 2
    assert rows["shell-suite"]["count_command"] == "one per executed *.test.sh script"
    assert report["fleet_totals"]["test_count"] == 10
    assert report["fleet_totals"]["runtime_seconds"] == sum(
        row["runtime_seconds"] for row in report["repositories"]
    )


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


def _red_fleet(*, root: Path) -> tuple[Path, Path, Path]:
    """Create a pytest, a Rust and a three-script shell fixture repository."""
    python_repository = root / "red-pytest-suite"
    rust_repository = root / "rust-suite"
    shell_repository = root / "red-shell-suite"
    for repository in (python_repository, rust_repository, shell_repository):
        repository.mkdir()
    _ = rust_repository.joinpath("Cargo.toml").write_text("[workspace]\n", encoding="utf-8")
    for name in ("first.test.sh", "second.test.sh", "third.test.sh"):
        _ = shell_repository.joinpath(name).write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    return python_repository, rust_repository, shell_repository


def test_a_red_test_command_is_measured_and_the_fleet_run_continues(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-zero test command is timed, its exit status kept, and every repository reported."""
    paths = _red_fleet(root=tmp_path)
    module = _baseline()
    executed_scripts: list[str] = []

    def fake_run(*, command: tuple[str, ...], cwd: Path) -> subprocess.CompletedProcess[str]:
        assert cwd in paths
        if command[:3] == ("cargo", "nextest", "list"):
            return subprocess.CompletedProcess(
                args=command, returncode=0, stdout='{"type":"test"}\n', stderr=""
            )
        if command[0] == "bash":
            executed_scripts.append(command[1])
            if command[1] == "second.test.sh":
                raise subprocess.CalledProcessError(returncode=3, cmd=command)
            return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")
        if "--collect-only" in command:
            return subprocess.CompletedProcess(
                args=command, returncode=0, stdout="7 tests collected in 0.01s\n", stderr=""
            )
        if command[-2:] == ("pytest", "-q"):
            raise subprocess.CalledProcessError(returncode=1, cmd=command)
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="v 1\n", stderr="")

    monkeypatch.setattr(module, "_run", fake_run)

    report = module.measure_repositories(paths=paths)

    rows = {row["name"]: row for row in report["repositories"]}
    assert set(rows) == {"red-pytest-suite", "rust-suite", "red-shell-suite"}
    assert rows["red-pytest-suite"]["test_count"] == 7
    assert rows["red-pytest-suite"]["test_exit_status"] == 1
    assert rows["red-pytest-suite"]["runtime_seconds"] >= 0
    assert rows["rust-suite"]["test_exit_status"] == 0
    assert executed_scripts == ["first.test.sh", "second.test.sh", "third.test.sh"]
    assert rows["red-shell-suite"]["test_count"] == 3
    assert rows["red-shell-suite"]["test_exit_status"] == 3
    assert report["fleet_totals"]["test_count"] == 7 + 1 + 3
    assert report["fleet_totals"]["runtime_seconds"] == sum(
        row["runtime_seconds"] for row in report["repositories"]
    )
