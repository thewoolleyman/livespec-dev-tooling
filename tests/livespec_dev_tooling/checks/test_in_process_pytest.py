"""Run the nested pytest of a Red/Green-replay fixture inside this process.

`check-red-green-replay` spawns a REAL `pytest` against the tiny fixture suites
its tests build (a Red leg, a Green leg, the suite-green leg, the range
collector). Each spawn pays about 0.2 s importing pytest before it runs one
test, so a module of a hundred such cases spends most of its time starting
interpreters. The functions here execute the same command line with the real
`pytest.main` in this process instead: real collection, real assertion
rewriting, real failures, real exit codes and real terminal output, with no
interpreter start and no pty.

What is isolated per run is exactly what a child process would have isolated:
the working directory, `sys.path` (plus `PYTHONPATH`, which a child's
interpreter would have put there), the modules the run imported from the
fixture tree, and the environment variables the caller layered on.

This file is a test module, so the tests below pin that isolation: a helper
that leaked one fixture tree's imports into the next would make every case that
uses it pass or fail on the order it ran in.
"""

from __future__ import annotations

import contextlib
import importlib
import io
import os
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace

import pytest

from livespec_dev_tooling.checks._red_green_replay_suite_runner import SuiteBound, SuiteRun

__all__: list[str] = ["in_process_subprocess", "in_process_suite_run", "run_in_process"]


def _pytest_arguments(*, argv: Sequence[str]) -> list[str] | None:
    """Return the pytest arguments of `argv`, or None when it is not a pytest command."""
    command = [str(part) for part in argv]
    if command[:1] and Path(command[0]).name == "pytest":
        return command[1:]
    if command[1:3] == ["-m", "pytest"]:
        return command[3:]
    return None


def _imported_from(*, roots: Sequence[Path]) -> list[str]:
    """Name the loaded modules whose source sits under any of `roots`."""
    return [
        name
        for name, loaded in list(sys.modules.items())
        if any(
            Path(source).is_relative_to(root)
            for source in [getattr(loaded, "__file__", None)]
            if source
            for root in roots
        )
    ]


@contextlib.contextmanager
def _isolated_interpreter(*, cwd: Path | None, environ: Mapping[str, str]) -> Iterator[None]:
    """Give one nested pytest run a child's view of cwd, import state and environment.

    A child's imports die with it. Here the modules the run loaded from the
    fixture tree (the working directory: its tests, its `livespec` package, its
    conftest) are dropped afterwards, so the next run, which may be another
    commit's tree with a same-named module, imports its own. pytest's and the
    interpreter's own modules stay loaded: they are not the fixture's, and
    reloading them would duplicate their classes and registrations.
    """
    saved_cwd = Path.cwd()
    saved_path = list(sys.path)
    saved_environ = dict(os.environ)
    os.environ.update(environ)
    if cwd is not None:
        os.chdir(cwd)
    # A child's interpreter puts the layered PYTHONPATH on sys.path; this process
    # already carries the caller's own, so only the layered entries are added.
    sys.path[:0] = [entry for entry in environ.get("PYTHONPATH", "").split(os.pathsep) if entry]
    roots = [Path.cwd().resolve()]
    importlib.invalidate_caches()
    try:
        yield
    finally:
        for name in _imported_from(roots=roots):
            del sys.modules[name]
        sys.path[:] = saved_path
        os.chdir(saved_cwd)
        os.environ.clear()
        os.environ.update(saved_environ)
        importlib.invalidate_caches()


def run_in_process(
    *, arguments: list[str], cwd: Path | None, environ: Mapping[str, str]
) -> tuple[int, str]:
    """Run `pytest.main(arguments)` isolated like a child process; return (exit code, output)."""
    output = io.StringIO()
    with (
        _isolated_interpreter(cwd=cwd, environ=environ),
        contextlib.redirect_stdout(output),
        contextlib.redirect_stderr(output),
    ):
        returncode = int(pytest.main(["-p", "no:cacheprovider", *arguments]))
    return returncode, output.getvalue()


def in_process_suite_run(
    *,
    argv: list[str],
    bound: SuiteBound,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
    **_unused: object,
) -> SuiteRun:
    """Stand in for the check's `run_suite`, running its pytest command in this process."""
    del bound
    arguments = _pytest_arguments(argv=argv)
    assert arguments is not None, argv
    returncode, output = run_in_process(arguments=arguments, cwd=cwd, environ=environ or {})
    return SuiteRun(returncode=returncode, output=output, timed_out=False)


def _in_process_run(
    argv: list[str], *, capture_output: bool, text: bool, check: bool
) -> subprocess.CompletedProcess[str]:
    """Stand in for the `subprocess.run` the Red and Green legs run their test with."""
    assert capture_output
    assert text
    assert not check
    arguments = _pytest_arguments(argv=argv)
    assert arguments is not None, argv
    returncode, output = run_in_process(arguments=arguments, cwd=None, environ={})
    return subprocess.CompletedProcess(argv, returncode, stdout=output, stderr="")


