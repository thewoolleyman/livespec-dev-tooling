"""Tests that the kill matrix reuses a stored baseline measurement only while nothing moved.

Measuring per-test coverage runs the target's whole suite serially, which took
about 3.6 hours on run 20261111t1.  A run resumed from the result cache would
repeat that before it could reuse anything, so the measurement is stored beside
the result cache under a key that covers everything the baseline run depends on.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

__all__: list[str] = []


_MODULE = "livespec_dev_tooling.mutation_kill_matrix_measurement"
_T1 = "tests/test_calc.py::test_add"
_T2 = "tests/test_calc.py::test_double"
_COVERAGE = {
    "src/calc.py": {1: frozenset({""}), 2: frozenset({_T1}), 6: frozenset({_T1, _T2})},
    "tests/test_calc.py": {5: frozenset({_T1}), 9: frozenset({_T1, _T2})},
}


def _execute() -> object:
    return importlib.import_module(
        "livespec_dev_tooling.mutation_kill_matrix_execution"
    ).execute_command


def _target(*, root: Path) -> Path:
    target = root / "pkg"
    files = {
        "src/calc.py": "def add(a, b):\n    return a + b\n",
        "tests/test_calc.py": "from calc import add\n",
        "tests/data.bin": "5\n",
        "reports/mutation-kill-matrix.json": "{}",
        "mutants/src/calc.py": "mutated",
    }
    for relative, text in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text(text, encoding="utf-8")
    return target


def _key(
    *,
    target: Path,
    tests: list[str] | None = None,
    timeout: float = 60.0,
    engine_version: str = "3.2.3",
) -> str:
    module = importlib.import_module(_MODULE)
    key: str = module.measurement_key(
        target=target,
        tests=[_T1, _T2] if tests is None else tests,
        engine_version=engine_version,
        timeout=timeout,
        execute=_execute(),
    )
    return key


def test_a_stored_measurement_round_trips_under_its_own_key_only(*, tmp_path: Path) -> None:
    """The coverage map and the baseline failures come back whole, and only for the same key."""
    module = importlib.import_module(_MODULE)
    path = module.measurement_path(cache_path=tmp_path / "cache" / "kill-matrix-cache.json")
    measurement = module.Measurement(coverage=_COVERAGE, baseline_failures=frozenset({_T2}))

    module.save_measurement(path=path, key="k1", measurement=measurement)

    assert path == tmp_path / "cache" / "kill-matrix-cache-measure.json"
    assert module.load_measurement(path=path, key="k1") == measurement
    assert module.load_measurement(path=path, key="k2") is None
    assert [entry.name for entry in path.parent.iterdir()] == [path.name]
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored["tests"] == ["", _T1, _T2]
    assert sorted(stored["sets"]) == [[0], [1], [1, 2]]


def test_a_run_without_a_cache_or_without_coverage_stores_nothing(*, tmp_path: Path) -> None:
    """No cache path means no stored measurement, and an unmeasured run is never reused."""
    module = importlib.import_module(_MODULE)
    path = tmp_path / "measure.json"
    unmeasured = module.Measurement(coverage=None, baseline_failures=frozenset())

    module.save_measurement(path=path, key="k1", measurement=unmeasured)
    module.save_measurement(path=None, key="k1", measurement=unmeasured)

    assert module.measurement_path(cache_path=None) is None
    assert not path.exists()
    assert module.load_measurement(path=None, key="k1") is None
    assert module.load_measurement(path=path, key="k1") is None


@pytest.mark.parametrize(
    "text",
    [
        "not json",
        "[]",
        json.dumps({"schema": "other", "key": "k1"}),
        json.dumps({"schema": "rule-26-kill-matrix-measurement/1", "key": "k1"}),
    ],
)
def test_a_stored_measurement_that_cannot_be_trusted_is_not_reused(
    *, text: str, tmp_path: Path
) -> None:
    """Only a readable, complete document of this schema is a measurement."""
    module = importlib.import_module(_MODULE)
    path = tmp_path / "measure.json"
    _ = path.write_text(text, encoding="utf-8")

    assert module.load_measurement(path=path, key="k1") is None


def test_the_key_moves_with_every_input_of_the_baseline_run_and_with_nothing_else(
    *, tmp_path: Path
) -> None:
    """A source, test or data file, the tests collected and the timeout each move the key."""
    target = _target(root=tmp_path)
    before = _key(target=target)

    _ = (target / "reports" / "mutation-kill-matrix.json").write_text("{1}", encoding="utf-8")
    _ = (target / "mutants" / "src" / "calc.py").write_text("again", encoding="utf-8")
    assert _key(target=target) == before
    assert _key(target=target, tests=[_T1]) != before
    assert _key(target=target, timeout=30.0) != before

    for relative in ("src/calc.py", "tests/test_calc.py", "tests/data.bin"):
        original = (target / relative).read_text(encoding="utf-8")
        _ = (target / relative).write_text(original + "#\n", encoding="utf-8")
        assert _key(target=target) != before
        _ = (target / relative).write_text(original, encoding="utf-8")
    assert _key(target=target) == before


class _Distribution:
    """A stand-in for one installed distribution: a name and a version."""

    def __init__(self, *, name: str, version: str) -> None:
        self.metadata = {"Name": name}
        self.version = version


def test_the_key_moves_with_the_engine_the_python_version_and_the_dependency_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A different engine, interpreter or installed distribution is a different baseline run."""
    module = importlib.import_module(_MODULE)
    target = _target(root=tmp_path)
    installed = [_Distribution(name="pytest", version="8.0.0")]
    monkeypatch.setattr(module.metadata, "distributions", lambda: list(installed))
    monkeypatch.setattr(module.platform, "python_version", lambda: "3.10.16")
    before = _key(target=target)

    assert _key(target=target, engine_version="3.2.4") != before

    monkeypatch.setattr(module.platform, "python_version", lambda: "3.10.17")
    assert _key(target=target) != before
    monkeypatch.setattr(module.platform, "python_version", lambda: "3.10.16")
    assert _key(target=target) == before

    installed[0] = _Distribution(name="pytest", version="8.0.1")
    assert _key(target=target) != before
    installed[0] = _Distribution(name="pytest", version="8.0.0")
    installed.append(_Distribution(name="coverage", version="7.0.0"))
    assert _key(target=target) != before
    _ = installed.pop()
    assert _key(target=target) == before


