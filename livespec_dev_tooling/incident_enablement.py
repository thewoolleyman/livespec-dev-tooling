"""The incident enablement record the independent controller holds, and its fence.

The one enablement step writes the record through the controller's control route; the
execution resolver at every vantage reads it through the read-only query route. The
record binds the repository, the committed manifest identity of livespec core, the
step's operation identity and the controller release that retained it. The controller
confirms that identity with its own reads of core's default branch: twice before it
retains a record, and under a bounded freshness rule on every answer (a head read per
answer, the manifest re-read only when the head moved, a confirmed identity valid for
at most six hours). Arming the fence is an explicit write the controller refuses until
a record binds the current identity; disarming is explicit too. Nothing here enables,
arms or refuses an incident invocation itself: the resolver reads the answer.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol, cast

from livespec_dev_tooling._incident_fleet_sources import core_head_reader, core_identity_reader
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    repository_lock,
    save_record,
)
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_fleet_host import FLEET_OWNER
from livespec_dev_tooling.incident_fleet_runner import scrubbed_runner
from livespec_dev_tooling.incident_strict_json import strict_json

__all__: list[str] = [
    "CONTROL_PATHS",
    "FRESHNESS_SECONDS",
    "INSTALLATION_PORTS",
    "QUERY_PATHS",
    "EnablementPost",
    "EnablementWriter",
    "IdentitySource",
    "ObserverEnablement",
    "controller_enablement_writer",
    "production_identity_source",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-qmuk7z
ENABLE_PATH = "/enablement"
REVOKE_PATH = "/enablement/revoke"
ARM_PATH = "/fence/arm"
DISARM_PATH = "/fence/disarm"
READ_PATH = "/enablement/read"
CONTROL_PATHS = frozenset({ENABLE_PATH, REVOKE_PATH, ARM_PATH, DISARM_PATH})
QUERY_PATHS = frozenset({READ_PATH})
FRESHNESS_SECONDS = 6 * 60 * 60
_UNCONFIRMED = "manifest identity unconfirmed by the controller's own core read; nothing retained"
_NOT_ENABLED = "no record binds the current manifest identity; the fence stays disarmed"


@dataclass(frozen=True, kw_only=True)
class IdentitySource:
    """Fresh reads of livespec core's default branch: its head commit and manifest digest."""

    read_head: Callable[[], str | None]
    read_identity: Callable[[], str | None]


def production_identity_source() -> IdentitySource:
    """Core's head by ``git ls-remote`` and its manifest digest as the fleet audit reads it."""
    return IdentitySource(
        read_head=core_head_reader(owner=FLEET_OWNER, run=scrubbed_runner),
        read_identity=core_identity_reader(owner=FLEET_OWNER, run=scrubbed_runner),
    )


