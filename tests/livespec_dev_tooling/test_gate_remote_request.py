"""The delegated gate request's stable input defaults."""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.gate_remote_request import GATE_NAMESPACE, GateRunRequest

__all__: list[str] = []


def test_a_request_carries_the_gates_namespace_and_bounds_its_status_polls() -> None:
    """The bound derives from request policy rather than a separate time seam."""
    request = GateRunRequest(
        repo_root=Path("/repo"),
        mirror_url="ssh://mirror/repo.git",
        manifest="apiVersion: batch/v1\nkind: Job\n",
        gate_ref="refs/gates/tree-run",
        poll_interval_seconds=10.0,
        poll_timeout_seconds=25.0,
    )

    assert request.namespace == GATE_NAMESPACE == "gates"
    assert request.poll_budget() == 2


def test_a_request_bounds_the_admission_wait_at_1800_seconds_and_the_run_at_3600() -> None:
    """The admission bound and the post-admission poll budget carry their ratified defaults."""
    request = GateRunRequest(
        repo_root=Path("/repo"),
        mirror_url="ssh://mirror/repo.git",
        manifest="apiVersion: batch/v1\nkind: Job\n",
        gate_ref="refs/gates/tree-run",
    )

    assert request.admission_timeout_seconds == 1800.0
    assert request.poll_timeout_seconds == 3600.0
    assert request.admission_poll_budget() == 180
    assert request.poll_budget() == 360
