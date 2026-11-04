"""Run the protected non-authorizing recovery journal process protocol."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling._incident_inverse_types import InverseConflictRequest
from livespec_dev_tooling._incident_observer_store import (
    REPOSITORY_FENCE_FD_ENV,
    borrow_repository_fence,
    current_repository_fence,
)
from livespec_dev_tooling._incident_recovery_journal_identity import JournalCodec
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_recovery_journal import RecoveryJournal

__all__: list[str] = ["JournalService"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac
_MAX_REQUEST = 2 * 1024 * 1024
_FIRST_INHERITED_DESCRIPTOR = 3


def _refused(*, reason: str) -> dict[str, Any]:
    return {"status": "refused", "reason": reason, "authorizes_current_effects": False}


@dataclass(frozen=True, kw_only=True)
class JournalService:
    """Authenticate the existing packet and fixed installed state before effects."""

    journal: RecoveryJournal

    def execute(self, *, raw: bytes) -> dict[str, Any]:
        try:
            value: Any = JournalCodec.decode(raw=raw, limit=_MAX_REQUEST)
            data = cast("dict[str, Any]", value) if isinstance(value, dict) else {}
            return self._request(data=data)
        except (OSError, ValueError, TypeError, KeyError, RecursionError):
            return _refused(reason="invalid bounded journal packet")

    def _request(self, *, data: dict[str, Any]) -> dict[str, Any]:
        operation = data.get("operation")
        binding = data.get("binding")
        payload = {
            key: value
            for key, value in data.items()
            if key not in {"schema", "operation", "binding"}
        }
        expected = {
            "request_sha256": hashlib.sha256(JournalCodec.canonical(value=payload)).hexdigest()
        }
        if (
            type(data.get("schema")) is not int
            or data.get("schema") != 1
            or not isinstance(operation, str)
            or binding != expected
        ):
            return _refused(reason="exact schema and request binding required")
        reply = {"schema": 1, "operation": operation, "binding": expected}
        if operation not in {"lookup", "conflict"}:
            return {**reply, **_refused(reason="journal operation does not grant forge authority")}
        if (
            operation == "conflict"
            and current_repository_fence(
                repository=self.journal.installation.repository,
                directory=self.journal.installation.state,
            )
            is None
        ):
            return {**reply, **_refused(reason="borrowed observer repository fence required")}
        if set(payload) != ({"intent"} if operation == "lookup" else {"request"}):
            return {**reply, **_refused(reason="exact journal payload required")}
        result = (
            self.journal.lookup(intent=JournalCodec.intent(raw=payload["intent"]))
            if operation == "lookup"
            else self.journal.record_conflict(
                request=cast(
                    "InverseConflictRequest",
                    JournalCodec.request(operation="conflict", raw=payload["request"]),
                )
            )
        )
        return {**reply, **asdict(result)}


def _execute_installed(*, installation: ControllerInstallation, raw: bytes) -> dict[str, Any]:
    application = JournalService(journal=RecoveryJournal(installation=installation))
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
    """Use a positional protected config after -- in the fixed approved argv."""
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
    reply = _execute_installed(installation=installation, raw=raw)
    _ = sys.stdout.write(json.dumps(reply, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
