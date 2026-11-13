"""The enablement readers at the dev-host hooks and on the controller host itself.

The hooks ask the installation this library's committed configuration names for the
repository (`INSTALLATION_PORTS`, kept equal to the observer role's inventory by test)
through its read-only query route with the projected query credential, and compare the
identity the controller confirmed against their own read of core's default branch. The
controller reads its own record directly. The incident CI entrance reads the same query
route through `CiAuthorityBoundary.enablement`.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping

from livespec_dev_tooling._incident_enablement_reading import (
    REVERT_PHASES,
    EnablementReader,
    EnablementReading,
    answer_reading,
    fence_refusal,
)
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_enablement import (
    INSTALLATION_PORTS,
    READ_PATH,
    EnablementPost,
    IdentitySource,
    ObserverEnablement,
    _post,
    production_identity_source,
)

__all__: list[str] = ["controller_fence", "installation_reader"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-exdkra
_QUERY_TOKEN_ENV = "LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN"  # noqa: S105 - a variable name


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
        own = own_identity or production_identity_source().read_identity
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
