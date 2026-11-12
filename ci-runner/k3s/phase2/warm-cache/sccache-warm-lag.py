#!/usr/bin/env python3
"""Pure state transitions for one compilation-cache warm set.

The populator feeds this helper the cache marker it read and the outcome of its
writer decision.  Keeping the transition here makes the restart-safe manifest
state independently testable without making a second cache-record writer.
"""

from __future__ import annotations

from typing import TypedDict


class WarmSet(TypedDict):
    """The durable per-repository compilation-cache warm-set state."""

    consecutive_skipped_busy: int
    last_built_commit: str | None
    last_built_toolchain: str | None
    lag_started_at_epoch: int | None


def _previous(*, state: dict[str, object] | None) -> WarmSet:
    """Normalize an absent or older manifest's state to the durable schema."""
    state = state or {}
    return {
        "consecutive_skipped_busy": int(state.get("consecutive_skipped_busy") or 0),
        "last_built_commit": _text(value=state.get("last_built_commit")),
        "last_built_toolchain": _text(value=state.get("last_built_toolchain")),
        "lag_started_at_epoch": _epoch(value=state.get("lag_started_at_epoch")),
    }


def _text(*, value: object) -> str | None:
    """Keep only a non-empty marker field."""
    return value if isinstance(value, str) and value else None


def _epoch(*, value: object) -> int | None:
    """Keep only a non-negative lag epoch."""
    return value if isinstance(value, int) and value >= 0 else None


def transition(
    *,
    previous: dict[str, object] | None,
    outcome: str,
    run_started_at_epoch: int,
    **record: str | None,
) -> WarmSet:
    """Return one repository's next manifest state from one populate outcome.

    `unvisited` means the run stopped before a cache-record read; `unreadable`
    means the read was attempted but unavailable.  Every other non-success,
    non-busy outcome deliberately ends only the busy streak.
    """
    old = _previous(state=previous)
    cache_record_commit = record["cache_record_commit"]
    cache_record_toolchain = record["cache_record_toolchain"]
    if outcome == "unvisited":
        return old
    if outcome == "unreadable":
        return {**old, "consecutive_skipped_busy": 0}
    record = {
        "last_built_commit": cache_record_commit,
        "last_built_toolchain": cache_record_toolchain,
    }
    if outcome in {"built", "current"}:
        return {
            "consecutive_skipped_busy": 0,
            **record,
            "lag_started_at_epoch": None,
        }
    if outcome == "busy":
        return {
            "consecutive_skipped_busy": old["consecutive_skipped_busy"] + 1,
            **record,
            "lag_started_at_epoch": old["lag_started_at_epoch"] or run_started_at_epoch,
        }
    return {**old, **record, "consecutive_skipped_busy": 0}
