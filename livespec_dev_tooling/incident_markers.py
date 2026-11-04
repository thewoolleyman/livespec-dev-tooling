"""Validate Python incident comment carriers without granting incident authority.

The caller supplies a changed code/test file after authenticating the operation
through the canonical lifecycle reader. This helper only checks its comment
carrier; it never selects a mode or substitutes for a provenance receipt.
"""

from __future__ import annotations

import ast
import io
import sys
import tokenize
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.
from returns.result import Failure, Result, Success, safe  # noqa: E402 — vendor-path-aware import.

__all__: list[str] = ["IncidentMarkerRefusal", "validate_python_repair_marker"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gvylzw
_FIRST_PRINTABLE = 32
_DELETE_CONTROL = 127


@dataclass(frozen=True, kw_only=True)
class IncidentMarkerRefusal:
    """A marker validation failure, distinct from incident authorization."""

    code: str
    detail: str


@safe
def _comment_tokens(*, source: str) -> tuple[tokenize.TokenInfo, ...]:
    """Consume the complete stream so a truncated source never passes early."""
    _ = ast.parse(source)
    return tuple(tokenize.generate_tokens(io.StringIO(source).readline))


def validate_python_repair_marker(
    *, source: str, incident_item_id: str
) -> Result[tuple[int, ...], IncidentMarkerRefusal]:
    """Return actual comment locations, never matches from strings or prose.

    The operation's authenticated incident identity and the changed code/test
    file selection belong to the caller. Returned locations prove only that
    file's comment carrier, not historical provenance or permission to skip work.
    """
    if (
        not incident_item_id
        or incident_item_id != incident_item_id.strip()
        or any(
            ord(character) < _FIRST_PRINTABLE or ord(character) == _DELETE_CONTROL
            for character in incident_item_id
        )
    ):
        return Failure(
            IncidentMarkerRefusal(
                code="invalid-incident-marker-identity",
                detail="marker identity must be nonempty, trimmed and control-free",
            )
        )
    tokens = _comment_tokens(source=source)
    if not is_successful(tokens):
        return Failure(
            IncidentMarkerRefusal(
                code="unreadable-incident-marker-source",
                detail=f"Python comment stream could not be read: {tokens.failure()}",
            )
        )
    expected = f"# EXPEDITED_INCIDENT_RESPONSE flag: {incident_item_id}"
    locations = tuple(
        token.start[0]
        for token in tokens.unwrap()
        if token.type == tokenize.COMMENT and token.string.rstrip() == expected
    )
    if not locations:
        return Failure(
            IncidentMarkerRefusal(
                code="missing-incident-marker",
                detail=f"no exact Python comment carrier for incident {incident_item_id}",
            )
        )
    return Success(locations)
