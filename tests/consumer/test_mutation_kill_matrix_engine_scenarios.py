"""Consumer-tier scenarios for the Rule-26 kill-matrix engine (spec v165).

Each test runs the engine as a consumer does, `python -m
livespec_dev_tooling.mutation_kill_matrix_runner <package>` (or the scheduled
entry point), over a fixture package that sets up exactly its scenario's
Given steps, with outbound network access refused, and asserts each Then step
against the written report, what-changed summary, or exit status.  See
`kill_matrix_fixture` for the mutmut stand-in.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import cast

import pytest
import yaml

from tests.consumer.kill_matrix_fixture import (
    FixtureMutant,
    KillMatrixFixture,
    applied_mutants,
    read_report,
)

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SOURCE = "src/calc/__init__.py"
_TESTS = "tests/test_calc.py"
_ADD_AND_DOUBLE = "def add(a, b):\n    return a + b\n\n\ndef double(x):\n    return x * 2\n"
_ADD_MUTANT = "calc.x_add__mutmut_1"
_DOUBLE_MUTANT = "calc.x_double__mutmut_1"
_MINUS = FixtureMutant(path=_SOURCE, old="a + b", new="a - b")
_TRIPLE = FixtureMutant(path=_SOURCE, old="x * 2", new="x * 3")


def matrix_content(*, document: dict[str, object]) -> dict[str, object]:
    """A report without its run metadata, the only fields allowed to differ between runs."""
    return {key: value for key, value in document.items() if key != "run"}


def _killers(*, report: dict[str, object]) -> dict[str, list[str]]:
    """Map each mutant identifier to the tests the report says killed it."""
    rows = cast("list[dict[str, object]]", report["mutants"])
    return {str(row["identifier"]): cast("list[str]", row["killed_by"]) for row in rows}


def _ok(*, fixture: KillMatrixFixture, arguments: tuple[str, ...] = ()) -> dict[str, object]:
    """Run the engine, require it to complete, and return its report."""
    completed = fixture.run_engine("--workers", "1", "--timeout", "10", *arguments)
    assert completed.returncode == 0, completed.stderr
    return read_report(package=fixture.package)


def _node(name: str, *, file: str = _TESTS) -> str:
    return f"{file}::{name}"


def test_a_parallel_kill_matrix_run_reports_the_same_matrix_as_a_single_worker_run(
    *, tmp_path: Path
) -> None:
    """Scenario: a parallel kill-matrix run reports the same matrix as a single-worker run."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: _ADD_AND_DOUBLE},
        tests={
            _TESTS: (
                "from calc import add, double\n\n\n"
                "def test_add():\n    assert add(2, 3) == 5\n\n\n"
                "def test_double():\n    assert double(4) == 8\n\n\n"
                "def test_sum_of_doubles():\n    assert add(double(1), double(2)) == 6\n\n\n"
                "def test_weak():\n    assert add(0, 0) == 0\n"
            )
        },
        mutants={
            _ADD_MUTANT: _MINUS,
            "calc.x_add__mutmut_2": FixtureMutant(path=_SOURCE, old="a + b", new="a * b"),
            _DOUBLE_MUTANT: _TRIPLE,
            "calc.x_double__mutmut_2": FixtureMutant(path=_SOURCE, old="x * 2", new="x + 2"),
        },
    )

    single = fixture.run_engine("--workers", "1", "--timeout", "10", "--no-cache")
    assert single.returncode == 0, single.stderr
    single_report = read_report(package=fixture.package)
    parallel = fixture.run_engine("--workers", "3", "--timeout", "10", "--no-cache")
    assert parallel.returncode == 0, parallel.stderr
    parallel_report = read_report(package=fixture.package)

    assert matrix_content(document=parallel_report) == matrix_content(document=single_report)
    assert _killers(report=single_report)[_ADD_MUTANT] == [
        _node("test_add"),
        _node("test_sum_of_doubles"),
    ]
    assert cast("dict[str, object]", single_report["run"])["workers"] == 1
    assert cast("dict[str, object]", parallel_report["run"])["workers"] == 3


