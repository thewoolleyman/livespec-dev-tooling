"""Retry an untouched failing pytest test under the ratified policy."""

from __future__ import annotations

__all__: list[str] = [
    "RETRY_ATTEMPTS",
    "RETRY_DELAY_SECONDS",
]

RETRY_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 60
