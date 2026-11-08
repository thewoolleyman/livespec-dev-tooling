"""Command-line surface of the parallel check dispatcher."""

from __future__ import annotations

import argparse

__all__: list[str] = ["parse_args"]


def parse_args() -> argparse.Namespace:
    """Parse `sys.argv` into the dispatcher's `--workers`, `--skip` and target list."""
    parser = argparse.ArgumentParser(
        description="Parallel just-check dispatcher with core-budget cap."
    )
    _ = parser.add_argument(
        "--workers",
        type=int,
        default=None,
        help=(
            "Max concurrent targets, never above the CPUs the process may use. "
            "Default: the CPUs the process may use (cgroup cpu.max quota, else "
            "affinity mask), capped at 8."
        ),
    )
    _ = parser.add_argument("--skip", type=str, default="", help="Space-separated skip list.")
    _ = parser.add_argument("targets", nargs="*", help="Ordered target list.")
    return parser.parse_args()