@dataclass(frozen=True, kw_only=True)
class ObserverEnablement:
    """Hold, fence and answer for one installation's enablement record."""

    installation: ControllerInstallation
    source: IdentitySource
    now: Callable[[], float] = field(default=time.time)

    def execute(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        if path == ENABLE_PATH and set(payload) == {
            "repository",
            "manifest_sha256",
            "operation_id",
        }:
            return self._enable(payload=payload)
        if path in {REVOKE_PATH, ARM_PATH, DISARM_PATH} and set(payload) == {
            "repository",
            "operation_id",
        }:
            return self._fence_or_revoke(path=path, payload=payload)
        if path == READ_PATH and set(payload) == {"repository"}:
            return self._read(payload=payload)
        return _refused(reason="unknown or malformed enablement operation")

    def _state_path(self) -> Path:
        digest = hashlib.sha256(self.installation.repository.encode()).hexdigest()
        return self.installation.state / f"enablement-{digest}.json"

    def _enable(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        identity, operation = payload["manifest_sha256"], payload["operation_id"]
        if not (isinstance(identity, str) and isinstance(operation, str) and operation):
            return _refused(reason="unknown or malformed enablement operation")
        request = _digest(value=payload)
        with self._lock():
            state = self._load()
            retained = _retained(state=state, operation=operation)
            if retained is not None:
                return _retry(retained=retained, request=request)
        # The two confirming reads go outside the fence, so a blocked read cannot hold it.
        confirmations = (self.source.read_identity(), self.source.read_identity())
        if confirmations != (identity, identity):
            return _refused(reason=_UNCONFIRMED)
        record = {
            "repository": self.installation.repository,
            "manifest_sha256": identity,
            "operation_id": operation,
            "controller_release": self.installation.release,
            "controller_revision": self.installation.revision,
        }
        answer = {"schema": 1, "status": "enabled", "record": record}
        with self._lock():
            state = self._load()
            retained = _retained(state=state, operation=operation)
            if retained is not None:
                return _retry(retained=retained, request=request)
            state["record"] = record
            state["revoked"] = None
            _remember(state=state, operation=operation, request=request, answer=answer)
            self._save(state=state)
        return answer

    def _fence_or_revoke(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        operation = payload["operation_id"]
        if not (isinstance(operation, str) and operation):
            return _refused(reason="unknown or malformed enablement operation")
        request = _digest(value={"path": path, **payload})
        confirmed = self._confirmed() if path == ARM_PATH else None
        with self._lock():
            state = self._load()
            retained = _retained(state=state, operation=operation)
            if retained is not None:
                return _retry(retained=retained, request=request)
            if path == ARM_PATH and _reading(state=state, confirmed=confirmed) != "enabled":
                return _refused(reason=_NOT_ENABLED)
            if path == REVOKE_PATH:
                state["revoked"] = operation
                answer = {"schema": 1, "status": "revoked", "operation_id": operation}
            else:
                state["armed"] = path == ARM_PATH
                answer = {
                    "schema": 1,
                    "status": "armed" if path == ARM_PATH else "disarmed",
                    "operation_id": operation,
                }
            _remember(state=state, operation=operation, request=request, answer=answer)
            self._save(state=state)
        return answer

    def _read(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        confirmed = self._confirmed()
        with self._lock():
            state = self._load()
        return {
            "schema": 1,
            "status": _reading(state=state, confirmed=confirmed),
            "query": payload,
            "confirmed_manifest_sha256": confirmed,
            "armed": bool(state.get("armed", False)),
        }

    def _confirmed(self) -> str | None:
        """The committed manifest identity under the bounded freshness rule, or None."""
        head = self.source.read_head()
        moment = self.now()
        with self._lock():
            state = self._load()
        cached = cast("dict[str, Any] | None", state.get("confirmed"))
        fresh = cached is not None and moment - float(cached["at"]) <= FRESHNESS_SECONDS
        if head is None:
            return cast("str", cached["identity"]) if fresh and cached is not None else None
        if fresh and cached is not None and cached["head"] == head:
            return cast("str", cached["identity"])
        identity = self.source.read_identity()
        if identity is None:
            return None
        with self._lock():
            state = self._load()
            state["confirmed"] = {"head": head, "identity": identity, "at": moment}
            self._save(state=state)
        return identity

    def _lock(self) -> Any:
        settings = self.installation
        return repository_lock(directory=settings.state, repository=settings.repository)

    def _load(self) -> dict[str, Any]:
        return cast("dict[str, Any]", load_record(path=self._state_path()))

    def _save(self, *, state: dict[str, Any]) -> None:
        save_record(path=self._state_path(), record=state)


# The listener port of each production controller installation, equal by test to the
# incident_observer role's default port. Only the installation serving a repository can
# hold its record; a repository absent here has no installation and is refused by name.
INSTALLATION_PORTS: Mapping[str, int] = MappingProxyType(
    {"thewoolleyman/livespec-dev-tooling": 8765}
)
_CONTROL_SECRET_ENV = "LIVESPEC_INCIDENT_CONTROL_SECRET"  # noqa: S105 - a variable name
_ACCEPTED = 202


class EnablementPost(Protocol):
    def __call__(self, *, url: str, secret: bytes, body: bytes) -> tuple[int, dict[str, Any]]: ...


class EnablementWriter(Protocol):
    def __call__(self, *, repository: str, manifest_sha256: str) -> tuple[int, str]: ...


def _post(*, url: str, secret: bytes, body: bytes) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(  # noqa: S310 - fixed loopback http URL
        url,
        data=body,
        method="POST",
        headers={"Authorization": "Bearer " + secret.decode(), "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
            return response.status, cast(
                "dict[str, Any]", strict_json(text=response.read(), limit=None)
            )
    except urllib.error.HTTPError as refused:
        return refused.code, cast(
            "dict[str, Any]", strict_json(text=refused.read() or b"{}", limit=None)
        )


def controller_enablement_writer(
    *, environ: Mapping[str, str] = os.environ, post: EnablementPost = _post
) -> EnablementWriter:
    """The enablement step's one durable output: a record on the serving controller."""

    def write(*, repository: str, manifest_sha256: str) -> tuple[int, str]:
        port = INSTALLATION_PORTS.get(repository)
        if port is None:
            return 1, f"refused\t{repository}: no controller installation serves it"
        secret = environ.get(_CONTROL_SECRET_ENV, "")
        if not secret:
            return 1, f"refused\t{repository}: {_CONTROL_SECRET_ENV} is not projected"
        payload = {
            "repository": repository,
            "manifest_sha256": manifest_sha256,
            "operation_id": f"incident-enable-{uuid.uuid4().hex}",
        }
        try:
            status, answer = post(
                url=f"http://127.0.0.1:{port}{ENABLE_PATH}",
                secret=secret.encode(),
                body=json.dumps(payload).encode(),
            )
        except (OSError, ValueError) as unreachable:
            return 1, f"refused\t{repository}: controller unreachable: {unreachable}"
        if status == _ACCEPTED and answer.get("status") == "enabled":
            return 0, f"enabled\t{repository}"
        return 1, f"refused\t{repository}: controller refused: {answer.get('reason', status)}"

    return write


def _reading(*, state: dict[str, Any], confirmed: str | None) -> str:
    record = cast("dict[str, Any] | None", state.get("record"))
    if confirmed is None:
        return "unavailable"
    if record is None:
        return "absent"
    if state.get("revoked") is not None:
        return "revoked"
    return "enabled" if record["manifest_sha256"] == confirmed else "stale"


def _retained(*, state: dict[str, Any], operation: str) -> dict[str, Any] | None:
    operations = cast("dict[str, dict[str, Any]]", state.get("operations", {}))
    return operations.get(operation)


def _retry(*, retained: dict[str, Any], request: str) -> dict[str, Any]:
    if retained["request"] != request:
        return _refused(reason="operation identity already retained with different bytes")
    return cast("dict[str, Any]", retained["answer"])


def _remember(
    *, state: dict[str, Any], operation: str, request: str, answer: dict[str, Any]
) -> None:
    operations = cast("dict[str, dict[str, Any]]", state.setdefault("operations", {}))
    operations[operation] = {"request": request, "answer": answer}


def _digest(*, value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def _refused(*, reason: str) -> dict[str, Any]:
    return {"schema": 1, "status": "refused", "reason": reason}
