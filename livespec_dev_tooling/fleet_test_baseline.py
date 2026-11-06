"""Public import surface for the on-demand fleet test baseline collector."""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.fleet._test_baseline import (
    Runner,
    run_command,
)
from livespec_dev_tooling.fleet._test_baseline import (
    measure_repositories as _measure_repositories,
)

__all__: list[str] = ["measure_repositories"]

_run: Runner = run_command


def measure_repositories(*, paths: tuple[Path, ...]) -> dict[str, object]:
    """Measure repository baselines through this module's injectable runner."""
    return _measure_repositories(paths=paths, runner=_run)
