"""The one strict JSON decoder for every incident-path read of foreign text.

Python's ``json.loads`` accepts three ambiguities the incident path must never
trust: the last spelling of a duplicate key silently wins, ``NaN`` and
``Infinity`` parse as floats although JSON has no such numbers, and an
out-of-range exponent such as ``1e999`` becomes infinity without ever reaching
the constant hook. Five decoders once each handled a different subset of these
and refused in five different shapes. Every incident decoder now calls this one,
and every refusal is an ``IncidentJsonRefusalError``.
"""

from __future__ import annotations

import json
import math
from typing import Any, NoReturn

__all__: list[str] = ["DEFAULT_LIMIT", "IncidentJsonRefusalError", "strict_json"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-utw7u6
DEFAULT_LIMIT = 65536
_PREFIX = "incident JSON refused: "


class IncidentJsonRefusalError(Exception):
    """The single refusal shape for every incident JSON decoder.

    ``kind`` names the ambiguity for a caller that keeps its own refusal codes:
    ``duplicate-key``, ``non-finite``, ``nesting`` or the default ``malformed``.
    """

    kind: str = "malformed"


def _refuse(*, detail: str, kind: str = "malformed") -> NoReturn:
    refusal = IncidentJsonRefusalError(_PREFIX + detail)
    refusal.kind = kind
    raise refusal


def _unique(*, pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            _refuse(detail="duplicate key", kind="duplicate-key")
        value[key] = item
    return value


def _constant(*, name: str) -> NoReturn:
    _refuse(detail="non-finite number " + name, kind="non-finite")


def _number(*, text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        _refuse(detail="non-finite number " + text, kind="non-finite")
    return value


def strict_json(*, text: str | bytes, limit: int | None = DEFAULT_LIMIT) -> Any:
    """Bound and decode JSON, refusing duplicate keys and non-finite numbers.

    ``limit`` is a byte bound on the encoded input (65536 by default); ``None`` means the caller
    has no bound to apply. Anything the decoder cannot accept raises
    ``IncidentJsonRefusalError``.
    """
    size = len(text) if isinstance(text, bytes) else len(text.encode("utf-8", "surrogatepass"))
    if limit is not None and size > limit:
        _refuse(detail=f"input exceeds its {limit}-byte bound")
    try:
        return json.loads(
            text.decode("utf-8") if isinstance(text, bytes) else text,
            object_pairs_hook=lambda pairs: _unique(pairs=pairs),
            parse_constant=lambda name: _constant(name=name),
            parse_float=lambda number: _number(text=number),
        )
    except IncidentJsonRefusalError:
        raise
    except UnicodeDecodeError:
        _refuse(detail="input is not UTF-8")
    except RecursionError:
        _refuse(detail="nesting is too deep", kind="nesting")
    except ValueError:
        _refuse(detail="malformed JSON")
