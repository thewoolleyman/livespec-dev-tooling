"""Regression coverage for shell assertions rewritten by the pipefail sweep."""

from __future__ import annotations

import subprocess
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_NODE_STATUS_EXIT_TEST = _REPO_ROOT / (
    "ci-runner/k3s/secret-reinjection/seed-node-status-kubeconfig-exit-tests.sh"
)


def test_node_status_exit_test_retains_its_original_verdict() -> None:
    """Replacing `grep -q` must not relax the exit test's assertions."""
    completed = subprocess.run(
        [_NODE_STATUS_EXIT_TEST],
        cwd=_REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
