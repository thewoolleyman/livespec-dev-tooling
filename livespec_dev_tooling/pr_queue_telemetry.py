"""Derive the merge-queue fields of a pr-throughput event.

Pure functions over the GitHub GraphQL ``timelineItems`` nodes of a merged pull
request (``AddedToMergeQueueEvent``, ``RemovedFromMergeQueueEvent``,
``MergedEvent``). A pull request that never entered the queue yields no
attributes at all, never zeros.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Final

__all__: list[str] = ["queue_attributes", "queue_batch_sizes"]

_ADDED: Final = "AddedToMergeQueueEvent"
_REMOVED: Final = "RemovedFromMergeQueueEvent"
_MERGED: Final = "MergedEvent"
_SECONDS_PER_MINUTE: Final = 60


def _instant(*, value: object) -> datetime:
    """Parse a GitHub ISO-8601 ``Z`` timestamp."""
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _removal_fields(*, enqueued: datetime, removed: Mapping[str, object]) -> dict[str, object]:
    """Return the wait and reason fields for the removal that ended a queue stay."""
    seconds = (_instant(value=removed["createdAt"]) - enqueued).total_seconds()
    return {
        "pr.queue_wait_minutes": round(seconds / _SECONDS_PER_MINUTE, 1),
        "pr.queue_dequeue_reason": removed.get("reason"),
    }


def queue_attributes(*, nodes: Sequence[Mapping[str, object]]) -> dict[str, object]:
    """Return the ``pr.queue_*`` attributes for one pull request's timeline nodes."""
    merged = [_instant(value=n["createdAt"]) for n in nodes if n.get("__typename") == _MERGED]
    cutoff = max(merged) if merged else None
    adds = [
        n
        for n in nodes
        if n.get("__typename") == _ADDED
        and (cutoff is None or _instant(value=n["createdAt"]) <= cutoff)
    ]
    if not adds:
        return {}
    last = max(adds, key=lambda n: _instant(value=n["createdAt"]))
    enqueued = _instant(value=last["createdAt"])
    removals = sorted(
        (
            n
            for n in nodes
            if n.get("__typename") == _REMOVED and _instant(value=n["createdAt"]) >= enqueued
        ),
        key=lambda n: _instant(value=n["createdAt"]),
    )
    removal_fields = {
        key: value
        for removed in removals[:1]
        for key, value in _removal_fields(enqueued=enqueued, removed=removed).items()
    }
    return {"pr.queue_enqueued_at": last["createdAt"], **removal_fields}


def queue_batch_sizes(*, removals: Sequence[tuple[int, str]]) -> dict[int, int]:
    """Return ``pr.queue_batch_size`` per PR: how many share its removal instant."""
    per_instant = Counter(removed_at for _, removed_at in removals)
    return {number: per_instant[removed_at] for number, removed_at in removals}
