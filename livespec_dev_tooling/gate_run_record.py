"""Durable fields a detached gate client writes for its shell runner."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

__all__: list[str] = ["job_name_recorder"]


def job_name_recorder(*, run_dir: Path) -> Callable[[str], None]:
    """Return the atomic Job-name writer shared by direct and hook-run clients."""

    def record(*job_names: str) -> None:
        (job_name,) = job_names
        partial = run_dir / "job_name.partial"
        _ = partial.write_text(f"{job_name}\n", encoding="utf-8")
        _ = partial.replace(run_dir / "job_name")

    return record
