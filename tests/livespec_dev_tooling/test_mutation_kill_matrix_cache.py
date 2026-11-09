"""Tests for the kill matrix's content-keyed result cache."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.mutation_kill_matrix_cache"
_SOURCE = "def add(a, b):\n    return a + b\n\n\n@staticmethod\ndef double(x):\n    return x * 2\n"


def _execute() -> object:
    return importlib.import_module(
        "livespec_dev_tooling.mutation_kill_matrix_execution"
    ).execute_command


def _span(*, path: str = "src/calc.py", digest: str = "fd") -> object:
    selection = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_selection")
    return selection.MutantSpan(path=path, first_line=2, last_line=2, function_digest=digest)


def _target(*, root: Path) -> Path:
    target = root / "pkg"
    files = {
        "src/calc.py": _SOURCE,
        "src/broken.py": "def (:\n",
        "tests/test_calc.py": "from calc import add\n\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        "tests/conftest.py": "",
        "tests/data.txt": "5\n",
        "pyproject.toml": "[project]\nname = 'calc'\n",
        "reports/mutation-kill-matrix.json": "{}",
        "mutants/src/calc.py": "mutated",
        "src/__pycache__/calc.cpython-310.pyc": "bytes",
        ".coverage": "data",
    }
    for relative, text in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(text, encoding="utf-8")
    return target


def test_tree_files_list_inputs_and_skip_caches_and_outputs(*, tmp_path: Path) -> None:
    """Both the walked and the git-listed views keep inputs and drop generated files."""
    module = importlib.import_module(_MODULE)
    target = _target(root=tmp_path)
    expected = [
        Path("pyproject.toml"),
        Path("src/broken.py"),
        Path("src/calc.py"),
        Path("tests/conftest.py"),
        Path("tests/data.txt"),
        Path("tests/test_calc.py"),
    ]

    assert module.tree_files(target=target, execute=_execute()) == expected

    _ = subprocess.run(["git", "init", "-q"], cwd=target, check=True)
    _ = (target / ".gitignore").write_text("ignored.txt\n", encoding="utf-8")
    _ = (target / "ignored.txt").write_text("x", encoding="utf-8")
    assert module.tree_files(target=target, execute=_execute()) == sorted(
        [*expected, Path(".gitignore")]
    )


def _keys(*, target: Path, coverage: object) -> object:
    module = importlib.import_module(_MODULE)
    return module.CacheKeys(
        target=target, coverage=coverage, engine_version="3.2.3", timeout=10.0, execute=_execute()
    )


_T = "tests/test_calc.py::test_add"
_COVERAGE = {
    "src/calc.py": {
        1: frozenset({""}),
        2: frozenset({_T}),
        5: frozenset({""}),
        7: frozenset({"t::double"}),
    },
    "tests/test_calc.py": {5: frozenset({_T})},
    "src/missing.py": {1: frozenset({_T})},
}


def test_a_key_moves_with_its_own_function_and_its_tests_code_but_not_with_others(
    *, tmp_path: Path
) -> None:
    """Editing double's body moves double's keys only; a data file moves every key."""
    target = _target(root=tmp_path)
    before = _keys(target=target, coverage=_COVERAGE)
    add_key = before.key(identifier="calc.x_add__mutmut_1", span=_span(), selected=[_T])

    _ = (target / "src/calc.py").write_text(_SOURCE.replace("x * 2", "x * 2 + 0"), encoding="utf-8")
    after_body = _keys(target=target, coverage=_COVERAGE)
    assert after_body.key(identifier="calc.x_add__mutmut_1", span=_span(), selected=[_T]) == add_key
    assert after_body.key(
        identifier="calc.x_double__mutmut_1", span=_span(), selected=["t::double"]
    ) != before.key(identifier="calc.x_double__mutmut_1", span=_span(), selected=["t::double"])

    _ = (target / "tests/data.txt").write_text("6\n", encoding="utf-8")
    after_data = _keys(target=target, coverage=_COVERAGE)
    assert after_data.key(identifier="calc.x_add__mutmut_1", span=_span(), selected=[_T]) != add_key


def test_unattributable_code_falls_back_to_the_whole_source(*, tmp_path: Path) -> None:
    """No coverage, no span, or an unmeasured selected test keys on all Python source."""
    target = _target(root=tmp_path)
    unmeasured = _keys(target=target, coverage=None)
    measured = _keys(target=target, coverage=_COVERAGE)

    without_span = measured.key(identifier="M", span=None, selected=[_T])
    unknown_test = measured.key(identifier="M", span=_span(), selected=["t::unmeasured"])
    no_coverage = unmeasured.key(identifier="M", span=_span(), selected=[_T])
    _ = (target / "src/broken.py").write_text("def (:\n    pass\n", encoding="utf-8")
    edited = _keys(target=target, coverage=_COVERAGE)

    assert edited.key(identifier="M", span=None, selected=[_T]) != without_span
    assert edited.key(identifier="M", span=_span(), selected=["t::unmeasured"]) != unknown_test
    assert edited.key(identifier="M", span=_span(), selected=[_T]) == measured.key(
        identifier="M", span=_span(), selected=[_T]
    )
    assert no_coverage != measured.key(identifier="M", span=_span(), selected=[_T])


def test_the_cache_round_trips_and_refuses_what_it_cannot_trust(*, tmp_path: Path) -> None:
    """Only a readable document of this schema is a cache."""
    module = importlib.import_module(_MODULE)
    path = tmp_path / "reports" / "cache.json"
    entries = {
        "k1": module.CachedOutcome(unapplied=False, killed_by=("t::a",)),
        "k2": module.CachedOutcome(unapplied=True, killed_by=()),
    }

    module.save_cache(path=path, entries=entries)

    assert module.load_cache(path=path) == entries
    assert module.load_cache(path=None) is None
    assert module.load_cache(path=tmp_path / "absent.json") is None
    for text in ("not json", "[]", json.dumps({"schema": "other", "entries": {}})):
        _ = path.write_text(text, encoding="utf-8")
        assert module.load_cache(path=path) is None


@pytest.mark.parametrize("name", ["setup.py", "conftest.py", "requirements-dev.txt", "data.bin"])
def test_environmental_files_reach_every_key(*, name: str, tmp_path: Path) -> None:
    """Settings, conftest and data files are in every mutant's key."""
    target = _target(root=tmp_path)
    path = target / name
    _ = path.write_text("one\n", encoding="utf-8")
    before = _keys(target=target, coverage=_COVERAGE).key(
        identifier="M", span=_span(), selected=[_T]
    )

    _ = path.write_text("two\n", encoding="utf-8")

    assert (
        _keys(target=target, coverage=_COVERAGE).key(identifier="M", span=_span(), selected=[_T])
        != before
    )
