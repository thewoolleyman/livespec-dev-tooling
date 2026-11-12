"""Tests for the kill matrix's shared-process test runs and isolated worker trees."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.mutation_kill_matrix_execution"


def _result(*, returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, "")


def test_a_command_that_outlives_its_timeout_is_killed_and_reported_as_timed_out(
    *, tmp_path: Path
) -> None:
    """The whole process group dies at the timeout and the result carries 124."""
    module = importlib.import_module(_MODULE)

    slow = module.execute_command(
        args=[sys.executable, "-c", "import time; time.sleep(30)"], cwd=tmp_path, timeout=0.5
    )
    quick = module.execute_command(args=[sys.executable, "-c", "print('ok')"], cwd=tmp_path)

    assert slow.returncode == module.TIMED_OUT_RETURNCODE
    assert (quick.returncode, quick.stdout.strip()) == (0, "ok")


def test_outcomes_are_read_per_test_and_an_absent_file_reads_as_none(*, tmp_path: Path) -> None:
    """Each recorded line is one test's outcome."""
    module = importlib.import_module(_MODULE)
    outcomes = tmp_path / "outcomes.jsonl"
    _ = outcomes.write_text(
        json.dumps({"test": "t::a", "failed": True, "duration": 0.1})
        + "\n\n"
        + json.dumps({"test": "t::b", "failed": False, "duration": 0.2})
        + "\n"
        + json.dumps({"test": "t::slow", "failed": False, "duration": 9.0})
        + "\n",
        encoding="utf-8",
    )

    assert module.read_outcomes(outcomes=outcomes) == {
        "t::a": True,
        "t::b": False,
        "t::slow": False,
    }
    assert module.read_outcomes(outcomes=outcomes, slower_than=5.0)["t::slow"] is True
    assert module.read_outcomes(outcomes=tmp_path / "absent.jsonl") == {}
    assert module.outcome_environment(outcomes=outcomes, timeout=2.0) == (
        f"KILL_MATRIX_OUTCOMES={outcomes}",
        "KILL_MATRIX_TIMEOUT=2.0",
    )


