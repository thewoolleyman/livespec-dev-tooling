"""Run the live incident recovery principal's schema-1 process protocol.

The released-installation manifest names this file as the observer's principal:

    <interpreter> -I <installed incident_recovery_principal_service.py> <controller.json>

It reads ONE bounded request on stdin and writes ONE reply on stdout, with the
same envelope `incident_inverse_service.ProcessInverseForge` sends: integer
`schema: 1`, the exact operation name and `binding.request_sha256` over the
canonical payload. `publish` and `conflict` require the observer's borrowed
repository fence, exactly as the journal's `conflict` does.

THE APP CREDENTIAL IS READ HERE AND NOWHERE ELSE. It is the protected
`recovery-app.json` beside the controller configuration, projected there by the
incident_observer role from the credential wrapper's environment. It is read
lazily, so `lookup` and `conflict` of an action with no open publication still
answer while the App is unprovisioned; every operation that needs the forge
refuses by name (`recovery-app-credential-absent`, and so on) instead.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling._incident_observer_store import (
    REPOSITORY_FENCE_FD_ENV,
    borrow_repository_fence,
    current_repository_fence,
)
from livespec_dev_tooling._incident_recovery_journal_identity import JournalCodec
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_recovery_app import (
    RECOVERY_APP_CREDENTIAL,
    AppRefusal,
    RecoveryAppCredential,
    RecoveryForge,
)
from livespec_dev_tooling.incident_recovery_principal import RecoveryPrincipal

__all__: list[str] = ["PrincipalService"]

_MAX_REQUEST = 2 * 1024 * 1024
_FIRST_INHERITED_DESCRIPTOR = 3
_PAYLOADS: dict[str, frozenset[str]] = {
    "landed": frozenset({"intent"}),
    "authorize": frozenset({"intent", "scope"}),
    "head": frozenset({"repository", "branch"}),
    "lookup": frozenset({"intent"}),
    "publish": frozenset({"request"}),
    "conflict": frozenset({"request"}),
}
_FENCED = frozenset({"publish", "conflict"})
_refused = RecoveryPrincipal.refusal


@dataclass(frozen=True, kw_only=True)
class PrincipalService:
    """Authenticate the envelope, then hand one exact payload to its operation."""

    principal: RecoveryPrincipal

    def execute(self, *, raw: bytes) -> dict[str, Any]:
        try:
            value: Any = JournalCodec.decode(raw=raw, limit=_MAX_REQUEST)
        except (ValueError, TypeError, RecursionError, UnicodeError):
            return _refused(reason="invalid bounded principal packet")
        data = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
        operation, binding = data.get("operation"), data.get("binding")
        payload = {
            key: item for key, item in data.items() if key not in {"schema", "operation", "binding"}
        }
        expected = {
            "request_sha256": hashlib.sha256(JournalCodec.canonical(value=payload)).hexdigest()
        }
        if type(data.get("schema")) is not int or data.get("schema") != 1 or binding != expected:
            return _refused(reason="exact schema and request binding required")
        reply = {"schema": 1, "operation": operation, "binding": expected}
        return {**reply, **self._operation(operation=operation, payload=payload)}

    def _operation(self, *, operation: object, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(operation, str) or operation not in _PAYLOADS:
            return _refused(reason="unknown recovery principal operation")
        if frozenset(payload) != _PAYLOADS[operation]:
            return _refused(reason="exact principal payload required")
        repository = self.principal.installation.repository
        state = self.principal.installation.state
        if (
            operation in _FENCED
            and current_repository_fence(repository=repository, directory=state) is None
        ):
            return _refused(reason="borrowed observer repository fence required")
        handler: Callable[..., dict[str, Any]] = getattr(self.principal, operation)
        try:
            return handler(payload=payload)
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
            return _refused(reason=f"{operation} unavailable: {type(error).__name__}")


def _connector(
    *, installation: ControllerInstallation, config: Path
) -> Callable[[], RecoveryForge | AppRefusal]:
    def connect() -> RecoveryForge | AppRefusal:
        credential = RecoveryAppCredential.load(path=config.parent / RECOVERY_APP_CREDENTIAL)
        if isinstance(credential, AppRefusal):
            return credential
        return RecoveryForge.connect(repository=installation.repository, credential=credential)

    return connect


def _execute_installed(
    *, installation: ControllerInstallation, config: Path, raw: bytes
) -> dict[str, Any]:
    principal = RecoveryPrincipal(
        installation=installation, connect=_connector(installation=installation, config=config)
    )
    application = PrincipalService(principal=principal)
    inherited = os.environ.get(REPOSITORY_FENCE_FD_ENV)
    if inherited is None:
        return application.execute(raw=raw)
    try:
        descriptor = int(inherited)
        if descriptor < _FIRST_INHERITED_DESCRIPTOR or str(descriptor) != inherited:
            return _refused(reason="noncanonical inherited observer repository fence")
        with borrow_repository_fence(
            descriptor=descriptor,
            directory=installation.state,
            repository=installation.repository,
        ):
            return application.execute(raw=raw)
    except (OSError, ValueError, TypeError):
        return _refused(reason="invalid inherited observer repository fence")


def main() -> int:
    """Use a positional protected config in the fixed approved argv."""
    parser = argparse.ArgumentParser(description=__doc__)
    _ = parser.add_argument("config", type=Path)
    args = parser.parse_args()
    installation = ControllerInstallation.load(config=args.config) if sys.flags.isolated else None
    if installation is None:
        _ = sys.stdout.write(
            json.dumps(_refused(reason="protected isolated installation required"))
        )
        return 2
    raw = sys.stdin.buffer.read(_MAX_REQUEST + 1)
    reply = _execute_installed(installation=installation, config=args.config, raw=raw)
    _ = sys.stdout.write(json.dumps(reply, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
