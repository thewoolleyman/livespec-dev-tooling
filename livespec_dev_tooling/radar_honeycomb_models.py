"""Committed data contract for the scheduler's deterministic Honeycomb reads."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, TypeAlias

__all__: list[str] = [
    "MAX_QUERIES_PER_TICK",
    "TICK_SPECS",
    "ColumnType",
    "QuerySpec",
]

ColumnType: TypeAlias = type[str] | type[float] | type[int] | type[bool]


@dataclass(frozen=True, kw_only=True)
class QuerySpec:
    """One versioned Honeycomb query, including its required result shape."""

    name: str
    dataset: str
    calculations: tuple[Mapping[str, str], ...]
    filters: tuple[Mapping[str, str], ...]
    breakdowns: tuple[str, ...]
    window_seconds: int
    expected_columns: Mapping[str, ColumnType]
    staleness_seconds: int


# Measurement source:
# plan/token-spend-analysis/research/005-account-attribution-build-2026-10-25.md.
# Its captured window measured the other MCP-key callers at two to three queries every
# five minutes (24--36 queries/hour) plus at most one `run_turn` read every 15 minutes
# (4 queries/hour): 28--40 queries/hour. Reserving the 40 queries/hour upper bound from
# the key's 100 queries/hour budget leaves 60/hour, or 15 queries for each 15-minute tick.
MAX_QUERIES_PER_TICK: Final[int] = 15


TICK_SPECS: Final[tuple[QuerySpec, ...]] = (
    QuerySpec(
        name="available_memory",
        dataset="metrics",
        calculations=(
            {
                "op": "MAX",
                "column": "system.linux.memory.available",
                "name": "available_memory_bytes",
            },
        ),
        filters=(),
        breakdowns=("host.name",),
        window_seconds=900,
        expected_columns={"available_memory_bytes": float},
        staleness_seconds=900,
    ),
)
