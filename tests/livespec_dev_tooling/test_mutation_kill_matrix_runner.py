"""Tests for the mutmut-backed Rule-26 kill-matrix runner."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping
from pathlib import Path
from subprocess import CompletedProcess

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runner_exposes_the_mutmut_kill_matrix_operation() -> None:
    """The portable reporter provides the executable Python adapter."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")

    assert callable(module.run_kill_matrix)


def test_runner_executes_every_test_against_every_generated_mutant(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The mutmut adapter attributes individual test kills in the portable report."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    assert hasattr(module, "run_kill_matrix")

    calls: list[tuple[list[str], Path, str | None]] = []
    results = iter(
        [
            CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "    package.module.first__mutmut_1: killed\n"
                    "    package.module.second__mutmut_1: survived\n"
                ),
                stderr="",
            ),
            CompletedProcess(
                args=[],
                returncode=0,
                stdout=(
                    "tests/test_package.py::test_first\n"
                    "tests/test_package.py::test_second\n"
                    "\n2 tests collected in 0.01s\n"
                ),
                stderr="",
            ),
            CompletedProcess(args=[], returncode=1, stdout="", stderr=""),
            CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]
    )

    def fake_run(
        *_args: object,
        args: list[str],
        cwd: str,
        env: Mapping[str, str] | None = None,
        **_kwargs: object,
    ) -> CompletedProcess[str]:
        command = args
        mutant = env.get("MUTANT_UNDER_TEST") if env is not None else None
        calls.append((command, Path(cwd), mutant))
        return next(results)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    report = module.run_kill_matrix(
        repo_root=tmp_path,
        report_path=tmp_path / "reports" / "mutation-kill-matrix.json",
        source_revision="abc123",
    )

    assert report.to_dict()["mutants_generated"] == 2
    assert report.to_dict()["mutants"][0]["killed_by"] == ["tests/test_package.py::test_first"]
    assert report.to_dict()["surviving_mutants"] == ["package.module.second__mutmut_1"]
    assert report.to_dict()["redundancy_candidates"] == ["tests/test_package.py::test_second"]
    assert [call[2] for call in calls[3:]] == [
        "package.module.first__mutmut_1",
        "package.module.first__mutmut_1",
        "package.module.second__mutmut_1",
        "package.module.second__mutmut_1",
    ]


def test_runner_refuses_unusable_mutmut_measurements(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Generation, enumeration, and collection failures cannot create a report."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")

    def failed_generation(
        *_args: object, args: list[str], cwd: Path, **_kwargs: object
    ) -> CompletedProcess[str]:
        _ = (args, cwd)
        return CompletedProcess(args=[], returncode=2, stdout="", stderr="")

    monkeypatch.setattr(module, "run_command", failed_generation)
    with pytest.raises(ValueError, match="mutmut failed"):
        _ = module.run_kill_matrix(
            repo_root=tmp_path,
            report_path=tmp_path / "report.json",
            source_revision="abc123",
        )

    responses = iter(
        [
            CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]
    )

    def empty_results(
        *_args: object, args: list[str], cwd: Path, **_kwargs: object
    ) -> CompletedProcess[str]:
        _ = (args, cwd)
        return next(responses)

    monkeypatch.setattr(module, "run_command", empty_results)
    with pytest.raises(ValueError, match="empty mutant set"):
        _ = module.run_kill_matrix(
            repo_root=tmp_path,
            report_path=tmp_path / "report.json",
            source_revision="abc123",
        )


def test_runner_refuses_when_pytest_collects_no_tests(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A report needs a test suite as well as a non-empty mutant set."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    responses = iter(
        [
            CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
            CompletedProcess(
                args=[],
                returncode=0,
                stdout="    package.module.first__mutmut_1: killed\n",
                stderr="",
            ),
            CompletedProcess(args=[], returncode=0, stdout="", stderr=""),
        ]
    )

    def no_tests(
        *_args: object, args: list[str], cwd: Path, **_kwargs: object
    ) -> CompletedProcess[str]:
        _ = (args, cwd)
        return next(responses)

    monkeypatch.setattr(module, "run_command", no_tests)
    with pytest.raises(ValueError, match="did not collect tests"):
        _ = module.run_kill_matrix(
            repo_root=tmp_path,
            report_path=tmp_path / "report.json",
            source_revision="abc123",
        )


def test_main_writes_the_requested_report_path(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The on-demand CLI resolves the revision and delegates to the runner."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    calls: list[tuple[Path, Path, str]] = []

    def revision(
        *_args: object, args: list[str], cwd: Path, **_kwargs: object
    ) -> CompletedProcess[str]:
        assert args == ["git", "rev-parse", "HEAD"]
        assert cwd == tmp_path
        return CompletedProcess(args=[], returncode=0, stdout="abc123\n", stderr="")

    def fake_runner(*, repo_root: Path, report_path: Path, source_revision: str) -> object:
        calls.append((repo_root, report_path, source_revision))
        return object()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(module, "run_command", revision)
    monkeypatch.setattr(module, "run_kill_matrix", fake_runner)
    monkeypatch.setattr(sys, "argv", ["mutation-kill-matrix", "--report", "out/report.json"])

    assert module.main() == 0
    assert calls == [(tmp_path, tmp_path / "out" / "report.json", "abc123")]


def test_command_runner_passes_through_the_optional_environment(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The adapter invokes subprocess with text capture and its supplied environment."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    observed: dict[str, object] = {}

    def fake_subprocess_run(**kwargs: object) -> CompletedProcess[str]:
        observed.update(kwargs)
        return CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_subprocess_run)
    environment = {"MUTANT_UNDER_TEST": "mutant"}
    _ = module.run_command(args=["pytest"], cwd=tmp_path, env=environment)

    assert observed["args"] == ["pytest"]
    assert observed["cwd"] == str(tmp_path)
    assert observed["env"] == environment
