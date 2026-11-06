"""A file-locked record store with the released client's verbs.

Every verb takes the store's exclusive lock, so two processes that close one
record at once see exactly one close land — `bd close --reason`'s server-side
compare-and-swap, reproduced on a file. The store's path is read from the
clone's `.beads/fake-store-path`.
"""

from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from livespec_orchestrator_beads_fabro.types import StoreConfig

__all__: list[str] = ["FakeBeadsClient", "make_beads_client"]

_CLOSED = "closed"
_TOKEN_KEY = "dispatch_claim_token"


class FakeBeadsClient:
    def __init__(self, *, store: Path) -> None:
        self._store = store

    @contextmanager
    def _locked(self) -> Iterator[dict[str, Any]]:
        lock = self._store.with_suffix(".lock")
        with lock.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            records = (
                json.loads(self._store.read_text(encoding="utf-8")) if self._store.exists() else {}
            )
            yield records
            self._store.write_text(json.dumps(records, indent=1, sort_keys=True), encoding="utf-8")
            fcntl.flock(handle, fcntl.LOCK_UN)

    def show_issue(self, *, issue_id: str) -> dict[str, Any]:
        with self._locked() as records:
            return dict(records[issue_id])

    def create_record(self, *, issue_id: str, **fields: Any) -> str:
        with self._locked() as records:
            records[issue_id] = {
                "id": issue_id,
                "status": "backlog",
                "close_reason": None,
                **fields,
            }
        return issue_id

    def create_no_history_issue(self, *, title: str, description: str) -> str:
        with self._locked() as records:
            issue_id = f"bd-ib-tok-{len(records) + 1:03d}"
            records[issue_id] = {
                "id": issue_id,
                "status": "backlog",
                "close_reason": None,
                "title": title,
                "description": description,
                "labels": ["claim-token"],
                "metadata": {},
            }
        return issue_id

    def close_issue_without_verdict(self, *, issue_id: str, reason: str) -> None:
        with self._locked() as records:
            record = records[issue_id]
            if record["status"] != _CLOSED:
                record.update(status=_CLOSED, close_reason=reason)

    def close_issue(self, *, issue_id: str, reason: str | None) -> None:
        self.close_issue_without_verdict(issue_id=issue_id, reason=reason or "")

    def update_issue(
        self,
        *,
        issue_id: str,
        status: str | None = None,
        assignee: str | None = None,
        clear_assignee: bool = False,
        add_labels: list[str] | None = None,
        remove_labels: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        names_claim_token: bool = False,
    ) -> None:
        with self._locked() as records:
            record = records[issue_id]
            if status is not None:
                record["status"] = status
            if assignee is not None:
                record["assignee"] = assignee
            if clear_assignee:
                record["assignee"] = None
            labels = [x for x in record.get("labels", []) if x not in (remove_labels or [])]
            record["labels"] = labels + [x for x in (add_labels or []) if x not in labels]
            if metadata is not None:
                payload = (
                    dict(metadata)
                    if names_claim_token
                    else {k: v for k, v in metadata.items() if k != _TOKEN_KEY}
                )
                record["metadata"] = {**record.get("metadata", {}), **payload}


def make_beads_client(*, config: StoreConfig) -> FakeBeadsClient:
    assert config.repo_root is not None
    pointer = config.repo_root / ".beads" / "fake-store-path"
    return FakeBeadsClient(store=Path(pointer.read_text(encoding="utf-8").strip()))
