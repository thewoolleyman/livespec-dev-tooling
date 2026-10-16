"""The clock, the boot identity and the bounded wait the guard measures time with.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Deadline". Governing design:
`docs/docker-engine-guard-design.md` I2, whose "deadline passed" is a
differing boot id OR a passed monotonic instant.

THE THREE BELONG TOGETHER because a deadline is made of the first two
and waited out with the third, and each is worthless alone. A monotonic
instant does not survive a reboot, so the boot it was taken on is
carried with it; the boot id says nothing about elapsed time, so the
instant is carried with it; and the lock's bounded wait is the one place
the guard spends time deliberately rather than measuring it.

NOT ONE OF THEM IS AN EXTERNAL COMMAND, which is why they do not run
through the guard's command runner: the clock is a syscall and the boot
id is a kernel file, read through the same injected `/proc` root the k3s
witness and the canary's cgroup are read through.

Stdlib only, Python 3.10 syntax, for the reason
`_docker_engine_guard_model.py` records.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Final

from livespec_dev_tooling.fleet._docker_engine_guard_witness import PROC_ROOT

__all__: list[str] = [
    "BOOT_ID_PATH",
    "monotonic_seconds",
    "pause",
    "read_boot_id",
]

# Where the kernel publishes this boot's identity, relative to `/proc`.
BOOT_ID_PATH: Final[str] = "sys/kernel/random/boot_id"


def monotonic_seconds() -> float:
    """CLOCK_MONOTONIC seconds, the clock every deadline is recorded against.

    The clock is NAMED rather than left to `time.monotonic()`, because
    which clock this is decides what a recorded deadline means. The wall
    clock is unusable outright: an NTP step would move a deadline under
    a run already in flight, in either direction. CLOCK_MONOTONIC runs
    from this boot and only this boot, which is exactly the scope the
    boot id beside it declares.
    """
    return time.clock_gettime(time.CLOCK_MONOTONIC)


def read_boot_id(*, proc_root: Path = PROC_ROOT) -> str:
    """This boot's id, with the newline the kernel writes after it dropped.

    The strip is load-bearing rather than tidy: a recorded deadline is
    read back and its boot id compared for EQUALITY with this value, and
    one side carrying a trailing newline would make every deadline read
    as taken on a different boot — which the dispatch table treats as
    passed, so every operation that checks a deadline would refuse.
    """
    return (proc_root / BOOT_ID_PATH).read_text(encoding="utf-8").strip()


def pause(*, seconds: float) -> None:
    """Wait `seconds` out. The bounded poll the lock acquisition spends."""
    time.sleep(seconds)