def test_tests_sharing_one_process_each_keep_their_own_kill_outcome(*, tmp_path: Path) -> None:
    """Scenario: tests sharing one process each keep their own kill outcome."""
    pids = tmp_path / "pids.txt"
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: _ADD_AND_DOUBLE},
        tests={
            _TESTS: (
                "import os\n\nfrom calc import add\n\n\n"
                "def _record(value):\n"
                f"    with open({str(pids)!r}, 'a') as handle:\n"
                "        handle.write(f'{os.getpid()} {value}\\n')\n\n\n"
                "def test_first():\n    _record(add(2, 3))\n    assert add(2, 3) == 5\n\n\n"
                "def test_second():\n    _record(add(2, 3))\n    assert add(0, 0) == 0\n"
            )
        },
        mutants={_ADD_MUTANT: _MINUS},
    )

    report = _ok(fixture=fixture)

    assert _killers(report=report)[_ADD_MUTANT] == [_node("test_first")]
    under_mutant = [
        line.split()[0] for line in pids.read_text().splitlines() if line.split()[1] == "-1"
    ]
    assert len(under_mutant) == 2
    assert len(set(under_mutant)) == 1


def test_a_test_whose_shared_process_dies_is_re_run_alone(*, tmp_path: Path) -> None:
    """Scenario: a test whose shared process dies is re-run alone."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: "import os\n\n\ndef add(a, b):\n    return a + b\n"},
        tests={
            _TESTS: (
                "from calc import add\n\n\n"
                "def test_a_first():\n    assert add(0, 0) == 0\n\n\n"
                "def test_b_second():\n    assert add(2, 3) == 5\n"
            )
        },
        mutants={
            _ADD_MUTANT: FixtureMutant(
                path=_SOURCE,
                old="    return a + b",
                new="    if a == 0:\n        os._exit(3)\n    return a + b",
            )
        },
    )

    report = _ok(fixture=fixture)

    assert _killers(report=report)[_ADD_MUTANT] == [_node("test_a_first")]


def test_a_test_that_exceeds_the_per_test_timeout_against_a_mutant_kills_it(
    *, tmp_path: Path
) -> None:
    """Scenario: a test that exceeds the per-test timeout against a mutant kills it."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: "def add(a, b):\n    return a + b\n"},
        tests={_TESTS: "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"},
        mutants={
            _ADD_MUTANT: FixtureMutant(
                path=_SOURCE, old="    return a + b", new="    while True:\n        pass"
            )
        },
    )

    completed = fixture.run_engine("--workers", "1", "--timeout", "2")

    assert completed.returncode == 0, completed.stderr
    report = read_report(package=fixture.package)
    assert _killers(report=report)[_ADD_MUTANT] == [_node("test_add")]
    assert report["per_test_timeout_seconds"] == 2.0


def test_a_test_that_fails_against_the_unmutated_source_is_excluded_from_attribution(
    *, tmp_path: Path
) -> None:
    """Scenario: a test that fails against the unmutated source is excluded from attribution."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: "def add(a, b):\n    return a + b\n"},
        tests={
            _TESTS: (
                "import time\n\nfrom calc import add\n\n\n"
                "def test_broken():\n    assert add(2, 3) == 6\n\n\n"
                "def test_slow():\n    assert add(2, 3) == 5\n    time.sleep(4)\n\n\n"
                "def test_good():\n    assert add(2, 3) == 5\n"
            )
        },
        mutants={_ADD_MUTANT: _MINUS},
    )

    completed = fixture.run_engine("--workers", "1", "--timeout", "2")

    assert completed.returncode == 0, completed.stderr
    report = read_report(package=fixture.package)
    excluded = {_node("test_broken"), _node("test_slow")}
    assert set(cast("list[str]", report["baseline_failures"])) == excluded
    assert all(not excluded & set(killers) for killers in _killers(report=report).values())
    assert not excluded & set(cast("list[str]", report["redundancy_candidates"]))
    assert not excluded & set(cast("list[str]", report["unapplied_coverage_tests"]))
    assert _killers(report=report)[_ADD_MUTANT] == [_node("test_good")]


def test_a_mutant_the_engine_cannot_apply_is_recorded_and_the_run_continues(
    *, tmp_path: Path
) -> None:
    """Scenario: a mutant the engine cannot apply is recorded and the run continues."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: _ADD_AND_DOUBLE},
        tests={
            _TESTS: (
                "from calc import add, double\n\n\n"
                "def test_add():\n    assert add(2, 3) == 5\n\n\n"
                "def test_double():\n    assert double(4) == 8\n"
            )
        },
        mutants={
            _ADD_MUTANT: _MINUS,
            _DOUBLE_MUTANT: FixtureMutant(path=_SOURCE, old="text mutmut cannot find", new="x"),
        },
    )

    report = _ok(fixture=fixture)

    assert report["unapplied_mutants"] == [_DOUBLE_MUTANT]
    assert report["mutants_unapplied"] == 1
    assert report["mutants_generated"] == report["mutants_applied"] + report["mutants_unapplied"]
    assert _DOUBLE_MUTANT not in cast("list[str]", report["surviving_mutants"])
    assert _killers(report=report)[_DOUBLE_MUTANT] == []
    assert report["unapplied_coverage_tests"] == [_node("test_double")]
    assert _node("test_double") not in cast("list[str]", report["redundancy_candidates"])


