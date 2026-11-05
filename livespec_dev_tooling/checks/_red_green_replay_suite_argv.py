"""Worker-count selection for the suite-green replay command."""

from __future__ import annotations

from collections.abc import Callable, Mapping

__all__: list[str] = ["lane_worker_count", "visible_cpu_count"]

_LANE_ENV: str = "LIVESPEC_CI_LANE"
_PARALLELISM_ENV: str = "LIVESPEC_TEST_PARALLELISM"


def lane_worker_count(*, environ: Mapping[str, str], visible_cpus: int) -> str:
    """Return the consumers' lane-aware suite-green worker count."""
    if environ.get(_LANE_ENV, "local") == "hosted":
        return "auto"
    explicit = environ.get(_PARALLELISM_ENV, "").strip()
    if explicit:
        return explicit
    return str(max(1, visible_cpus // 4))


def visible_cpu_count(*, affinity: Callable[[int], set[int]] | None, cpu_count: int | None) -> int:
    """Return how many CPUs this process may use.

    `affinity` is `os.sched_getaffinity`, which only Linux provides; elsewhere
    (macOS) the count falls back to `os.cpu_count()`, and to 1 when that is
    unknown.
    """
    if affinity is not None:
        return len(affinity(0))
    return cpu_count or 1
