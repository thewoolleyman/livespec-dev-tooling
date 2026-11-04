"""Canonical immutable recovery effect history and exact result validation."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict
from typing import Any

from livespec_dev_tooling._incident_observer_types import RecoveryIntent
from livespec_dev_tooling._incident_recovery_journal_identity import JournalCodec
from livespec_dev_tooling._incident_recovery_journal_types import JournalResult

__all__: list[str] = ["JournalHistory"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac
_DIGEST = re.compile(r"[0-9a-f]{64}")


class JournalHistory:
    """Derive and authenticate one non-authorizing retained effect result."""

    @staticmethod
    def digest(*, value: Any) -> str:
        return hashlib.sha256(JournalCodec.canonical(value=value)).hexdigest()

    @staticmethod
    def result(*, operation: str, request: dict[str, Any]) -> JournalResult:
        digest = JournalHistory.digest(value={"request": request})
        if operation == "reserve":
            return JournalResult(
                status="reserved",
                reason="durable non-authorizing action reservation",
                request_sha256=digest,
            )
        return JournalResult(
            status="recorded",
            reason="durable owned rollback conflict",
            receipt=request["receipt"],
            request_sha256=digest,
        )

    @staticmethod
    def entry(*, operation: str, request: dict[str, Any], context: str | None) -> dict[str, Any]:
        result = asdict(JournalHistory.result(operation=operation, request=request))
        history = {
            "operation": operation,
            "request_sha256": result["request_sha256"],
            "result": result,
            "context_sha256": context,
        }
        return {
            "schema": 1,
            "intent_sha256": JournalHistory.digest(value=request["intent"]),
            "operation": operation,
            "request": request,
            "context_sha256": context,
            "result": result,
            "history": [history],
        }

    @staticmethod
    def validate(*, entry: dict[str, Any], intent: RecoveryIntent) -> JournalResult:
        fields = {
            "schema",
            "intent_sha256",
            "operation",
            "request",
            "context_sha256",
            "result",
            "history",
        }
        if (
            set(entry) != fields
            or type(entry["schema"]) is not int
            or entry["schema"] != 1
            or entry["operation"] not in {"reserve", "conflict"}
        ):
            message = "invalid recovery effect history"
            raise ValueError(message)
        operation, request, context = entry["operation"], entry["request"], entry["context_sha256"]
        decoded = JournalCodec.request(operation=operation, raw=request)
        if JournalCodec.canonical(value=asdict(decoded.intent)) != JournalCodec.canonical(
            value=asdict(intent)
        ):
            message = "recovery history belongs to another retained action"
            raise ValueError(message)
        if (operation == "reserve" and context is not None) or (
            operation == "conflict"
            and (not isinstance(context, str) or _DIGEST.fullmatch(context) is None)
        ):
            message = "invalid independently authenticated scope context"
            raise ValueError(message)
        expected = JournalHistory.entry(
            operation=operation, request=JournalCodec.wire(value=asdict(decoded)), context=context
        )
        if JournalCodec.canonical(value=entry) != JournalCodec.canonical(value=expected):
            message = "recovery effect request or result history is corrupt"
            raise ValueError(message)
        return JournalHistory.result(operation=operation, request=request)
