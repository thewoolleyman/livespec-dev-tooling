"""The enablement readers at the dev-host hooks and on the controller host itself.

The hooks ask the installation this library's committed configuration names for the
repository (`INSTALLATION_PORTS`, kept equal to the observer role's inventory by test)
through its read-only query route with the projected query credential, and compare the
identity the controller confirmed against their own read of core's default branch. The
controller reads its own record directly. The incident CI entrance reads the same query
route through `CiAuthorityBoundary.enablement`.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_enablement_reading import (
    REVERT_PHASES,
    EnablementReader,
    EnablementReading,
    answer_reading,
    fence_refusal,
)
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_enablement import (
    FRESHNESS_SECONDS,
    INSTALLATION_PORTS,
    READ_PATH,
    EnablementPost,
    IdentitySource,
    ObserverEnablement,
    _post,
    production_identity_source,
)
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError, strict_json

__all__: list[str] = ["controller_fence", "installation_reader"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-exdkra
_QUERY_TOKEN_ENV = "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN"  # noqa: S105 - a variable name


@dataclass(frozen=True, kw_only=True)
class _HookConfirmation:
    """The hook's local freshness cache, never the controller enablement record."""

    head: str
    identity: str
    at: float


def _hook_confirmation_path(*, environ: Mapping[str, str], repository: str) -> Path:
    """A host-local state path, deliberately independent of any candidate checkout."""
    state_home = Path(environ.get("XDG_STATE_HOME", str(Path.home() / ".local" / "state")))
    digest = hashlib.sha256(repository.encode()).hexdigest()
    return state_home / "livespec-dev-tooling" / "incident-enablement" / f"{digest}.json"


def _load_hook_confirmation(*, path: Path) -> _HookConfirmation | None:
    """Return only a complete local confirmation; malformed cache state is unavailable."""
    try:
        value: object = strict_json(text=path.read_bytes(), limit=None)
    except (IncidentJsonRefusalError, OSError):
        return None
    if not isinstance(value, dict):
        return None
    record = cast("dict[str, object]", value)
    head, identity, confirmed_at = record.get("head"), record.get("identity"), record.get("at")
    if (
        not isinstance(head, str)
        or not isinstance(identity, str)
        or type(confirmed_at) not in (float, int)
    ):
        return None
    return _HookConfirmation(
        head=head,
        identity=identity,
        at=float(cast("float | int", confirmed_at)),
    )


def _save_hook_confirmation(*, path: Path, confirmation: _HookConfirmation) -> None:
    """Atomically retain a successful own read for a future hook invocation."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            _ = stream.write(
                json.dumps(
                    {
                        "at": confirmation.at,
                        "head": confirmation.head,
                        "identity": confirmation.identity,
                    },
                    sort_keys=True,
                )
            )
            stream.flush()
            os.fsync(stream.fileno())
        _ = Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _own_identity(
    *, environ: Mapping[str, str], repository: str, source: IdentitySource
) -> str | None:
    """Read core's head once and its manifest only when local confirmation needs renewal."""
    moment = time.time()
    path = _hook_confirmation_path(environ=environ, repository=repository)
    cached = _load_hook_confirmation(path=path)
    fresh = cached is not None and moment - cached.at <= FRESHNESS_SECONDS
    head = source.read_head()
    if head is None:
        return cached.identity if fresh and cached is not None else None
    if fresh and cached is not None and cached.head == head:
        return cached.identity
    identity = source.read_identity()
    if identity is None:
        return None
    _save_hook_confirmation(
        path=path,
        confirmation=_HookConfirmation(head=head, identity=identity, at=moment),
    )
    return identity


def installation_reader(
    *,
    environ: Mapping[str, str] = os.environ,
    post: EnablementPost = _post,
    own_identity: Callable[[], str | None] | None = None,
) -> EnablementReader:
    """The dev-host hooks' reader: the serving installation's query route, then core."""

    def read(*, repository: str) -> EnablementReading:
        port = INSTALLATION_PORTS.get(repository)
        if port is None:
            return EnablementReading(
                reading="no-installation",
                armed=None,
                installation="none",
                detail="no controller installation serves it",
            )
        installation = f"127.0.0.1:{port}"
        token = environ.get(_QUERY_TOKEN_ENV, "")
        if not token:
            return EnablementReading(
                reading="unavailable",
                armed=None,
                installation=installation,
                detail=f"{_QUERY_TOKEN_ENV} is not projected; {READ_PATH} was not queried",
            )
        try:
            _status, answer = post(
                url=f"http://{installation}{READ_PATH}",
                secret=token.encode(),
                body=json.dumps({"repository": repository}).encode(),
            )
        except (OSError, ValueError) as unreachable:
            return EnablementReading(
                reading="unavailable",
                armed=None,
                installation=installation,
                detail=f"{READ_PATH} query failed: {unreachable}",
            )
        if own_identity is None:
            source = production_identity_source()

            def own() -> str | None:
                return _own_identity(
                    environ=environ,
                    repository=repository,
                    source=source,
                )

        else:
            own = own_identity
        return answer_reading(
            answer=answer,
            installation=installation,
            repository=repository,
            compare_own=True,
            own_identity=own(),
        )

    return read


def controller_fence(
    *, installation: ControllerInstallation, source: IdentitySource, phase: str, shadow: bool
) -> tuple[EnablementReading | None, str | None]:
    """The controller's own reading of its record, and the refusal an arm in `phase` needs.

    Only an armed fence can refuse, so an entrance that records no reading (`shadow`
    False: the current and admitted answers) reads nothing while disarmed. While
    disarmed with no record retained the reading is `absent` without a read of core,
    because no confirmation of core's identity can make a missing record `enabled`.
    """
    repository = installation.repository
    where = f"controller:{repository}"
    enablement = ObserverEnablement(installation=installation, source=source)
    with enablement.lock():
        state = enablement.load()
    armed = bool(state.get("armed", False))
    if not armed and not shadow:
        return None, None
    if not armed and state.get("record") is None:
        reading = EnablementReading(
            reading="absent", armed=False, installation=where, detail="no record retained"
        )
    else:
        answer = enablement.execute(path=READ_PATH, payload={"repository": repository})
        reading = answer_reading(answer=answer, installation=where, repository=repository)
    revert = phase in REVERT_PHASES
    return reading, fence_refusal(reading=reading, repository=repository, revert=revert)
