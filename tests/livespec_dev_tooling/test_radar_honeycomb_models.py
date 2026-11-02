"""Typed, committed Honeycomb query specs used by the scheduler reader."""

import pytest

from livespec_dev_tooling.radar_honeycomb_models import (
    FALLBACK_TABLE,
    MAX_QUERIES_PER_TICK,
    TICK_SPECS,
)

pytestmark = pytest.mark.integration


def test_committed_tick_specs_are_typed_and_fit_the_measured_budget() -> None:
    """The tick's fixed query inventory names every part of its Honeycomb contract."""
    assert TICK_SPECS, "TICK_SPECS must contain the committed per-tick query inventory"
    assert (
        len(TICK_SPECS) <= MAX_QUERIES_PER_TICK
    ), f"tick has {len(TICK_SPECS)} specs; MAX_QUERIES_PER_TICK={MAX_QUERIES_PER_TICK}"
    for spec in TICK_SPECS:
        assert spec.dataset
        assert spec.calculations
        assert spec.filters is not None
        assert spec.breakdowns is not None
        assert spec.window_seconds > 0
        assert spec.expected_columns
        assert spec.staleness_seconds > 0
        assert spec.name in FALLBACK_TABLE
