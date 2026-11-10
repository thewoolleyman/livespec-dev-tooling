"""Answer one historical provenance query through the installed canonical reader.

A hosted range gate holds no tenant credential, so it asks here. The query names
the exact attempt; the answer comes only from the host's `read-history` process,
decoded by the shared `_incident_provenance_protocol` decoder, which only this
module uses; the other `read-history` readers decode their replies themselves. A retained arm
is not consulted, so an answer still holds once that arm is bound or invalidated.
The route grants no current effect and no normal proof.
"""

from __future__ import annotations

import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling._incident_provenance_protocol import (  # noqa: E402
    decode_historical_result,
)
from livespec_dev_tooling._incident_provenance_types import IncidentCommitQuery  # noqa: E402
from livespec_dev_tooling.incident_authority_client import (  # noqa: E402
    call_authority,
    report_authority_refusal,
)
from livespec_dev_tooling.incident_controller_installation import (  # noqa: E402
    ControllerInstallation,
)

__all__: list[str] = ["ObserverProvenance"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-zbzls2
_INTEGERS = frozenset({"generation", "pr_number"})
_OBJECT_IDS = frozenset({"base", "head", "commit_sha", "tree_sha"})
_TEXTS = frozenset({"repository", "item_id", "attempt_id", "phase", "operation_id", "owner"})
# A repayment carrier is normal factory work and earns normal evidence instead.
_DEFERRING_PHASE = "repair"


@dataclass(frozen=True, kw_only=True)
class ObserverProvenance:
    """Consult the protected reader without granting mutation or recovery authority."""

    installation: ControllerInstallation

    def execute(self, *, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        _ = path
        settings = self.installation
        if not _valid_query(payload=payload) or payload["phase"] != _DEFERRING_PHASE:
            return _refused(reason="invalid exact provenance query")
        query = IncidentCommitQuery(**payload)
        flags = {
            "repo": str(settings.repo),
            "repository": query.repository,
            "item": query.item_id,
            "attempt": query.attempt_id,
            "phase": query.phase,
            "operation": query.operation_id,
            "generation": str(query.generation),
            "owner": query.owner,
        }
        checked = call_authority(
            command=settings.reader, action="read-history", flags=flags, cwd=settings.repo
        )
        if not is_successful(checked):
            report_authority_refusal(refusal=checked.failure())
            return _refused(reason=checked.failure().code)
        decoded = decode_historical_result(result=checked.unwrap(), query=query)
        if not is_successful(decoded):
            return _refused(reason=decoded.failure().code)
        return {"schema": 1, "status": "provenance", "query": asdict(query)}


def _valid_query(*, payload: dict[str, Any]) -> bool:
    return (
        frozenset(payload) == _INTEGERS | _OBJECT_IDS | _TEXTS
        and all(type(payload[name]) is int and payload[name] > 0 for name in _INTEGERS)
        and all(isinstance(payload[name], str) and payload[name] for name in _TEXTS)
        and all(
            isinstance(payload[name], str) and re.fullmatch(r"[0-9a-f]{40}", payload[name])
            for name in _OBJECT_IDS
        )
    )


def _refused(*, reason: str) -> dict[str, Any]:
    return {"schema": 1, "status": "refused", "reason": reason}
