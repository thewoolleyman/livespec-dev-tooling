"""Mirror-paired tests for suite-green worker-count selection."""

from __future__ import annotations

from livespec_dev_tooling.checks._red_green_replay_suite_argv import (
    lane_worker_count,
    visible_cpu_count,
)

__all__: list[str] = []


def test_worker_count_follows_the_local_and_hosted_lane_rules() -> None:
    """Hosted uses auto; local execution stays bounded to the available quota."""
    assert lane_worker_count(environ={"LIVESPEC_CI_LANE": "hosted"}, visible_cpus=32) == "auto"
    assert lane_worker_count(environ={"LIVESPEC_TEST_PARALLELISM": "6"}, visible_cpus=32) == "6"
    assert lane_worker_count(environ={}, visible_cpus=4) == "1"


def test_visible_cpus_use_the_affinity_set_where_the_platform_has_one() -> None:
    """Linux counts the CPUs this process may run on."""
    assert visible_cpu_count(affinity=lambda _pid: {0, 1, 2}, cpu_count=64) == 3


def test_visible_cpus_fall_back_to_the_cpu_count_where_affinity_is_absent() -> None:
    """macOS has no `os.sched_getaffinity`; the suite-green leg must still run there."""
    assert visible_cpu_count(affinity=None, cpu_count=12) == 12
    assert visible_cpu_count(affinity=None, cpu_count=None) == 1
