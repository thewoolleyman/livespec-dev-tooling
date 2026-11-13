"""Cache reuse follows the executing source even after a target resyncs its venv."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

__all__: list[str] = []


def _target(root: Path) -> Path:
    target = root / "target"
    target.mkdir()
    _ = (target / "calc.py").write_text("def add(a, b):\n    return a + b\n")
    return target


def _engine(root: Path) -> Path:
    root.mkdir()
    for name in (
        "mutation_kill_matrix.py",
        "mutation_kill_matrix_cache.py",
        "mutation_kill_matrix_execution.py",
        "mutation_kill_matrix_pytest_plugin.py",
        "mutation_kill_matrix_selection.py",
    ):
        _ = (root / name).write_text("# executing engine version one\n")
    return root / "mutation_kill_matrix_cache.py"


def _keys(target: Path) -> tuple[str, str]:
    cache = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_cache")
    measurement = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_measurement")
    execution = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_execution")
    keys = cache.CacheKeys(
        target=target,
        coverage=None,
        engine_version="3.2.3",
        timeout=120.0,
        execute=execution.execute_command,
    )
    return (
        keys.key(identifier="calc.x_add__mutmut_1", span=None, selected=["test_add"]),
        measurement.measurement_key(
            target=target,
            tests=["test_add"],
            engine_version="3.2.3",
            timeout=120.0,
            execute=execution.execute_command,
        ),
    )


@pytest.mark.parametrize(
    "component",
    [
        "mutation_kill_matrix.py",
        "mutation_kill_matrix_execution.py",
        "mutation_kill_matrix_pytest_plugin.py",
        "mutation_kill_matrix_selection.py",
    ],
)
def test_changed_executing_source_invalidates_outcome_and_measurement_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, component: str
) -> None:
    """Installed metadata stays fixed while PYTHONPATH's actual engine changes."""
    cache = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_cache")
    engine = _engine(tmp_path / "engine")
    monkeypatch.setattr(cache, "__file__", str(engine))
    target = _target(tmp_path)
    before_outcome, before_measurement = _keys(target)

    _ = engine.with_name(component).write_text("# executing engine version two\n")
    after_outcome, after_measurement = _keys(target)

    assert after_outcome != before_outcome
    assert after_measurement != before_measurement


def test_identical_engine_bytes_at_a_different_path_keep_both_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A relocated checkout still reuses evidence for identical executing source."""
    cache = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_cache")
    first = _engine(tmp_path / "first")
    second = _engine(tmp_path / "second")
    target = _target(tmp_path)
    monkeypatch.setattr(cache, "__file__", str(first))
    before = _keys(target)

    monkeypatch.setattr(cache, "__file__", str(second))
    assert _keys(target) == before


def test_an_unreadable_source_identity_refuses_cache_reuse(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An empty source directory cannot masquerade as a known engine version."""
    cache = importlib.import_module("livespec_dev_tooling.mutation_kill_matrix_cache")
    engine = tmp_path / "absent" / "mutation_kill_matrix_cache.py"
    monkeypatch.setattr(cache, "__file__", str(engine))

    with pytest.raises((OSError, RuntimeError), match="engine|source"):
        _ = _keys(_target(tmp_path))
