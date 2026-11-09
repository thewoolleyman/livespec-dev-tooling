"""Historical provenance through the registered canonical producer process.

The caller supplies the governed primary repository root and an exact receipt
query. No caller JSON, label, environment flag or mutable local receipt supplies
authority. Historical attribution never selects mode or supplies normal proof.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess, impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

from livespec_dev_tooling._incident_provenance_protocol import (  # noqa: E402
    decode_historical_result,
)
from livespec_dev_tooling._incident_provenance_types import (  # noqa: E402
    HistoricalIncidentProof,
    IncidentCommitQuery,
    IncidentProvenanceRefusal,
)
from livespec_dev_tooling.flake_retry_filer import registered_plugin_root  # noqa: E402
from livespec_dev_tooling.incident_authority_client import (  # noqa: E402
    call_authority,
    registered_authority_command,
)

__all__: list[str] = [
    "HistoricalIncidentProof",
    "IncidentCommitQuery",
    "IncidentProvenanceRefusal",
    "read_historical_incident_commit",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gvylzw


@impure_safe
def _command(*, repo_root: Path) -> list[str]:
    """A registered code path and credential wrapper establish the producer boundary."""
    plugin_root = registered_plugin_root(
        repo_root=repo_root,
        registry=Path.home() / ".claude" / "plugins" / "installed_plugins.json",
    )
    return registered_authority_command(plugin_root=plugin_root)


def read_historical_incident_commit(
    *, repo_root: Path, query: IncidentCommitQuery
) -> IOResult[HistoricalIncidentProof, IncidentProvenanceRefusal]:
    """Read one immutable canonical attribution; never fall back to normal admission."""
    command = _command(repo_root=repo_root)
    if not is_successful(command):
        failure = unsafe_perform_io(command.failure())
        return IOFailure(
            IncidentProvenanceRefusal(
                code="incident-authority-unavailable",
                detail=(
                    f"registered canonical history reader unavailable: "
                    f"{type(failure).__name__}: {failure}"
                ),
            )
        )
    checked = call_authority(
        command=unsafe_perform_io(command.unwrap()),
        action="read-history",
        flags={
            "repo": repo_root,
            "repository": query.repository,
            "item": query.item_id,
            "attempt": query.attempt_id,
            "phase": query.phase,
            "operation": query.operation_id,
            "owner": query.owner,
            "generation": query.generation,
        },
        cwd=repo_root,
    )
    if not is_successful(checked):
        refusal = checked.failure()
        return IOFailure(IncidentProvenanceRefusal(code=refusal.code, detail=refusal.detail))
    decoded = decode_historical_result(result=checked.unwrap(), query=query)
    return IOSuccess(decoded.unwrap()) if is_successful(decoded) else IOFailure(decoded.failure())
