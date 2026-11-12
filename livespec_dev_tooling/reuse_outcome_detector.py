"""Evaluate recorded mandatory coverage-reuse outcomes for maintainer notices."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__: list[str] = ["Notice", "evaluate"]


@dataclass(frozen=True, kw_only=True)
class Notice:
    """One notification that the host-side delivery adapter must send."""

    message: str


def evaluate(
    *,
    outcomes: Sequence[dict[str, object]],
    jobs: Sequence[dict[str, object]],
    now: str,
    last_success: str,
    interval_seconds: int,
) -> list[Notice]:
    """Render every recorded mandatory-consumer fallback as a notification."""
    _ = (jobs, now, last_success, interval_seconds)
    return [
        Notice(
            message=(
                "coverage reuse fallback: "
                f"repository={outcome['repository']} run={outcome['run_id']} "
                f"job={outcome['job_id']} outcome={outcome['outcome']}"
            )
        )
        for outcome in outcomes
    ]
