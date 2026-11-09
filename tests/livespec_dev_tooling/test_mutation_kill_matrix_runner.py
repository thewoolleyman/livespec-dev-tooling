"""Tests for the mutmut adapter behind the portable Rule-26 report.

The engine runs in-process over fixture packages, and its children are real:
the mutmut stand-in from `tests.consumer.kill_matrix_fixture` and real pytest.
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
from typing import cast

import pytest

from tests.consumer.kill_matrix_fixture import (
    APPLY_LOG_VARIABLE,
    FixtureMutant,
    KillMatrixFixture,
    applied_mutants,
)

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.mutation_kill_matrix_runner"
_SOURCE = "src/calc/__init__.py"
_TESTS = "tests/test_calc.py"
_TWO_FUNCTIONS = "def add(a, b):\n    return a + b\n\n\ndef double(x):\n    return x * 2\n"
_TWO_TESTS = (
    "from calc import add, double\n\n\n"
    "def test_add():\n    assert add(2, 3) == 5\n\n\n"
    "def test_double():\n    assert double(4) == 8\n"
)
_ADD = "calc.x_add__mutmut_1"
_DOUBLE = "calc.x_double__mutmut_1"
_MUTANTS = {
    _ADD: FixtureMutant(path=_SOURCE, old="a + b", new="a - b"),
    _DOUBLE: FixtureMutant(path=_SOURCE, old="x * 2", new="x * 3"),
}


def _fixture(
    *,
    root: Path,
    monkeypatch: pytest.MonkeyPatch,
    tests: str = _TWO_TESTS,
    mutants: dict[str, FixtureMutant] | None = None,
) -> KillMatrixFixture:
    """Write a fixture package and point this process's children at its stand-ins."""
    fixture = KillMatrixFixture.create(
        root=root,
        sources={_SOURCE: _TWO_FUNCTIONS},
        tests={_TESTS: tests},
        mutants=mutants or _MUTANTS,
    )
    for name in (
        "COVERAGE_PROCESS_START",
        "COV_CORE_CONFIG",
        "COV_CORE_DATAFILE",
        "COV_CORE_SOURCE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PYTHONPATH", str(fixture.stubs))
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")
    monkeypatch.setenv(APPLY_LOG_VARIABLE, str(fixture.apply_log))
    return fixture


def _killers(*, document: dict[str, object]) -> dict[str, list[str]]:
    rows = cast("list[dict[str, object]]", document["mutants"])
    return {str(row["identifier"]): cast("list[str]", row["killed_by"]) for row in rows}


