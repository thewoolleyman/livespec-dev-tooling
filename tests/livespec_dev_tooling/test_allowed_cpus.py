"""Tests for the single allowed-CPU reading (cgroup quota, else affinity, else count)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from livespec_dev_tooling.allowed_cpus import allowed_cpu_count, current_allowed_cpu_count

__all__: list[str] = []


def _affinity(*, count: int) -> Callable[[int], set[int]]:
    return lambda _pid: set(range(count))


def test_quota_of_six_cpus_wins_over_a_72_cpu_affinity_mask() -> None:
    got = allowed_cpu_count(cpu_max="600000 100000\n", affinity=_affinity(count=72), cpu_count=72)
    assert got == 6


def test_unlimited_quota_falls_back_to_the_affinity_mask() -> None:
    got = allowed_cpu_count(cpu_max="max 100000\n", affinity=_affinity(count=4), cpu_count=72)
    assert got == 4


def test_absent_quota_falls_back_to_the_affinity_mask() -> None:
    got = allowed_cpu_count(cpu_max=None, affinity=_affinity(count=4), cpu_count=72)
    assert got == 4


def test_quota_larger_than_the_affinity_mask_is_bounded_by_the_mask() -> None:
    got = allowed_cpu_count(cpu_max="800000 100000", affinity=_affinity(count=2), cpu_count=72)
    assert got == 2


def test_no_affinity_falls_back_to_cpu_count_then_to_one() -> None:
    assert allowed_cpu_count(cpu_max=None, affinity=None, cpu_count=12) == 12
    assert allowed_cpu_count(cpu_max=None, affinity=None, cpu_count=None) == 1


def test_fractional_quota_rounds_down_but_never_below_one() -> None:
    assert allowed_cpu_count(cpu_max="250000 100000", affinity=None, cpu_count=8) == 2
    assert allowed_cpu_count(cpu_max="50000 100000", affinity=None, cpu_count=8) == 1


def test_malformed_quota_text_is_ignored() -> None:
    for text in ("", "garbage", "abc 100000", "100000 0", "0 100000", "-1 100000"):
        assert allowed_cpu_count(cpu_max=text, affinity=_affinity(count=3), cpu_count=9) == 3, text


def test_current_allowed_cpu_count_reads_the_given_cpu_max_file(*, tmp_path: Path) -> None:
    cpu_max = tmp_path / "cpu.max"
    cpu_max.write_text("300000 100000\n", encoding="utf-8")
    assert current_allowed_cpu_count(cpu_max_path=cpu_max) <= 3


def test_current_allowed_cpu_count_tolerates_a_missing_cpu_max_file(*, tmp_path: Path) -> None:
    assert current_allowed_cpu_count(cpu_max_path=tmp_path / "absent") >= 1
