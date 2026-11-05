"""Tests for the scheduler's committed Honeycomb query-spec inventory."""

import dataclasses
import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_committed_tick_specs_are_frozen_typed_and_within_budget() -> None:
    """Each fixed tick query declares its complete offline data contract."""
    module_path = Path(__file__).parents[2] / "livespec_dev_tooling" / "radar_honeycomb_models.py"
    assert module_path.is_file(), "the scheduler needs committed Honeycomb query specs"

    models = importlib.import_module("livespec_dev_tooling.radar_honeycomb_models")

    assert dataclasses.is_dataclass(models.QuerySpec)
    assert models.QuerySpec.__dataclass_params__.frozen
    assert models.TICK_SPECS, "TICK_SPECS must contain the committed per-tick query inventory"

    count = len(models.TICK_SPECS)
    assert (
        count <= models.MAX_QUERIES_PER_TICK
    ), f"tick has {count} specs; MAX_QUERIES_PER_TICK={models.MAX_QUERIES_PER_TICK}"

    for spec in models.TICK_SPECS:
        assert spec.name
        assert spec.dataset
        assert spec.calculations
        assert spec.filters is not None
        assert spec.breakdowns is not None
        assert spec.window_seconds > 0
        assert spec.expected_columns
        assert all(isinstance(column, str) for column in spec.expected_columns)
        assert all(
            column_type in {str, float, int, bool} for column_type in spec.expected_columns.values()
        )
        assert spec.staleness_seconds > 0


def test_tick_budget_cites_the_steady_state_mcp_key_measurement() -> None:
    """The committed budget retains its host-captured measurement evidence."""
    source = (
        Path(__file__).parents[2] / "livespec_dev_tooling" / "radar_honeycomb_models.py"
    ).read_text()

    assert "about 36 queries/hour for the other callers" in source
    assert "40 queries/hour reserved" in source
    assert "2026-11-03 18:20:26Z to 19:20:29Z UTC" in source
    assert (
        "plan/radar-and-deterministic-admission/research/" "002-mcp-key-caller-rate-2026-11-03.md"
    ) in source
    assert "plan/token-spend-analysis/research/005" not in source
