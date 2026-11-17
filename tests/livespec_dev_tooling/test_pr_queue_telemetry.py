"""The pr-throughput event carries merge-queue fields derived from timeline items."""

from __future__ import annotations

from livespec_dev_tooling.pr_queue_telemetry import queue_attributes, queue_batch_sizes

__all__: list[str] = []


def test_real_pull_request_sample_yields_queue_fields() -> None:
    nodes = [
        {"__typename": "AutoMergeEnabledEvent", "createdAt": "2026-11-16T19:04:23Z"},
        {
            "__typename": "AddedToMergeQueueEvent",
            "createdAt": "2026-11-16T19:28:42Z",
            "enqueuer": {"login": "livespec-ai-factory-bot[bot]"},
        },
        {"__typename": "MergedEvent", "createdAt": "2026-11-16T20:27:38Z"},
        {
            "__typename": "RemovedFromMergeQueueEvent",
            "createdAt": "2026-11-16T20:27:38Z",
            "reason": "merged",
        },
    ]
    assert queue_attributes(nodes=nodes) == {
        "pr.queue_enqueued_at": "2026-11-16T19:28:42Z",
        "pr.queue_wait_minutes": 58.9,
        "pr.queue_dequeue_reason": "merged",
    }


def test_pull_request_that_never_queued_yields_nothing() -> None:
    nodes = [{"__typename": "MergedEvent", "createdAt": "2026-11-16T20:27:38Z"}]
    assert queue_attributes(nodes=nodes) == {}
    assert queue_attributes(nodes=[]) == {}


def test_last_add_and_the_removal_after_it_are_used() -> None:
    nodes = [
        {"__typename": "AddedToMergeQueueEvent", "createdAt": "2026-11-16T10:00:00Z"},
        {
            "__typename": "RemovedFromMergeQueueEvent",
            "createdAt": "2026-11-16T10:30:00Z",
            "reason": "ci_failure",
        },
        {"__typename": "AddedToMergeQueueEvent", "createdAt": "2026-11-16T11:00:00Z"},
        {"__typename": "MergedEvent", "createdAt": "2026-11-16T11:12:00Z"},
        {
            "__typename": "RemovedFromMergeQueueEvent",
            "createdAt": "2026-11-16T11:12:00Z",
            "reason": "merged",
        },
    ]
    assert queue_attributes(nodes=nodes) == {
        "pr.queue_enqueued_at": "2026-11-16T11:00:00Z",
        "pr.queue_wait_minutes": 12.0,
        "pr.queue_dequeue_reason": "merged",
    }


def test_batch_size_counts_prs_sharing_a_removal_instant() -> None:
    removals = [
        (1, "2026-11-16T20:27:38Z"),
        (2, "2026-11-16T20:27:38Z"),
        (3, "2026-11-16T21:00:00Z"),
    ]
    assert queue_batch_sizes(removals=removals) == {1: 2, 2: 2, 3: 1}
    assert queue_batch_sizes(removals=[(9, "2026-11-16T21:00:00Z")]) == {9: 1}
