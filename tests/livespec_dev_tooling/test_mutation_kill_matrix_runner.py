"""Tests for the mutmut-backed Rule-26 kill-matrix runner."""

from __future__ import annotations

import importlib
import sys
from collections.abc import Mapping
from pathlib import Path
from subprocess import CompletedProcess

import pytest

__all__: list[str] = []


def test_runner_attributes_every_test_against_every_mutant(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The adapter records a kill only for the failing test-mutant pair."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    assert hasattr(module, "run_kill_matrix")
    calls: list[str | None] = []
    responses = iter(
        [
            CompletedProcess([], 0, "", ""),
            CompletedProcess(
                [], 0, "package.one__mutmut_1: killed\npackage.two__mutmut_1: survived\n", ""
            ),
            CompletedProcess([], 0, "tests/test_x.py::test_one\ntests/test_x.py::test_two\n", ""),
            CompletedProcess([], 1, "", ""),
            CompletedProcess([], 0, "", ""),
            CompletedProcess([], 0, "", ""),
            CompletedProcess([], 0, "", ""),
        ]
    )

    def fake_run(
        *_args: object,
        args: list[str],
        cwd: str,
        env: Mapping[str, str] | None = None,
        **_kwargs: object,
    ) -> CompletedProcess[str]:
        _ = (args, cwd)
        calls.append(env.get("MUTANT_UNDER_TEST") if env else None)
        return next(responses)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    report = module.run_kill_matrix(
        repo_root=tmp_path, report_path=tmp_path / "report.json", source_revision="rev"
    )
    assert report.to_dict()["surviving_mutants"] == ["package.two__mutmut_1"]
    assert report.to_dict()["redundancy_candidates"] == ["tests/test_x.py::test_two"]
    assert calls[3:] == [
        "package.one__mutmut_1",
        "package.one__mutmut_1",
        "package.two__mutmut_1",
        "package.two__mutmut_1",
    ]


def test_runner_refuses_bad_generation_and_empty_results(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An unusable mutmut execution cannot produce a misleading report."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    monkeypatch.setattr(module, "run_command", lambda **_kwargs: CompletedProcess([], 2, "", ""))
    with pytest.raises(ValueError, match="mutmut failed"):
        module.run_kill_matrix(
            repo_root=tmp_path, report_path=tmp_path / "report.json", source_revision="rev"
        )


def test_main_delegates_to_the_requested_report_path(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The on-demand CLI uses its documented report path argument."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix")
    observed: list[Path] = []
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        module, "run_command", lambda **_kwargs: CompletedProcess([], 0, "rev\n", "")
    )
    monkeypatch.setattr(
        module, "run_kill_matrix", lambda *, report_path, **_kwargs: observed.append(report_path)
    )
    monkeypatch.setattr(sys, "argv", ["matrix", "--report", "reports/out.json"])
    assert module.main() == 0
    assert observed == [tmp_path / "reports/out.json"]