def test_a_kill_matrix_run_in_which_no_mutant_applies_exits_non_zero(*, tmp_path: Path) -> None:
    """Scenario: a kill-matrix run in which no mutant applies exits non-zero."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: "def add(a, b):\n    return a + b\n"},
        tests={_TESTS: "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n"},
        mutants={_ADD_MUTANT: FixtureMutant(path=_SOURCE, old="absent text", new="x")},
    )

    completed = fixture.run_engine("--workers", "1", "--timeout", "10")

    assert completed.returncode != 0
    assert "applied mutant set is empty" in completed.stderr
    assert not (fixture.package / "reports" / "mutation-kill-matrix.json").exists()


def _two_function_fixture(*, root: Path) -> KillMatrixFixture:
    """add is covered only by test_add and double only by test_double."""
    return KillMatrixFixture.create(
        root=root,
        sources={_SOURCE: _ADD_AND_DOUBLE},
        tests={
            _TESTS: (
                "from calc import add, double\n\n\n"
                "def test_add():\n    assert add(2, 3) == 5\n\n\n"
                "def test_double():\n    assert double(4) == 8\n"
            )
        },
        mutants={_ADD_MUTANT: _MINUS, _DOUBLE_MUTANT: _TRIPLE},
    )


def test_an_unchanged_package_is_not_re_tested_on_a_second_kill_matrix_run(
    *, tmp_path: Path
) -> None:
    """Scenario: an unchanged package is not re-tested on a second kill-matrix run."""
    fixture = _two_function_fixture(root=tmp_path)
    first = _ok(fixture=fixture)
    applied_after_first = applied_mutants(fixture=fixture)

    second = _ok(fixture=fixture)

    assert applied_mutants(fixture=fixture) == applied_after_first
    assert matrix_content(document=second) == matrix_content(document=first)
    assert second["run"] == {"incremental": True, "reused_mutants": 2, "workers": 1}


def test_a_changed_functions_mutants_are_re_tested_on_an_incremental_run(*, tmp_path: Path) -> None:
    """Scenario: a changed function's mutants are re-tested on an incremental run."""
    fixture = _two_function_fixture(root=tmp_path)
    _ = _ok(fixture=fixture)
    applied_after_first = len(applied_mutants(fixture=fixture))
    fixture.write(
        files={_SOURCE: _ADD_AND_DOUBLE.replace("return x * 2", "return x * 2 if x != 99 else -1")}
    )

    report = _ok(fixture=fixture)

    assert applied_mutants(fixture=fixture)[applied_after_first:] == [_DOUBLE_MUTANT]
    assert cast("dict[str, object]", report["run"])["reused_mutants"] == 1


