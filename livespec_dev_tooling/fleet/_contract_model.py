"""Shared fleet obligation row model and vantage constants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from livespec_dev_tooling.fleet._context import FleetContext, FleetMember, RowOutcome

__all__: list[str] = [
    "ADMIN_VANTAGE",
    "CENTRAL_APP_VANTAGE",
    "CENTRAL_VANTAGE",
    "ObligationRow",
    "RowFn",
]


CENTRAL_VANTAGE = "central"
CENTRAL_APP_VANTAGE = "central-app"
ADMIN_VANTAGE = "admin"


class RowFn(Protocol):
    """One obligation-row operation (assert or reconcile) over a member."""

    def __call__(self, *, ctx: FleetContext, member: FleetMember) -> RowOutcome: ...


@dataclass(frozen=True, kw_only=True)
class ObligationRow:
    """One per-class obligation: assert logic plus its reconcile reference."""

    row_id: str
    obligation_type: str
    applies_to: frozenset[str]
    assert_member: RowFn
    reconcile: RowFn | None = None
    manual_hint: str = ""
    vantage: str = CENTRAL_VANTAGE
