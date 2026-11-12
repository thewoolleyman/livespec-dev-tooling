"""Run the independent observer from protected released host configuration.

Only the independently provisioned controller account starts this process. HTTP
requests never supply executables, release identity, state paths or principals.
"""

from __future__ import annotations

import argparse
import hmac
import importlib
import io
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from threading import Event
from typing import Any, cast
from wsgiref.simple_server import make_server

from livespec_dev_tooling import incident_enablement as enable
from livespec_dev_tooling._incident_ci_identity_json import identity_json
from livespec_dev_tooling._incident_observer_dispatch import REFUSED_STARTUP
from livespec_dev_tooling._incident_observer_dispatch import RequestDispatcher as _RequestDispatcher
from livespec_dev_tooling._incident_observer_dispatch import json_reply as _reply
from livespec_dev_tooling._incident_observer_routes import CONTROL_PATHS, QUERY_PATHS
from livespec_dev_tooling._incident_observer_types import RecoveryIntent
from livespec_dev_tooling._incident_original_run_canonical import LedgerPort
from livespec_dev_tooling._incident_original_run_ports import installed_ports
from livespec_dev_tooling.incident_ci_attachment import CiJobAttachment
from livespec_dev_tooling.incident_ci_identity import CiIdentityVerifier
from livespec_dev_tooling.incident_ci_job_collection import CiJobCollection
from livespec_dev_tooling.incident_conflict_sweep import ConflictSweep, waking_recover
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_observer_control import ObserverControl
from livespec_dev_tooling.incident_observer_endpoint import _read_request, observer_endpoint
from livespec_dev_tooling.incident_observer_events import verify_leaf_completion
from livespec_dev_tooling.incident_observer_provenance import ObserverProvenance
from livespec_dev_tooling.incident_observer_query import ObserverQuery
from livespec_dev_tooling.incident_observer_reconcile import ObserverReconcile
from livespec_dev_tooling.incident_observer_recovery import ObserverRecovery
from livespec_dev_tooling.incident_original_run_watch import installed_watcher
from livespec_dev_tooling.incident_pr_run_records import PrRunSweep, retain_callback_run
from livespec_dev_tooling.incident_release_screen import RELEASE_SCREEN_PATH, ReleaseScreen
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["ControllerService", "installed_ledger"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wanebl
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-si6uu7
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gho3w4
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zbzls2
# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-ariayn
_ROUTED = {"/provenance": ObserverProvenance, "/reconcile": ObserverReconcile}
_OIDC_ROUTES = {"/ci/identity": CiIdentityVerifier, "/ci/attach": CiJobAttachment}
_StartResponse = Callable[[str, list[tuple[str, str]]], object]


@dataclass(frozen=True, kw_only=True)
class ControllerService:
    """A WSGI service over the canonical reader, protected arm and real callback."""

    installation: ControllerInstallation
    recover: Callable[[RecoveryIntent], str | None]
    # Set when a recovery journals a rollback-conflict, so the conflict sweep writes it to
    # the chain at once, outside the fence the recovery itself ran under.
    conflict_journaled: Event = field(default_factory=Event, compare=False, repr=False)
    # Set when a callback retains an expedited pull-request run record, so the run sweep
    # writes it onto the incident item at once, outside the repository lock.
    pr_run_retained: Event = field(default_factory=Event, compare=False, repr=False)
    identity_source: enable.IdentitySource = field(
        default_factory=enable.production_identity_source
    )

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
        journaled = Event()
        return cls(
            installation=installation,
            recover=waking_recover(callback=callback, journaled=journaled),
            conflict_journaled=journaled,
        )

    def __call__(self, environ: dict[str, Any], start_response: _StartResponse) -> Iterable[bytes]:
        """Authenticate control calls separately from GitHub's signed callback."""
        if environ.get("PATH_INFO") == "/callback":
            return self._callback(environ=environ, start_response=start_response)
        path = str(environ.get("PATH_INFO", ""))
        if path in _OIDC_ROUTES:
            return self._identity(environ=environ, start_response=start_response, path=path)
        secret = (
            self.installation.query_secret
            if path in QUERY_PATHS
            else self.installation.control_secret
        )
        authorized = path in QUERY_PATHS | CONTROL_PATHS and hmac.compare_digest(
            str(environ.get("HTTP_AUTHORIZATION", "")).encode(),
            b"Bearer " + secret,
        )
        body = _read_request(environ=environ) if authorized else None
        try:
            raw_payload: object = strict_json(text=body, limit=None) if body is not None else None
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
            result = (
                ObserverRecovery(installation=self.installation, recover=self.recover).execute(
                    payload=payload
                )
                if path == "/recover"
                else self._handler(path=path).execute(path=path, payload=payload)
            )
            return _reply(
                start_response=start_response,
                status="403 Forbidden" if result.get("status") == "refused" else "202 Accepted",
                result=result,
            )
        except (OSError, ValueError, IncidentJsonRefusalError, TypeError, KeyError):
            return _reply(
                start_response=start_response,
                status="403 Forbidden",
                result={
                    "status": "refused",
                    "reason": "invalid control request or unavailable protected state",
                },
            )

    def _handler(
        self, *, path: str
    ) -> (
        CiJobCollection
        | ObserverProvenance
        | ObserverQuery
        | ObserverReconcile
        | ObserverControl
        | enable.ObserverEnablement
        | ReleaseScreen
    ):
        if path == RELEASE_SCREEN_PATH:
            return ReleaseScreen(installation=self.installation)
        if path.startswith("/ci/jobs/"):
            return CiJobCollection(installation=self.installation)
        if path in _ROUTED:
            return _ROUTED[path](installation=self.installation)
        if path in enable.CONTROL_PATHS | enable.QUERY_PATHS:
            source, installation = self.identity_source, self.installation
            return enable.ObserverEnablement(installation=installation, source=source)
        if path in QUERY_PATHS:
            return ObserverQuery(installation=self.installation)
        return ObserverControl(installation=self.installation)

    def _identity(
        self, *, environ: dict[str, Any], start_response: _StartResponse, path: str
    ) -> Iterable[bytes]:
        result = {"schema": 1, "status": "refused", "reason": "protected CI identity unavailable"}
        if (
            environ.get("REQUEST_METHOD") == "POST"
            and getattr(self.installation, "ci_identity_policy", None) is not None
        ):
            try:
                payload = identity_json(raw=_read_request(environ=environ) or b"")
                result = _OIDC_ROUTES[path](installation=self.installation).execute(
                    authorization=str(environ.get("HTTP_AUTHORIZATION", "")), payload=payload
                )
            except (OSError, ValueError, IncidentJsonRefusalError, TypeError, RecursionError):
                pass
        return _reply(
            start_response=start_response,
            status="202 Accepted"
            if result.get("status") in {"authenticated", "attached"}
            else "403 Forbidden",
            result=result,
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
        if completion.branch != self.installation.target_branch:
            # Only the configured target branch's jobs reach recovery; a registration
            # retained for any other branch never acts. An armed pull-request head's
            # incident CI job is still recorded on its incident item, and acts on nothing.
            return _reply(
                start_response=start_response,
                status="202 Accepted",
                result={
                    "status": "ignored",
                    "reason": "job is outside the configured target branch",
                    "action_id": None,
                    "pr_run": retain_callback_run(
                        state=self.installation.state,
                        completion=completion,
                        body=body or b"",
                        wake=self.pr_run_retained,
                        identity_provisioned=self.installation.ci_identity_policy is not None,
                    ),
                },
            )
        forwarded = {**environ, "wsgi.input": io.BytesIO(body or b"")}
        return observer_endpoint(
            directory=self.installation.state,
            webhook_secret=self.installation.webhook_secret,
            recover=self.recover,
        )(forwarded, start_response)


def installed_ledger(*, installation: ControllerInstallation) -> LedgerPort | None:
    """The tenant-credentialed ledger port, or None while the credential is unavailable."""
    try:
        return installed_ports(installation=installation).canonical.ledger
    except OSError:
        return None


def main() -> int:
    """Serve only a provisioned isolated installation on loopback behind host TLS."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    application = ControllerService.installed(config=args.config) if sys.flags.isolated else None
    if application is None:
        _ = sys.stdout.write(REFUSED_STARTUP)
        return 2
    _ = ObserverReconcile(installation=application.installation).resume_prepared()
    # A reverted incident's original run is collected by the controller itself, so no
    # operator has to remember to run the entrance; the watcher resumes from the record.
    # A watcher that dies shuts the server down, so the service exits non-zero and systemd
    # restarts it instead of answering HTTP with nothing collecting.
    # The conflict sweep writes journaled rollback-conflicts to the chain outside the
    # fence; like the watcher, a sweep that crashes shuts the server down.
    watcher = installed_watcher(installation=application.installation)
    stop = Event()
    sweep = ConflictSweep(
        installation=application.installation, wake=application.conflict_journaled
    )
    # The run sweep writes armed heads' run records onto their incident items.
    runs = PrRunSweep(
        state=application.installation.state,
        repository=application.installation.repository,
        ledger=lambda: installed_ledger(installation=application.installation),
        wake=application.pr_run_retained,
    )
    with make_server("127.0.0.1", application.installation.port, application) as server:
        server.process_request = _RequestDispatcher(server=server)
        _ = watcher.start(on_exit=server.shutdown)
        _ = sweep.start(stop=stop, on_crash=server.shutdown)
        _ = runs.start(stop=stop, on_crash=server.shutdown)
        try:
            server.serve_forever()
        finally:
            stop.set()
            application.conflict_journaled.set()
            application.pr_run_retained.set()
    return 1 if any(e.is_set() for e in (watcher.failed, sweep.crashed, runs.crashed)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
