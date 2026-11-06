"""The two record shapes the probe constructs, with the released field names."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

__all__: list[str] = ["StoreConfig", "WorkItem"]


@dataclass(frozen=True, kw_only=True)
class StoreConfig:
    tenant: str
    prefix: str
    server_user: str
    database: str
    bd_path: str
    server_host: str = "127.0.0.1"
    server_port: int = 3307
    socket: str | None = None
    fake: bool = False
    repo_root: Path | None = None
    credential_wrapper: tuple[str, ...] = ()


@dataclass(frozen=True, kw_only=True)
class WorkItem:
    id: str
    type: str
    status: str
    title: str
    description: str
    origin: str
    gap_id: str | None
    rank: str
    assignee: str | None
    depends_on: tuple[Any, ...]
    captured_at: str
    resolution: str | None
    reason: str | None
    audit: Any
    superseded_by: str | None
    labels: list[str] = field(default_factory=list)
