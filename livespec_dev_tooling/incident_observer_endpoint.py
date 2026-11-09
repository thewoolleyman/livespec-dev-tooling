"""An actual early-job webhook endpoint for the independent controller host."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any

from livespec_dev_tooling._incident_observer_ack import (
    record_job_callback,
    recover_recorded_job_callback,
)
from livespec_dev_tooling._incident_observer_types import JobCallback, RecoveryIntent

__all__: list[str] = ["observer_endpoint"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
_MAX_BODY_BYTES = 1_000_000
_MAX_LENGTH_DIGITS = len(str(_MAX_BODY_BYTES))
# Strictly inside GitHub's 10-second webhook delivery timeout, leaving the rest for the answer.
_FENCE_WAIT_SECONDS = 5.0
_STATUSES = {"refused": "403 Forbidden", "unavailable": "503 Service Unavailable"}
_StartResponse = Callable[[str, list[tuple[str, str]]], object]


def observer_endpoint(
    *,
    directory: Path,
    webhook_secret: bytes,
    recover: Callable[[RecoveryIntent], str | None],
    fence_wait_seconds: float = _FENCE_WAIT_SECONDS,
) -> Callable[[dict[str, Any], _StartResponse], Iterable[bytes]]:
    """Build the HTTP callback from independent host configuration only.

    No request can create a registration, alter its fence, or supply an authority
    receipt. Production must provision canonical-reader admission and the narrow
    recovery principal before installing this endpoint on the released controller.
    """

    return _ObserverEndpoint(
        directory=directory,
        webhook_secret=webhook_secret,
        recover=recover,
        fence_wait_seconds=fence_wait_seconds,
    )


@dataclass(frozen=True, kw_only=True)
class _ObserverEndpoint:
    """Callable implementing WSGI's externally fixed positional convention."""

    directory: Path
    webhook_secret: bytes
    recover: Callable[[RecoveryIntent], str | None]
    fence_wait_seconds: float

    def __call__(self, environ: dict[str, Any], start_response: _StartResponse) -> Iterable[bytes]:
        body = _read_request(environ=environ)
        if body is None:
            _ = start_response("400 Bad Request", [("Content-Type", "application/json")])
            return [b'{"status":"refused","reason":"invalid callback request"}']
        delivery = JobCallback(
            body=body,
            signature=str(environ.get("HTTP_X_HUB_SIGNATURE_256", "")),
            event=str(environ.get("HTTP_X_GITHUB_EVENT", "")),
            delivery_id=str(environ.get("HTTP_X_GITHUB_DELIVERY", "")),
        )
        result, intent = record_job_callback(
            directory=self.directory,
            delivery=delivery,
            webhook_secret=self.webhook_secret,
            fence_wait_seconds=self.fence_wait_seconds,
        )
        status = _STATUSES.get(result.status, "202 Accepted")
        _ = start_response(status, [("Content-Type", "application/json")])
        if intent is not None:
            Thread(
                target=recover_recorded_job_callback,
                kwargs={"directory": self.directory, "intent": intent, "recover": self.recover},
                name=f"incident-recovery-{intent.action_id}",
                daemon=True,
            ).start()
        return [
            json.dumps(
                {"status": result.status, "reason": result.reason, "action_id": result.action_id}
            ).encode()
        ]


def _read_request(*, environ: dict[str, Any]) -> bytes | None:
    if environ.get("REQUEST_METHOD") != "POST":
        return None
    length = str(environ.get("CONTENT_LENGTH", ""))
    if (
        len(length) > _MAX_LENGTH_DIGITS
        or not length.isascii()
        or not length.isdecimal()
        or int(length) > _MAX_BODY_BYTES
    ):
        return None
    stream = environ.get("wsgi.input")
    if stream is None:
        return None
    body: object = stream.read(int(length))
    return body if isinstance(body, bytes) and len(body) == int(length) else None
