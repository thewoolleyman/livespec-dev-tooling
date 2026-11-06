"""The claim stamp and claim row, with the released names and metadata key."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__: list[str] = ["ClaimRow", "ClaimStamp", "claim_row_from_record", "claim_stamp_metadata"]

CLAIM_STAMP_METADATA_KEY = "dispatch_claim"


@dataclass(frozen=True, kw_only=True)
class ClaimStamp:
    dispatch_id: str | None
    dispatching_host: str | None
    run_id: str | None
    factory_name: str | None
    factory_server: str | None


@dataclass(frozen=True, kw_only=True)
class ClaimRow:
    status: str | None
    assignee: str | None
    stamp: ClaimStamp | None


def claim_stamp_metadata(*, stamp: ClaimStamp) -> dict[str, Any]:
    return {
        CLAIM_STAMP_METADATA_KEY: {
            "dispatch_id": stamp.dispatch_id,
            "dispatching_host": stamp.dispatching_host,
            "run_id": stamp.run_id,
            "factory": {"name": stamp.factory_name, "server": stamp.factory_server},
        }
    }


def claim_row_from_record(*, record: dict[str, Any]) -> ClaimRow:
    raw = (record.get("metadata") or {}).get(CLAIM_STAMP_METADATA_KEY)
    stamp = None
    if isinstance(raw, dict):
        factory = raw.get("factory") or {}
        stamp = ClaimStamp(
            dispatch_id=raw.get("dispatch_id"),
            dispatching_host=raw.get("dispatching_host"),
            run_id=raw.get("run_id"),
            factory_name=factory.get("name"),
            factory_server=factory.get("server"),
        )
    return ClaimRow(status=record.get("status"), assignee=record.get("assignee"), stamp=stamp)