def test_a_reused_measurement_judges_its_stored_baseline_failures_again(*, tmp_path: Path) -> None:
    """A stored failure is re-judged on reuse, so a one-off failure does not stick."""
    module = importlib.import_module(_MODULE)
    path = tmp_path / "measure.json"
    measured = module.Measurement(coverage=_COVERAGE, baseline_failures=frozenset({_T1, _T2}))
    asked: list[frozenset[str]] = []

    def measure() -> object:
        return measured

    def rejudge(*, failures: frozenset[str]) -> frozenset[str]:
        asked.append(failures)
        return frozenset({_T2})

    first = module.reuse_or_measure(path=path, key="k1", measure=measure, rejudge=rejudge)
    assert first == measured
    assert asked == []

    reused = module.reuse_or_measure(path=path, key="k1", measure=measure, rejudge=rejudge)
    assert asked == [frozenset({_T1, _T2})]
    assert reused == module.Measurement(coverage=_COVERAGE, baseline_failures=frozenset({_T2}))
    assert module.reuse_or_measure(path=path, key="k1", measure=measure) == measured


def test_only_a_stored_failure_that_fails_again_on_the_unmutated_target_is_kept(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each stored failure runs again, alone from the mutants, and is kept only if it fails."""
    module = importlib.import_module(_MODULE)
    target = tmp_path / "pkg"
    (target / "tests").mkdir(parents=True)
    _ = (target / "tests" / "test_calc.py").write_text(
        "def test_add():\n    assert 1 + 1 == 2\n\n\ndef test_double():\n    assert 2 * 2 == 5\n",
        encoding="utf-8",
    )
    for name in (
        "COVERAGE_PROCESS_START",
        "COV_CORE_CONFIG",
        "COV_CORE_DATAFILE",
        "COV_CORE_SOURCE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PYTHONDONTWRITEBYTECODE", "1")

    kept = module.still_failing(
        execute=_execute(), target=target, failures=frozenset({_T1, _T2}), timeout=30.0
    )

    assert kept == frozenset({_T2})
    assert (
        module.still_failing(execute=_execute(), target=target, failures=frozenset(), timeout=30.0)
        == frozenset()
    )


def test_a_matching_stored_measurement_is_reused_and_anything_else_is_measured(
    *, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The measure stage runs only when no measurement is stored under this key."""
    module = importlib.import_module(_MODULE)
    path = tmp_path / "measure.json"
    measurement = module.Measurement(coverage=_COVERAGE, baseline_failures=frozenset())
    runs: list[str] = []

    def measure() -> object:
        runs.append("measured")
        return measurement

    assert module.reuse_or_measure(path=path, key="k1", measure=measure) == measurement
    assert capsys.readouterr().err == ""
    assert module.reuse_or_measure(path=path, key="k1", measure=measure) == measurement
    assert runs == ["measured"]
    assert "reused the stored per-test coverage" in capsys.readouterr().err
    assert module.reuse_or_measure(path=path, key="k2", measure=measure) == measurement
    assert runs == ["measured", "measured"]