def test_runner_records_each_mutants_killers_without_mutating_the_target(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each mutant runs against the tests that execute it, in a worker tree, never the target."""
    module = importlib.import_module(_MODULE)
    fixture = _fixture(root=tmp_path, monkeypatch=monkeypatch)

    report = module.run_kill_matrix(
        target=fixture.package,
        source_revision="abc123",
        options=module.RunOptions(workers=2, per_test_timeout=10.0),
    )

    document = report.to_dict()
    assert _killers(document=document) == {
        _ADD: ["tests/test_calc.py::test_add"],
        _DOUBLE: ["tests/test_calc.py::test_double"],
    }
    assert document["test_selection_method"].startswith("coverage-guided:")
    assert document["run"] == {"incremental": False, "reused_mutants": 0, "workers": 2}
    assert (fixture.package / _SOURCE).read_text(encoding="utf-8") == _TWO_FUNCTIONS
    assert (fixture.package / "reports" / "mutation-kill-matrix.json").is_file()
    assert not (fixture.package / "reports" / "mutation-kill-matrix-cache.json").exists()


def test_a_cached_run_reuses_outcomes_and_writes_a_summary_against_a_previous_report(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With a cache, an unchanged second run applies nothing; a previous report adds a summary."""
    module = importlib.import_module(_MODULE)
    fixture = _fixture(root=tmp_path, monkeypatch=monkeypatch)
    cache = tmp_path / "cache.json"
    options = module.RunOptions(per_test_timeout=10.0, cache_path=cache)
    _ = module.run_kill_matrix(target=fixture.package, source_revision="r1", options=options)
    previous = tmp_path / "previous.json"
    _ = previous.write_text(
        (fixture.package / "reports" / "mutation-kill-matrix.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    applied = applied_mutants(fixture=fixture)

    second = module.run_kill_matrix(
        target=fixture.package,
        source_revision="r2",
        options=module.RunOptions(
            per_test_timeout=10.0, cache_path=cache, previous_report=previous
        ),
    )

    assert applied_mutants(fixture=fixture) == applied
    assert second.to_dict()["run"] == {"incremental": True, "reused_mutants": 2, "workers": 1}
    summary = json.loads(
        (fixture.package / "reports" / "mutation-kill-matrix-changes.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["previous_source_revision"] == "r1"
    assert summary["new_surviving_mutants"] == []


def test_a_test_that_kills_the_baseline_process_is_re_run_alone_and_excluded(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A test that ends the coverage run's process is judged alone, and is a baseline failure."""
    module = importlib.import_module(_MODULE)
    tests = (
        "import os\n\nfrom calc import add, double\n\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n\n"
        "def test_b_exits():\n    os._exit(4)\n\n\n"
        "def test_double():\n    assert double(4) == 8\n"
    )
    fixture = _fixture(root=tmp_path, monkeypatch=monkeypatch, tests=tests)

    document = module.run_kill_matrix(
        target=fixture.package,
        source_revision="abc",
        options=module.RunOptions(per_test_timeout=10.0),
    ).to_dict()

    assert document["baseline_failures"] == ["tests/test_calc.py::test_b_exits"]
    assert _killers(document=document)[_DOUBLE] == ["tests/test_calc.py::test_double"]


def test_a_run_in_which_no_mutant_applies_refuses_and_writes_no_report(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty applied set is a refusal, never a clean-looking report."""
    module = importlib.import_module(_MODULE)
    fixture = _fixture(
        root=tmp_path,
        monkeypatch=monkeypatch,
        mutants={_ADD: FixtureMutant(path=_SOURCE, old="absent", new="x")},
    )

    with pytest.raises(RuntimeError, match="applied mutant set is empty"):
        _ = module.run_kill_matrix(target=fixture.package, source_revision="abc")

    assert not (fixture.package / "reports" / "mutation-kill-matrix.json").exists()


def test_main_passes_its_options_and_reports_where_it_wrote(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The entry point turns its flags into run options and names what it wrote."""
    module = importlib.import_module(_MODULE)
    received: dict[str, object] = {}
    previous = tmp_path / "previous.json"
    _ = previous.write_text("{}", encoding="utf-8")

    def run_matrix(
        *, target: Path, source_revision: str, execute: object, options: object
    ) -> object:
        received.update(target=target, source_revision=source_revision, execute=execute)
        received["options"] = options
        return object()

    def revision(*, target: Path) -> str:
        return "rev" if target == tmp_path else "unknown"

    monkeypatch.setattr(module, "run_kill_matrix", run_matrix)
    monkeypatch.setattr(module, "source_revision", revision)

    assert module.main(argv=[str(tmp_path), "--workers", "3", "--timeout", "7"]) == 0
    assert received["source_revision"] == "rev"
    assert received["options"] == module.RunOptions(
        workers=3, per_test_timeout=7.0, cache_path=tmp_path / module.CACHE_PATH
    )
    assert "no what-changed summary was written" in capsys.readouterr().out

    arguments = [str(tmp_path), "--no-cache", "--previous-report", str(previous)]
    assert module.main(argv=arguments) == 0
    assert received["options"] == module.RunOptions(
        workers=os.cpu_count() or 1, cache_path=None, previous_report=previous
    )
    assert "mutation-kill-matrix-changes.json" in capsys.readouterr().out


def test_main_reports_a_refused_run_as_a_named_finding(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A refusal exits 1 with its finding, rather than a traceback."""
    module = importlib.import_module(_MODULE)

    def refuse(**_: object) -> object:
        message = "mutmut generated no mutants for the kill matrix"
        raise RuntimeError(message)

    def revision(*, target: Path) -> str:
        _ = target
        return "rev"

    monkeypatch.setattr(module, "run_kill_matrix", refuse)
    monkeypatch.setattr(module, "source_revision", revision)

    assert module.main(argv=[str(tmp_path)]) == 1
    assert "mutation-kill-matrix: mutmut generated no mutants" in capsys.readouterr().err


@pytest.mark.parametrize(
    "arguments",
    [
        ["missing"],
        [".", "--workers", "0"],
        [".", "--previous-report", "no-such-report.json"],
    ],
)
def test_main_refuses_unusable_arguments(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, arguments: list[str]
) -> None:
    """A typo fails before mutmut can write anywhere."""
    module = importlib.import_module(_MODULE)
    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        _ = module.main(argv=arguments)


def test_source_revision_labels_a_non_git_fixture_unknown(*, tmp_path: Path) -> None:
    """A standalone fixture has no revision to report."""
    module = importlib.import_module(_MODULE)

    assert module.source_revision(target=tmp_path) == "unknown"
