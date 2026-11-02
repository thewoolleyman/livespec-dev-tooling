"""Mirror-paired tests for suite-green worker-count selection."""

from __future__ import annotations

from livespec_dev_tooling.checks._red_green_replay_suite_argv import lane_worker_count

__all__: list[str] = []


def test_worker_count_follows_the_local_and_hosted_lane_rules() -> None:
    """Hosted uses auto; local execution stays bounded to the available quota."""
    assert lane_worker_count(environ={"LIVESPEC_CI_LANE": "hosted"}, visible_cpus=32) == "auto"
    assert lane_worker_count(environ={"LIVESPEC_TEST_PARALLELISM": "6"}, visible_cpus=32) == "6"
    assert lane_worker_count(environ={}, visible_cpus=4) == "1"
