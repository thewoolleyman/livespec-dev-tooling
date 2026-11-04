"""Run the independent observer from protected released host configuration.

Only the independently provisioned controller account starts this process. HTTP
requests never supply executables, release identity, state paths or principals.
"""

from __future__ import annotations

import argparse
import hmac
import importlib
import io
import json
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from threading import Thread
from typing import Any, cast
from wsgiref.simple_server import make_server

from livespec_dev_tooling._incident_observer_types import (
    RecoveryIntent,
)
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_observer_control import ObserverControl
from livespec_dev_tooling.incident_observer_endpoint import _read_request, observer_endpoint
from livespec_dev_tooling.incident_observer_events import verify_leaf_completion
from livespec_dev_tooling.incident_observer_query import ObserverQuery

__all__: list[str] = ["ControllerService"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wanebl
_StartResponse = Callable[[str, list[tuple[str, str]]], object]


@dataclass(frozen=True, kw_only=True)
class ControllerService:
    """A WSGI service over the canonical reader, protected arm and real callback."""

    installation: ControllerInstallation
    recover: Callable[[RecoveryIntent], str | None]

    @classmethod
    def installed(cls, *, config: Path) -> ControllerService | None:
        """Fail before listening if the independently installed inverse is absent."""
        installation = ControllerInstallation.load(config=config)
        if installation is None:
            return None
        try:
            inverse = importlib.import_module("livespec_dev_tooling.incident_inverse")
            service = importlib.import_module("livespec_dev_tooling.incident_inverse_service")
            principal = service.ProcessInverseForge(command=installation.principal)
            callback = inverse.observer_inverse_callback(
                repo_root=installation.repo, forge=principal
            )
        except (ImportError, AttributeError, OSError, ValueError):
            return None
        return cls(installation=installation, recover=callback)

    def __call__(self, environ: dict[str, Any], start_response: _StartResponse) -> Iterable[bytes]:
        """Authenticate control calls separately from GitHub's signed callback."""
        if environ.get("PATH_INFO") == "/callback":
            return self._callback(environ=environ, start_response=start_response)
        path = str(environ.get("PATH_INFO", ""))
        secret = (
            self.installation.query_secret
            if path in {"/current", "/admitted"}
            else self.installation.control_secret
        )
        authorized = path in {
            "/current",
            "/admitted",
            "/arm",
            "/bind",
            "/invalidate-ci",
        } and hmac.compare_digest(
            str(environ.get("HTTP_AUTHORIZATION", "")).encode(),
            b"Bearer " + secret,
        )
        body = _read_request(environ=environ) if authorized else None
        try:
            raw_payload: object = json.loads(body) if body is not None else None
            payload = cast("dict[str, Any]", raw_payload)
            if (
                not isinstance(raw_payload, dict)
                or payload.get("repository") != self.installation.repository
            ):
                return _reply(
                    start_response=start_response,
                    status="403 Forbidden",
                    result={
                        "status": "refused",
                        "reason": "protected control authentication and repository required",
                    },
                )
            handler = (
                ObserverQuery(installation=self.installation)
                if path in {"/current", "/admitted"}
                else ObserverControl(installation=self.installation)
            )
            result = handler.execute(path=path, payload=payload)
            return _reply(
                start_response=start_response,
                status="403 Forbidden" if result.get("status") == "refused" else "202 Accepted",
                result=result,
            )
        except (OSError, ValueError, TypeError, KeyError):
            return _reply(
                start_response=start_response,
                status="403 Forbidden",
                result={
                    "status": "refused",
                    "reason": "invalid control request or unavailable protected state",
                },
            )

    def _callback(
        self, *, environ: dict[str, Any], start_response: _StartResponse
    ) -> Iterable[bytes]:
        body = _read_request(environ=environ)
        completion = verify_leaf_completion(
            body=body or b"",
            signature=str(environ.get("HTTP_X_HUB_SIGNATURE_256", "")),
            event=str(environ.get("HTTP_X_GITHUB_EVENT", "")),
            delivery_id=str(environ.get("HTTP_X_GITHUB_DELIVERY", "")),
            secret=self.installation.webhook_secret,
        )
        if completion is None or completion.repository != self.installation.repository:
            return _reply(
                start_response=start_response,
                status="403 Forbidden",
                result={
                    "status": "refused",
                    "reason": "authenticated callback outside provisioned repository",
                },
            )
        forwarded = {**environ, "wsgi.input": io.BytesIO(body or b"")}
        return observer_endpoint(
            directory=self.installation.state,
            webhook_secret=self.installation.webhook_secret,
            recover=self.recover,
        )(forwarded, start_response)


def _reply(*, start_response: _StartResponse, status: str, result: dict[str, Any]) -> list[bytes]:
    _ = start_response(
        status, [("Content-Type", "application/json"), ("Cache-Control", "no-store")]
    )
    return [json.dumps(result).encode()]


@dataclass(frozen=True, kw_only=True)
class _RequestDispatcher:
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


def main() -> int:
    """Serve only a provisioned isolated installation on loopback behind host TLS."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    application = ControllerService.installed(config=args.config) if sys.flags.isolated else None
    if application is None:
        _ = sys.stdout.write(
            json.dumps(
                {
                    "status": "refused",
                    "reason": "protected released installation and recovery capability required",
                }
            )
        )
        return 2
    with make_server("127.0.0.1", application.installation.port, application) as server:
        server.process_request = _RequestDispatcher(server=server)
        server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
