"""Strict bounded JSON and base64url at the untrusted CI identity seam."""

from __future__ import annotations

import base64
import re
from typing import Any, cast

from livespec_dev_tooling.incident_strict_json import strict_json

__all__: list[str] = ["identity_json", "unbase64url"]


def identity_json(*, raw: bytes, limit: int = 65536) -> dict[str, Any]:
    """Decode an object without duplicate keys or non-JSON numeric extensions."""
    value: object = strict_json(text=raw, limit=limit)
    if not isinstance(value, dict):
        message = "identity JSON must be an object"
        raise TypeError(message)
    return cast("dict[str, Any]", value)


def unbase64url(*, value: object, limit: int) -> bytes:
    """Require canonical unpadded base64url, including its unused trailing bits."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > limit
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
    ):
        message = "invalid identity base64url"
        raise ValueError(message)
    decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    if base64.urlsafe_b64encode(decoded).rstrip(b"=").decode() != value:
        message = "noncanonical identity base64url"
        raise ValueError(message)
    return decoded
