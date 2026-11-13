"""Tests for the kill matrix's generate, measure and plan stages."""

from __future__ import annotations

import importlib
import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest

from tests.consumer.kill_matrix_fixture import FixtureMutant, KillMatrixFixture, read_report

__all__: list[str] = []


def _scripted(
    outputs: list[subprocess.CompletedProcess[str]],
    *,
    collection_text: str | None = '["t.py::a"]',
) -> Callable[..., subprocess.CompletedProcess[str]]:
    def execute(
        *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        _ = cwd, timeout
        if "--collect-only" in args and collection_text is not None:
            destinations = (
                arg.partition("=")[2] for arg in args if arg.startswith("KILL_MATRIX_COLLECTED=")
            )
            for destination in destinations:
                _ = Path(destination).write_text(collection_text, encoding="utf-8")
        return outputs.pop(0)

    return execute


@pytest.mark.parametrize(
    ("outputs", "message"),
    [
        ([subprocess.CompletedProcess([], 1, "", "")], "mutmut could not generate"),
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
        (
            [
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "M1: survived\n", ""),
                subprocess.CompletedProcess([], 2, "", ""),
            ],
            "pytest collection failed",
        ),
    ],
)
def test_generation_refuses_unusable_mutmut_output(
    *, tmp_path: Path, outputs: list[subprocess.CompletedProcess[str]], message: str
) -> None:
    """A failed or empty measurement cannot become a Rule-26 report."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")

    with pytest.raises(RuntimeError, match=message):
        _ = module.generate(execute=_scripted(outputs), target=tmp_path)


def test_generation_lists_mutants_and_collected_tests(*, tmp_path: Path) -> None:
    """Actual collected ids survive spaces; console messages are never test inventory."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")
    outputs = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "    pkg.x_f__mutmut_1: killed\n", ""),
        subprocess.CompletedProcess([], 0, "console.py::not_a_collected_test\n", ""),
    ]

    mutants, tests = module.generate(
        execute=_scripted(outputs, collection_text='["t.py::a", "t.py::b[x y]"]'),
        target=tmp_path,
    )

    assert [mutant.identifier for mutant in mutants] == ["pkg.x_f__mutmut_1"]
    assert tests == ["t.py::a", "t.py::b[x y]"]


@pytest.mark.parametrize("collection_text", [None, "{", "{}", '["t.py::a", 3]'])
def test_generation_refuses_a_missing_or_invalid_collection_inventory(
    *, tmp_path: Path, collection_text: str | None
) -> None:
    """A successful console exit cannot conceal missing or malformed collection data."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")
    outputs = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "pkg.x_f__mutmut_1: not checked\n", ""),
        subprocess.CompletedProcess([], 0, "t.py::a\n1 test collected\n", ""),
    ]

    with pytest.raises(RuntimeError, match="pytest collection inventory"):
        _ = module.generate(
            execute=_scripted(outputs, collection_text=collection_text), target=tmp_path
        )


def test_generation_only_generates_and_never_runs_mutmuts_own_mutation_run(
    *, tmp_path: Path
) -> None:
    """The engine needs mutmut's catalogue, not its run.

    `mutmut run` in 3.2.3 also runs mutmut's own per-test stats pass, a clean
    test run and a forked run of every mutant, all of which the engine
    discards.  Generation goes through mutmut's own generation functions.
    """
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_stages")
    calls: list[list[str]] = []
    outputs = [
        subprocess.CompletedProcess([], 0, "", ""),
        subprocess.CompletedProcess([], 0, "    pkg.x_f__mutmut_1: not checked\n", ""),
        subprocess.CompletedProcess([], 0, "t.py::a\n", ""),
    ]
    scripted = _scripted(outputs)

    def execute(
        *, args: list[str], cwd: Path, timeout: float | None = None
    ) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        return scripted(args=args, cwd=cwd, timeout=timeout)

    _ = module.generate(execute=execute, target=tmp_path)

    generation = calls[0]
    assert generation[generation.index("-c") + 1].count("create_mutants()") == 1
    assert all(call[-1] != "run" for call in calls)


def test_selection_preserves_the_whole_node_id_in_each_line(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Spaced parameter values and file names remain one exact selected test each."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_pytest_plugin")
    names = ["tests/test values.py::test_case[has spaces]", "t.py::test_case[é value]"]
    items = [Mock(nodeid=name) for name in [*names, "t.py::other"]]
    select = tmp_path / "selected.txt"
    _ = select.write_text("\n".join(names) + "\n", encoding="utf-8")
    monkeypatch.setenv(module.SELECT_VARIABLE, str(select))
    config = Mock()

    module.pytest_collection_modifyitems(config, items)

    assert [item.nodeid for item in items] == names
    assert [item.nodeid for item in config.hook.pytest_deselected.call_args.kwargs["items"]] == [
        "t.py::other"
    ]


def test_collection_inventory_records_exact_final_items_only_when_requested(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Machine-readable collection uses the final pytest items, independently of console text."""
    module = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_pytest_plugin")
    inventory = tmp_path / "collected.json"
    monkeypatch.delenv("KILL_MATRIX_COLLECTED", raising=False)
    names = ["t.py::a[has spaces]", "t.py::b"]
    session = Mock(items=[Mock(nodeid=name) for name in names])

    hook = getattr(module, "pytest_collection_finish", None)
    assert callable(hook), "the engine must capture the actual pytest item inventory"
    hook(session)
    assert not inventory.exists()
    monkeypatch.setenv("KILL_MATRIX_COLLECTED", str(inventory))
    hook(session)
    assert json.loads(inventory.read_text(encoding="utf-8")) == names


@pytest.mark.consumer
def test_spaced_parameter_ids_keep_their_own_kill_outcomes(*, tmp_path: Path) -> None:
    """Console text cannot add tests, and spaced ids cannot disappear or become false killers."""
    mutant = "calc.x_add__mutmut_1"
    fixture = KillMatrixFixture.create(
        root=tmp_path,
        sources={"src/calc/__init__.py": "def add(a, b):\n    return a + b\n"},
        tests={
            "tests/test_calc.py": (
                "import pytest\nfrom calc import add\n\n"
                "@pytest.mark.parametrize('a,b,want', [(2, 3, 5), (0, 0, 0)], "
                "ids=['catches mutant', 'weak assertion'])\n"
                "def test_add(a, b, want):\n    assert add(a, b) == want\n"
            ),
            "tests/conftest.py": (
                "def pytest_terminal_summary(terminalreporter):\n"
                "    terminalreporter.write_line('invented.py::not_a_collected_test')\n"
            ),
        },
        mutants={mutant: FixtureMutant(path="src/calc/__init__.py", old="a + b", new="a - b")},
    )

    completed = fixture.run_engine("--workers", "1", "--timeout", "10", "--no-cache")

    assert completed.returncode == 0, completed.stderr
    report = read_report(package=fixture.package)
    catches = "tests/test_calc.py::test_add[catches mutant]"
    weak = "tests/test_calc.py::test_add[weak assertion]"
    assert report["tests"] == [catches, weak]
    rows = cast("list[dict[str, object]]", report["mutants"])
    assert [(row["identifier"], row["killed_by"]) for row in rows] == [(mutant, [catches])]
    assert report["baseline_failures"] == []
    assert report["surviving_mutants"] == []
    assert report["redundancy_candidates"] == [weak]