def test_a_change_to_a_data_file_a_test_reads_re_tests_the_mutants_that_test_covers(
    *, tmp_path: Path
) -> None:
    """Scenario: a change to a data file a test reads re-tests the mutants that test covers."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: "def add(a, b):\n    return a + b\n"},
        tests={
            _TESTS: (
                "import pathlib\n\nfrom calc import add\n\n\n"
                "def test_t1():\n"
                "    mode = (pathlib.Path(__file__).parent / 'mode.txt').read_text().strip()\n"
                "    assert add(2, 3) == 5 if mode == 'strict' else add(2, 3) is not None\n"
            ),
            "tests/mode.txt": "strict\n",
        },
        mutants={_ADD_MUTANT: _MINUS},
    )
    first = _ok(fixture=fixture)
    assert _killers(report=first)[_ADD_MUTANT] == [_node("test_t1")]
    applied_after_first = len(applied_mutants(fixture=fixture))
    fixture.write(files={"tests/mode.txt": "lenient\n"})

    second = _ok(fixture=fixture)

    assert applied_mutants(fixture=fixture)[applied_after_first:] == [_ADD_MUTANT]
    assert _killers(report=second)[_ADD_MUTANT] == []


def test_a_cached_killer_that_is_no_longer_a_test_is_dropped_and_its_mutant_re_tested(
    *, tmp_path: Path
) -> None:
    """Scenario: a cached killer that is no longer a test is dropped and its mutant re-tested."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: "def add(a, b):\n    return a + b\n"},
        tests={
            _TESTS: "from calc import add\n\n\ndef test_t1():\n    assert add(2, 3) == 5\n",
            "tests/test_other.py": "from calc import add\n\n\ndef test_t2():\n    assert add(0, 0) == 0\n",
        },
        mutants={_ADD_MUTANT: _MINUS},
    )
    first = _ok(fixture=fixture)
    assert _killers(report=first)[_ADD_MUTANT] == [_node("test_t1")]
    applied_after_first = len(applied_mutants(fixture=fixture))
    (fixture.package / _TESTS).unlink()

    second = _ok(fixture=fixture)

    assert all(_node("test_t1") not in killers for killers in _killers(report=second).values())
    assert applied_mutants(fixture=fixture)[applied_after_first:] == [_ADD_MUTANT]


def _keep_previous(*, fixture: KillMatrixFixture) -> str:
    """Copy the current report aside, as a previous report the next run compares to."""
    previous = fixture.package.parent / "previous-report.json"
    _ = shutil.copyfile(fixture.package / "reports" / "mutation-kill-matrix.json", previous)
    return str(previous)


def test_a_kill_matrix_run_reports_newly_redundant_tests_since_the_previous_report(
    *, tmp_path: Path
) -> None:
    """Scenario: a kill-matrix run reports newly redundant tests since the previous report."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: "def add(a, b):\n    return a + b\n"},
        tests={_TESTS: "from calc import add\n\n\ndef test_t1():\n    assert add(2, 3) == 5\n"},
        mutants={_ADD_MUTANT: _MINUS},
    )
    first = _ok(fixture=fixture)
    assert _killers(report=first)[_ADD_MUTANT] == [_node("test_t1")]
    previous = _keep_previous(fixture=fixture)
    fixture.write(
        files={
            "tests/test_t2.py": "from calc import add\n\n\ndef test_t2():\n    assert add(1, 1) == 2\n"
        }
    )

    _ = _ok(fixture=fixture, arguments=("--previous-report", previous))

    summary = read_report(package=fixture.package, name="mutation-kill-matrix-changes.json")
    assert summary["new_redundancy_candidates"] == [
        {"status": "changed", "test": _node("test_t1")},
        {"status": "new", "test": _node("test_t2", file="tests/test_t2.py")},
    ]


def test_a_kill_matrix_run_reports_newly_surviving_mutants_since_the_previous_report(
    *, tmp_path: Path
) -> None:
    """Scenario: a kill-matrix run reports newly surviving mutants since the previous report."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: "def add(a, b):\n    return a + b\n"},
        tests={_TESTS: "from calc import add\n\n\ndef test_t1():\n    assert add(2, 3) == 5\n"},
        mutants={_ADD_MUTANT: _MINUS},
    )
    _ = _ok(fixture=fixture)
    previous = _keep_previous(fixture=fixture)
    fixture.write(
        files={
            _SOURCE: "def add(a, b):\n    return a + b\n\n\ndef triple(x):\n    return x * 3\n",
            _TESTS: "from calc import add\n\n\ndef test_t1():\n    assert add(2, 3) is not None\n",
        }
    )
    fixture.set_mutants(
        mutants={
            _ADD_MUTANT: _MINUS,
            "calc.x_triple__mutmut_1": FixtureMutant(path=_SOURCE, old="x * 3", new="x * 4"),
        }
    )

    _ = _ok(fixture=fixture, arguments=("--previous-report", previous))

    summary = read_report(package=fixture.package, name="mutation-kill-matrix-changes.json")
    surviving = cast("list[dict[str, str]]", summary["new_surviving_mutants"])
    assert [(row["mutant"], row["status"]) for row in surviving] == [
        (_ADD_MUTANT, "changed"),
        ("calc.x_triple__mutmut_1", "new"),
    ]


