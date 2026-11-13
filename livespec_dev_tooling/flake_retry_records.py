"""Retry-record value types and serialisation for the flake-retry plugin."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

_FAILURE_TEXT_LIMIT = 4000

__all__: list[str] = [
    "RetryFailure",
    "RetryResult",
    "failure_from",
    "records_json",
    "summary",
]


@dataclass(frozen=True, kw_only=True)
class RetryFailure:
    """A bounded diagnostic captured from one failed retry attempt."""

    text: str
    cut: bool


@dataclass(frozen=True, kw_only=True)
class RetryResult:
    """The final outcome of a test pytest-rerunfailures has retried."""

    nodeid: str
    attempts: int
    outcome: str
    failures: tuple[RetryFailure, ...] = ()


def failure_from(*, longrepr: object) -> RetryFailure:
    """Preserve a compact rendering of a failed pytest report."""
    text = str(longrepr)
    return RetryFailure(text=text[:_FAILURE_TEXT_LIMIT], cut=len(text) > _FAILURE_TEXT_LIMIT)


def records_json(*, results: Iterable[RetryResult]) -> str:
    """Return one deterministic JSON line for each retried node id."""
    return "".join(json.dumps(asdict(result), sort_keys=True) + "\n" for result in results)


def summary(*, results: Iterable[RetryResult]) -> str:
    """Render the loud terminal block required for every retry decision."""
    rows: list[str] = []
    for result in results:
        rows.append(f"{result.nodeid}: {result.attempts} attempts, {result.outcome}")
        rows.extend(f"  {_first_failure_line(failure=failure)}" for failure in result.failures)
    return "FLAKE-RETRIED\n" + "\n".join(rows)


def _first_failure_line(*, failure: RetryFailure) -> str:
    """Return a summary-safe first line for one recorded failure."""
    return next((line for line in failure.text.splitlines() if line), "<no failure text>")
