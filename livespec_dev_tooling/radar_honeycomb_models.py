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
# plan/radar-and-deterministic-admission/research/002-mcp-key-caller-rate-2026-11-03.md.
# In the steady-state window 2026-11-03 18:20:26Z to 19:20:29Z UTC, after the token-spend
# cut, the measurement found about 36 queries/hour for the other callers.
# The 40 queries/hour reserved leave 60/hour, or 15 queries for each 15-minute tick.
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
