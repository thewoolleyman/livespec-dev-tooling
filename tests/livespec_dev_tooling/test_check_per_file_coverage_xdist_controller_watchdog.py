"""Regression coverage for the xdist-controller watchdog in the coverage producer.

The producer owns the pytest process and therefore has the only reliable view
of the controller after xdist workers have finished.  This test drives a copy
of that shell script with a deliberately shortened timeout: fake ``uv`` execs
a Python controller which forks one short-lived worker and then sleeps without
children or CPU progress.  The shipped script keeps the ten-minute bound; the
copy makes the behavioral proof practical without adding a production timeout
override.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRODUCER = _REPO_ROOT / "scripts" / "just" / "check-per-file-coverage.sh"


def _write_fake_uv(*, path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" == "run pytest" ]]; then
    exec "$REAL_PYTHON" -c 'import os; import time; child = os.fork(); child == 0 and (time.sleep(0.05) or os._exit(0)); os.waitpid(child, 0); time.sleep(600)'
fi
exit 99
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def test_coverage_producer_fails_an_idle_xdist_controller_after_workers_exit(
    *, tmp_path: Path
) -> None:
    """The controller gets a named non-zero verdict instead of waiting forever.

    The source still declares the required ten-minute timeout.  A copied script
    uses a one-second limit and a fast poll only to make this regression test
    complete promptly; production has no environment knob that could shorten
    or disable its watchdog.
    """
    producer = tmp_path / "check-per-file-coverage.sh"
    producer_text = _PRODUCER.read_text(encoding="utf-8")
    assert "xdist_controller_idle_limit_seconds=600" in producer_text
    assert "xdist_controller_watchdog_poll_seconds=5" in producer_text
    producer.write_text(
        producer_text.replace(
            "xdist_controller_idle_limit_seconds=600",
            "xdist_controller_idle_limit_seconds=1",
        ).replace(
            "xdist_controller_watchdog_poll_seconds=5",
            "xdist_controller_watchdog_poll_seconds=0.05",
        ),
        encoding="utf-8",
    )
    producer.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_uv(path=bin_dir / "uv")
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "REAL_PYTHON": sys.executable,
        "test_nprocs": "1",
    }

    result = subprocess.run(
        ["bash", str(producer)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=15,
    )

    combined = result.stdout + result.stderr
    assert result.returncode != 0, combined
    assert "pytest controller" in combined
    assert "idle for" in combined
    assert "after xdist workers exited" in combined
