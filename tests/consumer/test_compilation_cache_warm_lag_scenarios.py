"""Consumer-tier coverage for compilation-cache warm-set lag scenarios."""

from __future__ import annotations

import importlib.util
from pathlib import Path

__all__: list[str] = []

_ROOT = Path(__file__).resolve().parents[2]
_HELPER = _ROOT / "ci-runner" / "k3s" / "phase2" / "warm-cache" / "sccache-warm-lag.py"


def _transition_module() -> object:
    """Load the populator's pure transition helper as its consumer does."""
    assert _HELPER.is_file(), (
        "the populator must ship a pure per-repository warm-set lag transition helper; "
        "without it, busy skips can only be counted as fleet totals"
    )
    spec = importlib.util.spec_from_file_location("sccache_warm_lag", _HELPER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_busy_skips_start_and_accumulate_per_repository_lag() -> None:
    """Two busy skips preserve the cache record and age one repository's warm set."""
    module = _transition_module()
    previous = {
        "consecutive_skipped_busy": 1,
        "last_built_commit": "old",
        "last_built_toolchain": "1.80.0",
        "lag_started_at_epoch": 100,
    }

    updated = module.transition(
        previous=previous,
        outcome="busy",
        run_started_at_epoch=200,
        default_branch_commit="new",
        checkout_toolchain="1.81.0",
        cache_record_commit="old",
        cache_record_toolchain="1.80.0",
    )

    assert updated == {
        "consecutive_skipped_busy": 2,
        "last_built_commit": "old",
        "last_built_toolchain": "1.80.0",
        "lag_started_at_epoch": 100,
    }


def test_current_or_recorded_build_clears_lag_and_a_failed_build_does_not() -> None:
    """A successful/current warm set clears; every read-but-non-busy failure breaks the streak."""
    module = _transition_module()
    previous = {
        "consecutive_skipped_busy": 3,
        "last_built_commit": "old",
        "last_built_toolchain": "1.80.0",
        "lag_started_at_epoch": 100,
    }
    for outcome in ("current", "built"):
        assert module.transition(
            previous=previous,
            outcome=outcome,
            run_started_at_epoch=200,
            default_branch_commit="new",
            checkout_toolchain="1.81.0",
            cache_record_commit="new",
            cache_record_toolchain="1.81.0",
        ) == {
            "consecutive_skipped_busy": 0,
            "last_built_commit": "new",
            "last_built_toolchain": "1.81.0",
            "lag_started_at_epoch": None,
        }
    assert module.transition(
        previous=previous,
        outcome="failed",
        run_started_at_epoch=200,
        default_branch_commit="new",
        checkout_toolchain="1.81.0",
        cache_record_commit="old",
        cache_record_toolchain="1.80.0",
    ) == {**previous, "consecutive_skipped_busy": 0}


def test_unreadable_and_unvisited_cache_records_follow_the_required_preservation_rules() -> None:
    """An unreadable record keeps old fields; a pre-record stop keeps the whole prior state."""
    module = _transition_module()
    previous = {
        "consecutive_skipped_busy": 2,
        "last_built_commit": "old",
        "last_built_toolchain": "1.80.0",
        "lag_started_at_epoch": 100,
    }
    assert module.transition(
        previous=previous,
        outcome="unreadable",
        run_started_at_epoch=200,
        default_branch_commit="new",
        checkout_toolchain="1.81.0",
        cache_record_commit=None,
        cache_record_toolchain=None,
    ) == {**previous, "consecutive_skipped_busy": 0}
    assert (
        module.transition(
            previous=previous,
            outcome="unvisited",
            run_started_at_epoch=200,
            default_branch_commit="new",
            checkout_toolchain="1.81.0",
            cache_record_commit=None,
            cache_record_toolchain=None,
        )
        == previous
    )
