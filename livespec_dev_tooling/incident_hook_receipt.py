"""Validate exact immutable receipt lookup before another local gate execution."""

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-cerkbn
from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling.incident_hook_process import HookRefusalError

__all__: list[str] = ["recover_receipt"]
_MAX_EXIT = 255


def recover_receipt(
    *,
    repo: Path,
    query: dict[str, Any],
    reading: dict[str, Any],
    identity: dict[str, str],
    invoke: Callable[..., dict[str, Any]],
) -> dict[str, Any] | None:
    result = invoke(
        repo=repo, query=query, action="read-local-gates", receipt_id=identity["receipt_id"]
    )
    expected = dict(
        receipt_id=identity["receipt_id"],
        committed_token_id=reading["committed_token_id"],
        current_token_id=reading["current_token_id"],
    )
    if any(result.get(key) != value for key, value in expected.items()):
        message = "partial receipt lookup does not bind this invocation"
        raise HookRefusalError(message)
    if (
        result.get("status") == "absent"
        and result.get("receipt") is None
        and result.get("checksum") is None
    ):
        return None
    raw = result.get("receipt")
    receipt = cast("dict[str, Any]", raw) if isinstance(raw, dict) else None
    checksum = result.get("checksum")
    if (
        result.get("status") != "recorded"
        or not isinstance(receipt, dict)
        or any(receipt.get(key) != value for key, value in identity.items())
        or receipt.get("evidence_kind") != "expedited-local-partial"
        or type(receipt.get("exit_status")) is not int
        or not 0 <= receipt["exit_status"] <= _MAX_EXIT
        or not isinstance(checksum, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", checksum) is None
    ):
        message = "partial receipt lookup is malformed or conflicts"
        raise HookRefusalError(message)
    return receipt
