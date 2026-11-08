"""Tests for the mutmut adapter behind the portable Rule-26 report."""

from __future__ import annotations

import importlib
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest
from coverage import CoverageData

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_runner_applies_each_mutant_and_runs_every_collected_test(*, tmp_path: Path) -> None:
    """The mutmut adapter records the complete test-by-mutant matrix."""
    module_path = _REPO_ROOT / "livespec_dev_tooling" / "mutation_kill_matrix_runner.py"
    assert module_path.is_file()

    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_runner")
    source = tmp_path / "package.py"
    _ = source.write_text("VALUE = 'original'\n", encoding="utf-8")
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
            _ = source.write_text("VALUE = 'mutated'\n", encoding="utf-8")
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
    assert calls.count((sys.executable, "-B", "-m", "mutmut", "apply", "M1")) == 1
    assert calls.count((sys.executable, "-B", "-m", "mutmut", "apply", "M2")) == 1
    assert all(call[call.index(sys.executable) + 1] == "-B" for call in calls)
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

    def revision(*, target: Path) -> str:
        return "revision" if target == tmp_path else "unknown"

    monkeypatch.setattr(module, "run_kill_matrix", run_matrix)
    monkeypatch.setattr(module, "source_revision", revision)
    monkeypatch.setattr(sys, "argv", ["mutation-kill-matrix", str(tmp_path)])

    assert module.main() == 0
    assert received["target"] == tmp_path
    assert received["source_revision"] == "revision"


def test_main_refuses_a_target_that_is_not_a_package_directory(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A typo must fail before mutmut can write outside the intended package."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_runner")
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


_TWO_FUNCTIONS = "def f(value):\n    return value + 1\n\n\ndef g(value):\n    return value * 2\n"
_T1 = "tests/test_two.py::test_t1"
_T2 = "tests/test_two.py::test_t2"
_T3 = "tests/test_two.py::test_unmeasured"


def _guided_executor(
    *, target: Path, runs: list[tuple[str, str]], contexts: dict[str, list[int]] | None
) -> Callable[..., subprocess.CompletedProcess[str]]:
    """Fake mutmut and pytest over a two-function package, recording each mutant's test runs.

    `contexts` maps a test node id to the source lines its coverage context
    executes; None writes no coverage data at all. As in a real layout whose
    tests sit inside the measured tree, every collected test's context also
    executes its own body in the test file.
    """
    source = target / "pkg" / "core.py"
    test_file = target / "tests" / "test_two.py"
    applied: list[str] = []

    def execute(*, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        _ = cwd
        if args[-2:] == ["mutmut", "run"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args[-3:] == ["results", "--all", "True"]:
            return subprocess.CompletedProcess(
                args, 0, "pkg.core.x_f__mutmut_1: killed\npkg.core.x_g__mutmut_1: killed\n", ""
            )
        if args[-2:] == ["--collect-only", "-q"]:
            return subprocess.CompletedProcess(args, 0, f"{_T1}\n{_T2}\n{_T3}\n", "")
        if "--cov-context=test" in args and contexts is not None:
            rcfile = next(arg for arg in args if arg.startswith("--cov-config=")).partition("=")[2]
            data_file = Path(rcfile).read_text(encoding="utf-8").split("data_file = ")[1].strip()
            data = CoverageData(basename=data_file)
            for body_line, test in enumerate((_T1, _T2, _T3), start=2):
                data.set_context(f"{test}|run")
                data.add_lines({str(test_file): [body_line]})
                if test in contexts:
                    data.add_lines({str(source): contexts[test]})
            data.write()
        if args[-3:-1] == ["mutmut", "apply"]:
            applied.append(args[-1])
        if args[-2] == "-q" and args[-1].startswith("tests/"):
            runs.append((applied[-1], args[-1]))
            return subprocess.CompletedProcess(args, 1, "", "")
        return subprocess.CompletedProcess(args, 0, "", "")

    return execute


def _two_function_package(*, root: Path) -> Path:
    """Write a flat package whose module holds functions f (line 2) and g (line 6)."""
    (root / "pkg").mkdir()
    _ = (root / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    _ = (root / "pkg" / "core.py").write_text(_TWO_FUNCTIONS, encoding="utf-8")
    return root


def test_each_mutant_runs_only_against_the_tests_that_execute_its_function(
    *, tmp_path: Path
) -> None:
    """T1 executes only f and T2 only g; an unmeasured test runs against every mutant."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_runner")
    target = _two_function_package(root=tmp_path)
    runs: list[tuple[str, str]] = []

    report = module.run_kill_matrix(
        target=target,
        source_revision="abc123",
        execute=_guided_executor(target=target, runs=runs, contexts={_T1: [2], _T2: [6]}),
    )

    assert sorted(runs) == [
        ("pkg.core.x_f__mutmut_1", _T1),
        ("pkg.core.x_f__mutmut_1", _T3),
        ("pkg.core.x_g__mutmut_1", _T2),
        ("pkg.core.x_g__mutmut_1", _T3),
    ]
    document = report.to_dict()
    assert [row["location"] for row in document["mutants"]] == [
        "pkg/core.py:2-2",
        "pkg/core.py:6-6",
    ]
    assert document["test_selection_method"].startswith("coverage-guided:")


def test_without_per_test_coverage_every_test_runs_against_every_mutant(*, tmp_path: Path) -> None:
    """A suite that yields no coverage data falls back to the full matrix and says so."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_runner")
    target = _two_function_package(root=tmp_path)
    runs: list[tuple[str, str]] = []

    report = module.run_kill_matrix(
        target=target,
        source_revision="abc123",
        execute=_guided_executor(target=target, runs=runs, contexts=None),
    )

    assert len(runs) == 6
    assert report.to_dict()["test_selection_method"].startswith("full-matrix:")
