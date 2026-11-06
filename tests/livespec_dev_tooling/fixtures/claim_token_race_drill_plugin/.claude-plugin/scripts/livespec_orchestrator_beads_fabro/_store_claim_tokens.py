"""The released `change_claim` protocol, reduced to the steps the drill exercises.

Read the item and its token, ask the caller's decision of the fresh record,
create a successor, close the contested token under the store's lock, read the
reason back, and either name the successor in one item write or discard it and
stand down. `DRILL_FAKE_HANG_INTENT` makes a writer of that intent hang before
its close, so the play's cleanup can be exercised against a writer that never
finishes.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from typing import Any

__all__: list[str] = [
    "CLAIM_TOKEN_METADATA_KEY",
    "ClaimChangeResult",
    "change_claim",
    "create_claim_token",
]

CLAIM_TOKEN_METADATA_KEY = "dispatch_claim_token"
_HANG_ENV = "DRILL_FAKE_HANG_INTENT"


@dataclass(frozen=True, kw_only=True)
class ClaimChangeResult:
    outcome: str
    successor_token_id: str | None = None


def create_claim_token(*, client: Any) -> str:
    return client.create_no_history_issue(
        title="livespec dispatch claim token",
        description="Single-use dispatch-claim token; never a work item.",
    )


def change_claim(
    *,
    client: Any,
    work_item_id: str,
    writer: str,
    intent: str,
    claim_tokens: bool,
    status: str | None = None,
    assignee: str | None = None,
    clear_assignee: bool = False,
    add_labels: list[str] | None = None,
    remove_labels: list[str] | None = None,
    metadata: dict[str, Any] | None = None,
    clock: Callable[[], float] = time.monotonic,
    transition_observations: MutableMapping[Any, float] | None = None,
    still_as_decided: Callable[[dict[str, Any]], bool] | None = None,
) -> ClaimChangeResult:
    _ = (claim_tokens, add_labels, remove_labels, clock, transition_observations)
    record = client.show_issue(issue_id=work_item_id)
    token_id = (record.get("metadata") or {}).get(CLAIM_TOKEN_METADATA_KEY)
    if token_id is None:
        return ClaimChangeResult(outcome="claim-token-missing")
    if client.show_issue(issue_id=token_id)["status"] == "closed":
        return ClaimChangeResult(outcome="claim-transition-pending")
    if still_as_decided is not None and not still_as_decided(record):
        return ClaimChangeResult(outcome="claim-changed")
    successor = create_claim_token(client=client)
    reason = json.dumps(
        {
            "kind": "claim-token-transition",
            "writer": writer,
            "intent": intent,
            "successor": successor,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    while os.environ.get(_HANG_ENV) == intent:
        time.sleep(0.2)
    client.close_issue_without_verdict(issue_id=token_id, reason=reason)
    if client.show_issue(issue_id=token_id).get("close_reason") != reason:
        client.close_issue_without_verdict(
            issue_id=successor,
            reason=json.dumps({"kind": "claim-token-discard", "writer": writer}, sort_keys=True),
        )
        return ClaimChangeResult(outcome="claim-changed")
    merged = {
        **(record.get("metadata") or {}),
        **(metadata or {}),
        CLAIM_TOKEN_METADATA_KEY: successor,
    }
    client.update_issue(
        issue_id=work_item_id,
        status=status,
        assignee=assignee,
        clear_assignee=clear_assignee,
        metadata=merged,
        names_claim_token=True,
    )
    return ClaimChangeResult(outcome="applied", successor_token_id=successor)
