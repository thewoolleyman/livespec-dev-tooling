"""Concurrent request dispatch for the independent observer's WSGI server."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from threading import Thread
from typing import Any

__all__: list[str] = [
    "REFUSED_CONTROL",
    "REFUSED_REQUEST",
    "REFUSED_STARTUP",
    "RequestDispatcher",
    "json_reply",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
# What the service prints when it is not an isolated, provisioned installation.
REFUSED_STARTUP = json.dumps(
    {
        "status": "refused",
        "reason": "protected released installation and recovery capability required",
    }
)

# What a control or query route answers without its secret or for another repository.
REFUSED_CONTROL = {
    "status": "refused",
    "reason": "protected control authentication and repository required",
}
# What a control or query route answers to an invalid request or unavailable state.
REFUSED_REQUEST = {
    "status": "refused",
    "reason": "invalid control request or unavailable protected state",
}


@dataclass(frozen=True, kw_only=True)
class RequestDispatcher:
    """Compose concurrent dispatch through BaseServer's public request protocol."""

    server: Any

    def __call__(self, request: Any, client_address: Any) -> None:
        Thread(
            target=self._finish,
            kwargs={"request": request, "address": client_address},
            daemon=True,
        ).start()

    def _finish(self, *, request: Any, address: Any) -> None:
        request.settimeout(10)
        try:
            self.server.finish_request(request, address)
        finally:
            self.server.shutdown_request(request)


def json_reply(
    *, start_response: Callable[[str, list[tuple[str, str]]], object], status: str, result: object
) -> list[bytes]:
    """One uncached JSON answer."""
    _ = start_response(
        status, [("Content-Type", "application/json"), ("Cache-Control", "no-store")]
    )
    return [json.dumps(result).encode()]
