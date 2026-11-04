"""Historical provenance through the registered canonical producer process.

The caller supplies the governed primary repository root and an exact receipt
query. No caller JSON, label, environment flag or mutable local receipt supplies
authority. Historical attribution never selects mode or supplies normal proof.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess, impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

from livespec_dev_tooling._incident_provenance_protocol import decode_historical_reply  # noqa: E402
from livespec_dev_tooling._incident_provenance_types import (  # noqa: E402
    HistoricalIncidentProof,
    IncidentCommitQuery,
    IncidentProvenanceRefusal,
)
from livespec_dev_tooling.flake_retry_filer import registered_plugin_root  # noqa: E402

__all__: list[str] = [
    "HistoricalIncidentProof",
    "IncidentCommitQuery",
    "IncidentProvenanceRefusal",
    "read_historical_incident_commit",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-gvylzw
_READER_TIMEOUT = 30


@impure_safe
def _invoke(*, repo_root: Path, query: IncidentCommitQuery) -> subprocess.CompletedProcess[str]:
    """A registered code path and credential wrapper establish the producer boundary."""
    plugin_root = registered_plugin_root(
        repo_root=repo_root,
        registry=Path.home() / ".claude" / "plugins" / "installed_plugins.json",
    )
    argv = [
        "/usr/local/bin/with-livespec-env.sh",
        "--",
        "python3",
        str(plugin_root / "scripts" / "bin" / "incident_authority.py"),
        "read-history",
        "--repo",
        str(repo_root),
        "--repository",
        query.repository,
        "--item",
        query.item_id,
        "--attempt",
        query.attempt_id,
        "--phase",
        query.phase,
        "--operation",
        query.operation_id,
        "--owner",
        query.owner,
        "--generation",
        str(query.generation),
    ]
    return subprocess.run(  # noqa: S603 — fixed executable and structured argument vector.
        argv,
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=_READER_TIMEOUT,
        check=False,
    )


def read_historical_incident_commit(
    *, repo_root: Path, query: IncidentCommitQuery
) -> IOResult[HistoricalIncidentProof, IncidentProvenanceRefusal]:
    """Read one immutable canonical attribution; never fall back to normal admission."""
    invoked = _invoke(repo_root=repo_root, query=query)
    if not is_successful(invoked):
        failure = unsafe_perform_io(invoked.failure())
        return IOFailure(
            IncidentProvenanceRefusal(
                code="incident-reader-unavailable",
                detail=(
                    f"registered canonical history reader unavailable: "
                    f"{type(failure).__name__}: {failure}"
                ),
            )
        )
    completed = unsafe_perform_io(invoked.unwrap())
    decoded = decode_historical_reply(
        stdout=completed.stdout, returncode=completed.returncode, query=query
    )
    return IOSuccess(decoded.unwrap()) if is_successful(decoded) else IOFailure(decoded.failure())
