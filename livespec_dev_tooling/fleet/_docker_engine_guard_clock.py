"""The clock, the boot identity and the one bounded wait the guard makes.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Deadline" (this repository),
which records a run's deadline as a boot id AND a CLOCK_MONOTONIC
instant. Governing design: `docs/docker-engine-guard-design.md`.

THE WALL CLOCK IS NOT EITHER HALF, and that is the whole reason this
module exists rather than a `time.time()` beside each caller. The wall
clock steps under NTP and an administrator can set it, so a deadline
recorded against it is a deadline a run could buy itself more of; and a
monotonic instant alone means nothing across a reboot, because the
counter restarts. The two together — this boot's id and this boot's
monotonic second — are the only pair that says "the dead-man fires
then" and keeps saying it.

Stdlib only, Python 3.10 syntax, for the reason
`_docker_engine_guard_model.py` records.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Final

from livespec_dev_tooling.fleet._docker_engine_guard_witness import PROC_ROOT

__all__: list[str] = [
    "BOOT_ID_RELATIVE_PATH",
    "monotonic_seconds",
    "read_boot_id",
    "wait_seconds",
]

# Where the kernel publishes this boot's id, relative to `/proc`. Held
# relative rather than absolute so the whole read is drivable against a
# RECORDED tree through the host's own `proc_root`, exactly as the k3s
# witness's reads are.
BOOT_ID_RELATIVE_PATH: Final[Path] = Path("sys/kernel/random/boot_id")


def monotonic_seconds() -> float:
    """CLOCK_MONOTONIC seconds — the clock a deadline is recorded against."""
    return time.monotonic()


def read_boot_id(*, proc_root: Path = PROC_ROOT) -> str:
    """This boot's id, without the newline the kernel ends it with.

    The strip is load-bearing rather than tidy: a recorded deadline is
    compared by STRING equality against this value, so an unstripped id
    matches nothing — every armed run would read as belonging to another
    boot, and so as already out of time, from the instant it was armed.
    """
    return (proc_root / BOOT_ID_RELATIVE_PATH).read_text(encoding="utf-8").strip()


def wait_seconds(*, seconds: float) -> None:
    """The bounded wait the lock acquisition polls on, and nothing else."""
    time.sleep(seconds)
