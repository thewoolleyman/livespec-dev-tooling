"""Tests for the mutmut adapter behind the portable Rule-26 report."""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runner_applies_each_mutant_and_runs_every_collected_test(*, tmp_path: Path) -> None:
    """The mutmut adapter records the complete test-by-mutant matrix."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "mutation_kill_matrix_runner.py"
    assert module_path.is_file()

    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_runner")
    source = tmp_path / "package.py"
    source.write_text("VALUE = 'original'\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []

    def execute(*, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        _ = cwd
        calls.append(tuple(args))
        if args[-3:] == ["results", "--all", "True"]:
            return subprocess.CompletedProcess(args, 0, "M1: killed\nM2: survived\n", "")
        if args[-2:] == ["--collect-only", "-q"]:
            return subprocess.CompletedProcess(
                args,
                0,
                "tests/test_rule.py::test_a\ntests/test_rule.py::test_b\n2 tests collected\n",
                "",
            )
        if args[-2:] == ["mutmut", "run"]:
            return subprocess.CompletedProcess(args, 1, "", "")
        if args[-3:-1] == ["mutmut", "apply"]:
            source.write_text("VALUE = 'mutated'\n", encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[-2:] == ["-q", "tests/test_rule.py::test_a"]:
            return subprocess.CompletedProcess(
                args, 1 if source.read_text() == "VALUE = 'mutated'\n" else 0, "", ""
            )
        return subprocess.CompletedProcess(args, 0, "", "")

    report = module.run_kill_matrix(
        target=tmp_path,
        source_revision="abc123",
        execute=execute,
    )

    assert report.to_dict()["mutants"] == [
        {"identifier": "M1", "killed_by": ["tests/test_rule.py::test_a"], "location": "mutmut:M1"},
        {"identifier": "M2", "killed_by": ["tests/test_rule.py::test_a"], "location": "mutmut:M2"},
    ]
    assert source.read_text(encoding="utf-8") == "VALUE = 'original'\n"
    assert calls.count((sys.executable, "-m", "mutmut", "apply", "M1")) == 1
    assert calls.count((sys.executable, "-m", "mutmut", "apply", "M2")) == 1
    assert (tmp_path / "reports" / "mutation-kill-matrix.json").is_file()


@pytest.mark.parametrize(
    ("outputs", "message"),
    [
        ([subprocess.CompletedProcess([], 2, "", "")], "mutmut run failed"),
        (
            [
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 2, "", ""),
            ],
            "mutmut results failed",
        ),
        (
            [
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "", ""),
            ],
            "mutmut generated no mutants",
        ),
    ],
)
def test_runner_refuses_unusable_mutmut_output(
    *, tmp_path: Path, outputs: list[subprocess.CompletedProcess[str]], message: str
) -> None:
    """A failed or empty measurement cannot become a Rule-26 report."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_runner")

    def execute(*, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        _ = args, cwd
        return outputs.pop(0)

    with pytest.raises(RuntimeError, match=message):
        _ = module.run_kill_matrix(target=tmp_path, source_revision="abc123", execute=execute)


def test_main_accepts_the_target_package_path_and_uses_its_report_location(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The on-demand entry point makes the target path explicit."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_runner")
    received: dict[str, object] = {}

    def run_matrix(*, target: Path, source_revision: str, execute: object) -> object:
        received.update(target=target, source_revision=source_revision, execute=execute)
        return object()

    monkeypatch.setattr(module, "run_kill_matrix", run_matrix)
    monkeypatch.setattr(
        module,
        "source_revision",
        lambda *, target: "revision" if target == tmp_path else "unknown",
    )
    monkeypatch.setattr(sys, "argv", ["mutation-kill-matrix", str(tmp_path)])

    assert module.main() == 0
    assert received["target"] == tmp_path
    assert received["source_revision"] == "revision"


def test_main_refuses_a_target_that_is_not_a_package_directory(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A typo must fail before mutmut can write outside the intended package."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_runner")

    def unexpected_run(**kwargs: object) -> object:
        _ = kwargs
        raise AssertionError("the runner must not start for a missing target")

    monkeypatch.setattr(module, "run_kill_matrix", unexpected_run)
    monkeypatch.setattr(sys, "argv", ["mutation-kill-matrix", str(tmp_path / "missing")])

    with pytest.raises(SystemExit):
        _ = module.main()


def test_subprocess_executor_and_source_revision_handle_a_non_git_fixture(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The adapter uses normal subprocesses and labels non-git fixtures unknown."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_runner")
    observed: dict[str, object] = {}

    def fake_run(**kwargs: object) -> subprocess.CompletedProcess[str]:
        observed.update(kwargs)
        return subprocess.CompletedProcess([], 1, "", "not a repository")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    result = module.execute_command(args=["tool"], cwd=tmp_path)

    assert result.returncode == 1
    assert observed["cwd"] == str(tmp_path)
    assert module.source_revision(target=tmp_path) == "unknown"