in_process_subprocess = SimpleNamespace(run=_in_process_run)


_NO_AUTOLOAD = {"PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
_BOUND = SuiteBound(stall_seconds=900, ceiling_seconds=None)


def _tree(*, root: Path, helper_value: int) -> Path:
    """Write a fixture tree whose test imports a same-named helper module from it."""
    root.mkdir()
    (root / "fixture_helper.py").write_text(f"VALUE = {helper_value}\n", encoding="utf-8")
    (root / "test_case.py").write_text(
        "from fixture_helper import VALUE\n\n\ndef test_value() -> None:\n    assert VALUE == 1\n",
        encoding="utf-8",
    )
    return root


def test_a_passing_suite_reports_pytests_own_exit_code_and_output(*, tmp_path: Path) -> None:
    tree = _tree(root=tmp_path / "tree", helper_value=1)

    returncode, output = run_in_process(
        arguments=["-q", "test_case.py"], cwd=tree, environ=_NO_AUTOLOAD
    )

    assert returncode == 0
    assert "1 passed" in output


def test_a_failing_suite_reports_the_real_assertion_failure(*, tmp_path: Path) -> None:
    tree = _tree(root=tmp_path / "tree", helper_value=2)

    returncode, output = run_in_process(
        arguments=["--tb=short", "-q", "test_case.py"], cwd=tree, environ=_NO_AUTOLOAD
    )

    assert returncode == 1
    assert "assert 2 == 1" in output


def test_a_suite_with_no_tests_reports_pytests_no_tests_exit_code(*, tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "test_empty.py").write_text("X = 1\n", encoding="utf-8")

    returncode, _output = run_in_process(
        arguments=["-q", "test_empty.py"], cwd=tree, environ=_NO_AUTOLOAD
    )

    assert returncode == 5


def test_a_run_does_not_see_the_modules_an_earlier_tree_imported(*, tmp_path: Path) -> None:
    passing = _tree(root=tmp_path / "passing", helper_value=1)
    failing = _tree(root=tmp_path / "failing", helper_value=2)

    first, _ = run_in_process(arguments=["-q", "test_case.py"], cwd=passing, environ=_NO_AUTOLOAD)
    second, _ = run_in_process(arguments=["-q", "test_case.py"], cwd=failing, environ=_NO_AUTOLOAD)
    third, _ = run_in_process(arguments=["-q", "test_case.py"], cwd=passing, environ=_NO_AUTOLOAD)

    assert (first, second, third) == (0, 1, 0)
    assert "fixture_helper" not in sys.modules
    assert "test_case" not in sys.modules


def test_a_run_leaves_cwd_path_and_environment_as_it_found_them(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = _tree(root=tmp_path / "tree", helper_value=1)
    monkeypatch.delenv("LAYERED_BY_THE_CALLER", raising=False)
    monkeypatch.setenv("LAYERED_AND_PRESET", "before")
    before = (Path.cwd(), list(sys.path), dict(os.environ))

    _ = run_in_process(
        arguments=["-q", "test_case.py"],
        cwd=tree,
        environ={
            **_NO_AUTOLOAD,
            "LAYERED_BY_THE_CALLER": "x",
            "LAYERED_AND_PRESET": "during",
            "PYTHONPATH": str(tmp_path),
        },
    )

    assert (Path.cwd(), sys.path, dict(os.environ)) == before


def test_the_layered_pythonpath_is_importable_by_the_run(*, tmp_path: Path) -> None:
    tree = tmp_path / "tree"
    tree.mkdir()
    (tmp_path / "layered_only.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tree / "test_case.py").write_text(
        "from layered_only import VALUE\n\n\ndef test_value() -> None:\n    assert VALUE == 1\n",
        encoding="utf-8",
    )

    returncode, _output = run_in_process(
        arguments=["-q", "test_case.py"],
        cwd=tree,
        environ={**_NO_AUTOLOAD, "PYTHONPATH": str(tmp_path)},
    )

    assert returncode == 0


def test_the_suite_runner_stand_in_returns_a_completed_suite_run(*, tmp_path: Path) -> None:
    tree = _tree(root=tmp_path / "tree", helper_value=2)

    run = in_process_suite_run(
        argv=[sys.executable, "-m", "pytest", "-q", "test_case.py"],
        bound=_BOUND,
        cwd=tree,
        environ=_NO_AUTOLOAD,
    )

    assert (run.returncode, run.timed_out, run.kill_reason) == (1, False, None)
    assert "1 failed" in run.output


def test_the_subprocess_stand_in_returns_a_completed_process(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tree = _tree(root=tmp_path / "tree", helper_value=1)
    monkeypatch.chdir(tree)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")

    done = in_process_subprocess.run(
        ["pytest", "-q", "test_case.py"], capture_output=True, text=True, check=False
    )

    assert done.returncode == 0
    assert "1 passed" in done.stdout