def test_a_surviving_mutant_whose_function_changed_is_flagged_in_the_what_changed_summary(
    *, tmp_path: Path
) -> None:
    """Scenario: a surviving mutant whose function changed is flagged in the what-changed summary."""
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={_SOURCE: "def add(a, b):\n    return a + b\n"},
        tests={_TESTS: "from calc import add\n\n\ndef test_t1():\n    assert add(2, 3) == 5\n"},
        mutants={_ADD_MUTANT: _MINUS},
    )
    first = _ok(fixture=fixture)
    assert "function_digest" in cast("list[dict[str, object]]", first["mutants"])[0]
    previous = _keep_previous(fixture=fixture)
    fixture.write(
        files={_SOURCE: "def add(a, b):\n    if b == 3:\n        return 5\n    return a + b\n"}
    )

    _ = _ok(fixture=fixture, arguments=("--previous-report", previous))

    summary = read_report(package=fixture.package, name="mutation-kill-matrix-changes.json")
    assert summary["new_surviving_mutants"] == [
        {"function": "function changed", "mutant": _ADD_MUTANT, "status": "changed"}
    ]


def _workflow_triggers(*, path: Path) -> set[str]:
    """Return a workflow's trigger names (YAML 1.1 reads the `on` key as True)."""
    document = cast("dict[object, object]", yaml.safe_load(path.read_text(encoding="utf-8")))
    triggers = document.get("on", document.get(True, {}))
    return {str(name) for name in (triggers if isinstance(triggers, dict | list) else [triggers])}


def test_a_scheduled_kill_matrix_run_writes_its_report_without_gating_anything(
    *, tmp_path: Path
) -> None:
    """Scenario: a scheduled kill-matrix run writes its report without gating anything."""
    fixture = _two_function_fixture(root=tmp_path)
    first = fixture.run_scheduled("--workers", "1", "--timeout", "10")
    assert first.returncode == 0, first.stderr
    assert "without a what-changed summary" in first.stdout
    first_report = read_report(package=fixture.package)
    fixture.write(
        files={
            _TESTS: (fixture.package / _TESTS).read_text()
            + "\n\ndef test_extra():\n    assert True\n"
        }
    )

    fired = fixture.run_scheduled("--workers", "1", "--timeout", "10")

    assert fired.returncode == 0, fired.stderr
    fresh = read_report(package=fixture.package)
    assert _node("test_extra") in cast("list[str]", fresh["tests"])
    assert fresh != first_report
    summary = read_report(package=fixture.package, name="mutation-kill-matrix-changes.json")
    assert summary["new_redundancy_candidates"] == [{"status": "new", "test": _node("test_extra")}]
    workflows = sorted((_REPO_ROOT / ".github" / "workflows").glob("*.y*ml"))
    triggers = {path: _workflow_triggers(path=path) for path in workflows}
    assert all(
        triggers[path] <= {"schedule", "workflow_dispatch"}
        for path in workflows
        if "mutation-kill-matrix" in path.read_text(encoding="utf-8")
    )
    schedule = (_REPO_ROOT / "docs" / "mutation-kill-matrix-scheduled.md").read_text(
        encoding="utf-8"
    )
    assert "just mutation-kill-matrix-scheduled" in schedule
    assert "concurrencyPolicy: Forbid" in schedule
