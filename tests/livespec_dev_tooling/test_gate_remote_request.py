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