def test_unreported_tests_are_re_run_alone_and_decided_by_that_run(*, tmp_path: Path) -> None:
    """A shared run that reports only some tests sends each missing one to a lone run."""
    module = importlib.import_module(_MODULE)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    tree = module.WorkerTree(root=tmp_path, scratch=scratch)
    batches: list[list[str]] = []

    def execute(
        *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        _ = cwd
        selected = (scratch / "selected-tests.txt").read_text(encoding="utf-8").split()
        batches.append(selected)
        outcomes = Path(
            next(a for a in args if a.startswith("KILL_MATRIX_OUTCOMES=")).partition("=")[2]
        )
        assert timeout == 1.0 * len(selected) + 60.0
        if selected == ["t.py::a", "t.py::b", "t.py::c"]:
            _ = outcomes.write_text(json.dumps({"test": "t.py::a", "failed": False}) + "\n")
            return _result(returncode=module.TIMED_OUT_RETURNCODE)
        if selected == ["t.py::b"]:
            _ = outcomes.write_text(json.dumps({"test": "t.py::b", "failed": True}) + "\n")
            return _result(returncode=1)
        return _result(returncode=3)

    outcomes = module.run_selected(
        execute=execute, tree=tree, tests=["t.py::a", "t.py::b", "t.py::c"], timeout=1.0
    )

    assert outcomes == {"t.py::a": False, "t.py::b": True, "t.py::c": True}
    assert batches == [["t.py::a", "t.py::b", "t.py::c"], ["t.py::b"], ["t.py::c"]]
    assert module.run_selected(execute=execute, tree=tree, tests=[], timeout=1.0) == {}


class _Processes:
    """A stand-in executor: each call is one pytest process, scripted by its selection."""

    def __init__(
        self, *, scratch: Path, script: dict[tuple[str, ...], tuple[list[dict[str, object]], int]]
    ) -> None:
        self._scratch = scratch
        self._script = script
        self.started: list[list[str]] = []
        self.commands: list[list[str]] = []

    def __call__(
        self, *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        _ = cwd, timeout
        selected = (self._scratch / "selected-tests.txt").read_text(encoding="utf-8").split()
        self.started.append(selected)
        self.commands.append(args)
        rows, returncode = self._script.get(tuple(selected), ([], 4))
        outcomes = Path(
            next(a for a in args if a.startswith("KILL_MATRIX_OUTCOMES=")).partition("=")[2]
        )
        _ = outcomes.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        return _result(returncode=returncode)


def _passed(*tests: str) -> list[dict[str, object]]:
    return [{"test": test, "failed": False, "duration": 0.0} for test in tests]


def test_tests_in_a_file_that_cannot_be_collected_fail_without_a_process_each(
    *, tmp_path: Path
) -> None:
    """One process settles a mutant that breaks a file: its tests fail, the other files run."""
    module = importlib.import_module(_MODULE)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    tests = ["a.py::one", "a.py::two", "pkg/b.py::three", "pkgx.py::four", "c.py::five"]
    processes = _Processes(
        scratch=scratch,
        script={
            tuple(tests): (
                [
                    {"uncollected": "a.py"},
                    {"uncollected": "pkg"},
                    {"uncollected": ""},
                    *_passed("pkgx.py::four", "c.py::five"),
                ],
                1,
            )
        },
    )

    outcomes = module.run_selected(
        execute=processes,
        tree=module.WorkerTree(root=tmp_path, scratch=scratch),
        tests=tests,
        timeout=1.0,
    )

    assert outcomes == {
        "a.py::one": True,
        "a.py::two": True,
        "pkg/b.py::three": True,
        "pkgx.py::four": False,
        "c.py::five": False,
    }
    assert processes.started == [tests]
    assert "--continue-on-collection-errors" in processes.commands[0]
    assert module.read_outcomes(outcomes=scratch / "outcomes.jsonl") == {
        "pkgx.py::four": False,
        "c.py::five": False,
    }


def test_after_a_process_that_ends_partway_the_rest_run_in_one_further_process(
    *, tmp_path: Path
) -> None:
    """The first unreported test is judged alone; the tests after it share one process."""
    module = importlib.import_module(_MODULE)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    tests = [f"t.py::t{number}" for number in range(1, 7)]
    processes = _Processes(
        scratch=scratch,
        script={
            tuple(tests): (_passed(*tests[:2]), module.TIMED_OUT_RETURNCODE),
            (tests[2],): ([], -14),
            tuple(tests[3:]): (_passed(*tests[3:]), 0),
        },
    )

    outcomes = module.run_selected(
        execute=processes,
        tree=module.WorkerTree(root=tmp_path, scratch=scratch),
        tests=tests,
        timeout=1.0,
    )

    assert outcomes == {test: test == tests[2] for test in tests}
    assert processes.started == [tests, [tests[2]], tests[3:]]


def test_a_group_that_settles_nothing_is_split_instead_of_run_one_test_at_a_time(
    *, tmp_path: Path
) -> None:
    """When a whole group reports nothing, its first test runs alone and the rest in halves."""
    module = importlib.import_module(_MODULE)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    tests = [f"t.py::t{number}" for number in range(1, 6)]
    processes = _Processes(
        scratch=scratch,
        script={
            tuple(tests[1:3]): (_passed(*tests[1:3]), 0),
            tuple(tests[3:]): (_passed(*tests[3:]), 0),
        },
    )

    outcomes = module.run_selected(
        execute=processes,
        tree=module.WorkerTree(root=tmp_path, scratch=scratch),
        tests=tests,
        timeout=1.0,
    )

    assert outcomes == {test: test == tests[0] for test in tests}
    assert processes.started == [tests, [tests[0]], tests[1:3], tests[3:]]


def test_a_real_file_that_cannot_be_imported_costs_one_process_and_kills_its_tests(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Real pytest: the broken file's tests fail, the sound file's tests run, in one process."""
    module = importlib.import_module(_MODULE)
    target = tmp_path / "pkg"
    scratch = tmp_path / "scratch"
    (target / "tests").mkdir(parents=True)
    scratch.mkdir()
    _ = (target / "tests" / "test_broken.py").write_text(
        "import a_module_the_mutant_removed\n\n\ndef test_one():\n    pass\n\n\n"
        "def test_two():\n    pass\n",
        encoding="utf-8",
    )
    _ = (target / "tests" / "test_sound.py").write_text(
        "def test_three():\n    pass\n", encoding="utf-8"
    )
    for name in (
        "COVERAGE_PROCESS_START",
        "COV_CORE_CONFIG",
        "COV_CORE_DATAFILE",
        "COV_CORE_SOURCE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    started: list[list[str]] = []

    def counting(
        *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        started.append(args)
        result: subprocess.CompletedProcess[str] = module.execute_command(
            args=args, cwd=cwd, timeout=timeout
        )
        return result

    outcomes = module.run_selected(
        execute=counting,
        tree=module.WorkerTree(root=target, scratch=scratch),
        tests=[
            "tests/test_broken.py::test_one",
            "tests/test_broken.py::test_two",
            "tests/test_sound.py::test_three",
        ],
        timeout=30.0,
    )

    assert outcomes == {
        "tests/test_broken.py::test_one": True,
        "tests/test_broken.py::test_two": True,
        "tests/test_sound.py::test_three": False,
    }
    assert len(started) == 1


def test_import_roots_keep_only_target_paths_once_each(*, tmp_path: Path) -> None:
    """The interpreter's path entries inside the target become worker-relative roots."""
    module = importlib.import_module(_MODULE)
    entries = ["", str(tmp_path), str(tmp_path / "src"), str(tmp_path / "src"), "/elsewhere"]

    def execute(**_: object) -> subprocess.CompletedProcess[str]:
        return _result(stdout=json.dumps(entries))

    def failing(**_: object) -> subprocess.CompletedProcess[str]:
        return _result(returncode=1)

    assert module.import_roots(execute=execute, target=tmp_path) == [".", "src"]
    assert module.import_roots(execute=failing, target=tmp_path) == []


def _package(*, root: Path) -> Path:
    target = root / "pkg"
    for relative in (".git/HEAD", "src/pkg/__init__.py", "reports/old.json", "src/reports/keep.py"):
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text("x\n", encoding="utf-8")
    return target


def test_a_worker_tree_is_a_private_copy_whose_imports_resolve_into_it(*, tmp_path: Path) -> None:
    """Caches and root outputs stay behind, and the copy's roots lead its PYTHONPATH."""
    module = importlib.import_module(_MODULE)
    target = _package(root=tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def execute(
        *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        _ = args, timeout
        return _result(stdout=str(cwd / "src" / "pkg" / "__init__.py"))

    tree = module.make_worker_tree(
        execute=execute,
        target=target,
        workspace=workspace,
        index=0,
        roots=[".", "src"],
        modules=["pkg"],
    )

    assert (tree.root / "src" / "pkg" / "__init__.py").is_file()
    assert (tree.root / "src" / "reports" / "keep.py").is_file()
    assert not (tree.root / ".git").exists()
    assert not (tree.root / "reports").exists()
    pythonpath = tree.environment[0].partition("=")[2].split(":")
    assert pythonpath[:2] == [str(tree.root), str(tree.root / "src")]


def test_a_worker_tree_whose_module_resolves_into_the_original_target_is_refused(
    *, tmp_path: Path
) -> None:
    """An editable install would make every mutant in the copy invisible to the tests."""
    module = importlib.import_module(_MODULE)
    target = _package(root=tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    def leaking(**_: object) -> subprocess.CompletedProcess[str]:
        return _result(stdout=str(target / "src" / "pkg" / "__init__.py"))

    with pytest.raises(RuntimeError, match="worker tree imports the original target: pkg"):
        _ = module.make_worker_tree(
            execute=leaking, target=target, workspace=workspace, index=0, roots=[], modules=["pkg"]
        )


def test_an_unresolvable_module_does_not_stop_a_worker_tree(*, tmp_path: Path) -> None:
    """A module plain Python cannot find is resolved later by pytest's own pythonpath."""
    module = importlib.import_module(_MODULE)
    target = _package(root=tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    real = module.make_worker_tree(
        execute=module.execute_command,
        target=target,
        workspace=workspace,
        index=0,
        roots=[],
        modules=["pkg_absent"],
    )

    def failing(**_: object) -> subprocess.CompletedProcess[str]:
        return _result(returncode=1, stdout="ignored")

    failed = module.make_worker_tree(
        execute=failing, target=target, workspace=workspace, index=1, roots=[], modules=["pkg"]
    )

    assert real.root.is_dir()
    assert failed.root.is_dir()
