"""Typed, committed Honeycomb query specs used by the scheduler reader."""

import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_committed_tick_specs_are_typed_and_fit_the_measured_budget() -> None:
    """The tick's fixed query inventory names every part of its Honeycomb contract."""
    module_path = Path(__file__).parents[2] / "livespec_dev_tooling" / "radar_honeycomb_models.py"
    assert module_path.is_file(), "the reader needs committed typed query specs"
    models = importlib.import_module("livespec_dev_tooling.radar_honeycomb_models")
    assert models.TICK_SPECS, "TICK_SPECS must contain the committed per-tick query inventory"
    assert (
        len(models.TICK_SPECS) <= models.MAX_QUERIES_PER_TICK
    ), f"tick has {len(models.TICK_SPECS)} specs; MAX_QUERIES_PER_TICK={models.MAX_QUERIES_PER_TICK}"
    for spec in models.TICK_SPECS:
        assert spec.dataset
        assert spec.calculations
        assert spec.filters is not None
        assert spec.breakdowns is not None
        assert spec.window_seconds > 0
        assert spec.expected_columns
        assert spec.staleness_seconds > 0
        assert spec.name in models.FALLBACK_TABLE
