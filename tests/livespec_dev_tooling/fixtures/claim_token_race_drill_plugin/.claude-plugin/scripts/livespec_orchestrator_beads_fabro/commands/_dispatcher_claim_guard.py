"""The `same_claim_row` decision and the process-wide transition sightings."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from livespec_orchestrator_beads_fabro._store_dispatch_claim import ClaimRow, claim_row_from_record

__all__: list[str] = ["TRANSITION_OBSERVATIONS", "same_claim_row"]

TRANSITION_OBSERVATIONS: dict[tuple[str, str, str], float] = {}


def same_claim_row(*, row: ClaimRow) -> Callable[[dict[str, Any]], bool]:
    return lambda record: row.status == "active" and claim_row_from_record(record=record) == row
