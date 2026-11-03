"""Committed data contract for the scheduler's deterministic Honeycomb reads."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal, TypeAlias

__all__: list[str] = [
    "FALLBACK_TABLE",
    "MAX_QUERIES_PER_TICK",
    "TICK_SPECS",
    "ColumnValue",
    "InputValue",
    "QuerySpec",
    "TickSnapshot",
]

ColumnValue: TypeAlias = str | float | int | bool | None
ColumnType: TypeAlias = type[str] | type[float] | type[int] | type[bool]


@dataclass(frozen=True, kw_only=True)
class QuerySpec:
    """One versioned Honeycomb query, including the result contract it must satisfy."""

    name: str
    dataset: str
    calculations: tuple[Mapping[str, str], ...]
    filters: tuple[Mapping[str, str], ...]
    breakdowns: tuple[str, ...]
    window_seconds: int
    expected_columns: Mapping[str, ColumnType]
    staleness_seconds: int


@dataclass(frozen=True, kw_only=True)
class InputValue:
    """Rows for one input, including whether they are live or conservative fallback values."""

    rows: tuple[Mapping[str, ColumnValue], ...]
    inputs: Literal["live", "fallback"]
    failure_reason: str | None


@dataclass(frozen=True, kw_only=True)
class TickSnapshot:
    """A complete immutable tick result; partial live inputs are never returned after a failure."""

    values: Mapping[str, InputValue]
    queries_spent: int


# Measurement source: plan/token-spend-analysis/research/005-account-attribution-build-2026-10-25.md
# measured the other MCP-key callers at 2--3 queries every five minutes plus one `run_turn`
# read every 15 minutes: 36--40 queries/hour in its captured window. Reserving that measured
# 40/hour share from the 100/hour key leaves 60/hour, or 15 queries for each 15-minute tick.
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

# A zero available-memory value is deliberately conservative: a consumer cannot admit work from it.
FALLBACK_TABLE: Final[Mapping[str, tuple[Mapping[str, ColumnValue], ...]]] = {
    "available_memory": ({"available_memory_bytes": 0.0},),
}
