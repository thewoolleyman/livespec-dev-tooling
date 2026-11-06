"""The creation seam: a non-closed item names its first token in the creating write."""

from __future__ import annotations

from typing import Any

from livespec_orchestrator_beads_fabro._store_claim_tokens import (
    CLAIM_TOKEN_METADATA_KEY,
    create_claim_token,
)

__all__: list[str] = ["create_work_item"]


def create_work_item(*, client: Any, item: Any, claim_tokens: bool = False) -> None:
    metadata: dict[str, Any] = {"rank": item.rank}
    if claim_tokens:
        metadata[CLAIM_TOKEN_METADATA_KEY] = create_claim_token(client=client)
    client.create_record(
        issue_id=item.id,
        title=item.title,
        description=item.description,
        assignee=item.assignee,
        labels=[f"origin:{item.origin}"],
        metadata=metadata,
    )
    client.update_issue(issue_id=item.id, status=item.status)
