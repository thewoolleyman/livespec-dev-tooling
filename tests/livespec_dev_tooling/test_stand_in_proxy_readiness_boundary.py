"""Regression coverage for the stand-in proxy readiness signal."""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_EXIT_TESTS = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "gates" / "render-gate-job-exit-tests.sh"
)


def test_stand_in_proxy_readiness_waits_for_a_written_signal() -> None:
    """A slow stand-in passes when its child writes its ready signal.

    The readiness contract is the file written after the child has bound its
    HTTP server, not a deadline that can expire while a loaded runner delays
    the child.  Setting the old budget to zero keeps this regression red until
    the wall-clock helper is replaced.
    """
    script = r"""
set -u
helper="$(sed -n '/^wait_for_stand_in_proxy() {/,/^}/p' "$1")"
eval "${helper}"
failures=0
fail() { printf 'FAIL  %s\n' "$1"; failures=$((failures + 1)); }
ready="$(mktemp)"
rm -f "${ready}"
trap 'rm -f "${ready}"' EXIT
(sleep 0.1; printf 'ready\n' > "${ready}") &
child_pid=$!
STAND_IN_PROXY_READY_DEADLINE_SECONDS=0 wait_for_stand_in_proxy "${child_pid}" "${ready}"
"""
    completed = subprocess.run(
        ["bash", "-c", script, "--", str(_EXIT_TESTS)],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=5,
    )

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "FAIL" not in completed.stdout
