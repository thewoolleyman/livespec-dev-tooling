"""Regression coverage for the xdist-controller watchdog in the coverage producer.

The producer owns the pytest process and therefore has the only reliable view
of the controller after xdist workers have finished.  This test drives a copy
of that shell script with a deliberately shortened timeout: fake ``uv`` execs
a Python controller which forks one worker and then sleeps without children or
CPU progress.  The shipped script keeps the ten-minute bound; the copy makes
the behavioral proof practical without adding a production timeout override.

The watchdog arms only after it has SEEN a worker (``pgrep -P`` matching a
live child of the controller).  A fake worker that simply lives for a fixed
time races the watchdog's first poll: under load the poll lands after the
worker has gone, the watchdog never arms, and the controller sleeps its full
600 s (livespec-dev-tooling-4ulplz, push gate 20261111T132921Z-2043931).  So
the worker here exits only once the watchdog has observed it.  A ``pgrep``
shim placed first on the producer's PATH runs the real ``pgrep``, and when a
``-P`` query matches it writes a marker file that the worker waits for.  The
shim also holds back its FIRST answer for longer than the old fixture's worker
lived, so every run exercises the late-first-poll case rather than only the
runs that happen to be slow.  The subprocess timeout is a hang guard only.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_PRODUCER = _REPO_ROOT / "scripts" / "just" / "check-per-file-coverage.sh"

# A hang guard, not a performance bound: a correct run finishes in about two
# seconds, and nothing in the verdict depends on finishing inside this limit.
_HANG_GUARD_SECONDS = 180

# Longer than the 0.05 s the old fixture's worker lived, so the watchdog's
# first poll always lands after a fixed-lifetime worker would have exited.
_FIRST_POLL_DELAY_SECONDS = 0.5

# How long the fake worker waits for the watchdog before giving up, so a
# broken shim fails this test by its assertions rather than by the hang guard.
_WORKER_WAIT_SECONDS = 120


def _write_fake_controller(*, path: Path) -> None:
    path.write_text(
        f"""import os
import time

marker = os.environ["WATCHDOG_SAW_WORKER"]
child = os.fork()
if child == 0:
    deadline = time.monotonic() + {_WORKER_WAIT_SECONDS}
    while not os.path.exists(marker) and time.monotonic() < deadline:
        time.sleep(0.01)
    os._exit(0)
os.waitpid(child, 0)
time.sleep(600)
""",
        encoding="utf-8",
    )


def _write_fake_uv(*, path: Path) -> None:
    path.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" == "run pytest" ]]; then
    exec "$REAL_PYTHON" "$FAKE_CONTROLLER"
fi
exit 99
""",
        encoding="utf-8",
    )
    path.chmod(0o755)


def _write_pgrep_shim(*, path: Path) -> None:
    path.write_text(
        f"""#!/usr/bin/env bash
if [[ ! -e "$PGREP_SHIM_FIRST_CALL" ]]; then
    : > "$PGREP_SHIM_FIRST_CALL"
    sleep {_FIRST_POLL_DELAY_SECONDS}
fi
"$REAL_PGREP" "$@"
status=$?
if [[ "$status" -eq 0 && "${{1:-}}" == "-P" ]]; then
    : > "$WATCHDOG_SAW_WORKER"
fi
exit "$status"
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
    real_pgrep = shutil.which("pgrep")
    assert real_pgrep is not None, "the producer's watchdog needs pgrep on PATH"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_controller = tmp_path / "fake_controller.py"
    _write_fake_controller(path=fake_controller)
    _write_fake_uv(path=bin_dir / "uv")
    _write_pgrep_shim(path=bin_dir / "pgrep")
    saw_worker = tmp_path / "watchdog-saw-worker"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "REAL_PYTHON": sys.executable,
        "REAL_PGREP": real_pgrep,
        "FAKE_CONTROLLER": str(fake_controller),
        "WATCHDOG_SAW_WORKER": str(saw_worker),
        "PGREP_SHIM_FIRST_CALL": str(tmp_path / "pgrep-shim-first-call"),
        "test_nprocs": "1",
    }

    result = subprocess.run(
        ["bash", str(producer)],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        env=env,
        text=True,
        timeout=_HANG_GUARD_SECONDS,
    )

    combined = result.stdout + result.stderr
    assert saw_worker.exists(), combined
    assert result.returncode != 0, combined
    assert "pytest controller" in combined
    assert "idle for" in combined
    assert "after xdist workers exited" in combined
