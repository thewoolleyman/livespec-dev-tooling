"""The single reading of how many CPUs this process may use."""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

__all__: list[str] = ["allowed_cpu_count", "current_allowed_cpu_count"]

_CGROUP_CPU_MAX = Path("/sys/fs/cgroup/cpu.max")
_CPU_MAX_FIELDS = 2


def _quota_cpus(*, cpu_max: str | None) -> int | None:
    """Return the cgroup v2 `cpu.max` quota as whole CPUs, or None when unlimited or unreadable."""
    fields = (cpu_max or "").split()
    if len(fields) != _CPU_MAX_FIELDS:
        return None
    try:
        quota, period = int(fields[0]), int(fields[1])
    except ValueError:
        return None
    if quota <= 0 or period <= 0:
        return None
    return max(1, quota // period)


def allowed_cpu_count(
    *, cpu_max: str | None, affinity: Callable[[int], set[int]] | None, cpu_count: int | None
) -> int:
    """Return how many CPUs this process may use.

    The bound is the cgroup v2 `cpu.max` quota over its period (text in
    `cpu_max`, with `max` meaning unlimited) and the affinity mask
    (`os.sched_getaffinity`, Linux only), whichever is smaller. With neither,
    it is `os.cpu_count()`, and 1 when that is unknown.
    """
    bounds: list[int] = []
    quota = _quota_cpus(cpu_max=cpu_max)
    if quota is not None:
        bounds.append(quota)
    if affinity is not None:
        bounds.append(len(affinity(0)))
    if bounds:
        return max(1, min(bounds))
    return cpu_count or 1


def current_allowed_cpu_count(*, cpu_max_path: Path = _CGROUP_CPU_MAX) -> int:
    """Return `allowed_cpu_count` for this process, reading `cpu_max_path` when present."""
    try:
        cpu_max = cpu_max_path.read_text(encoding="utf-8")
    except OSError:
        cpu_max = None
    return allowed_cpu_count(
        cpu_max=cpu_max,
        affinity=getattr(os, "sched_getaffinity", None),
        cpu_count=os.cpu_count(),
    )
