"""Public import surface for the on-demand fleet test baseline collector."""

from __future__ import annotations

import argparse
import json
import sys
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


def main(*, argv: list[str] | None = None) -> int:
    """Emit one baseline JSON document for the supplied sibling clone paths."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("paths", metavar="REPOSITORY", nargs="+", type=Path)
    parsed = parser.parse_args(argv)
    _ = sys.stdout.write(json.dumps(measure_repositories(paths=tuple(parsed.paths))) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
