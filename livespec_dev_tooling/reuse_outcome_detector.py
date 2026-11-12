"""Decide which CI coverage-reuse outcomes require maintainer attention."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__: list[str] = ["Notification", "reuse_outcome_notification"]

_REUSED_OUTCOME = "reused"


@dataclass(frozen=True, kw_only=True)
class Notification:
    """One maintainer-facing event the host delivery adapter must publish."""

    message: str
    occurred_at: datetime


def reuse_outcome_notification(
    *, repository: str, run_id: str, job_id: str, outcome: str, completed_at: datetime
) -> Notification | None:
    """Return the required fallback notification, or nothing for a successful reuse.

    The caller has already read this one structured outcome from the CI run's
    telemetry. Any value other than ``reused`` remains visible so a producer
    schema regression cannot be silently classified as a successful reuse.
    """
    if outcome == _REUSED_OUTCOME:
        return None
    return Notification(
        message=(
            f"coverage reuse fallback repository={repository} run={run_id} "
            f"job={job_id} outcome={outcome}"
        ),
        occurred_at=completed_at,
    )
