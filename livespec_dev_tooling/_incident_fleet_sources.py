"""Production sources for the incident fleet audit: the committed claims and core's manifest.

Claims are the operator-authored statement of each consumer and surface (disposition,
owner, proof reference, release build). They are never serving evidence: the file
refuses a `serving_build` key, and the audit overwrites it with a host read (see
`incident_fleet_serving`). The manifest is read fresh from core's default branch.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure  # noqa: E402
from returns.result import Failure, Result, Success  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence  # noqa: E402
from livespec_dev_tooling.fleet._local_context import CommandRunner  # noqa: E402
from livespec_dev_tooling.fleet._manifest_git import git_file_text  # noqa: E402
from livespec_dev_tooling.incident_strict_json import (  # noqa: E402
    IncidentJsonRefusalError,
    strict_json,
)

__all__: list[str] = [
    "CLAIMS_RELATIVE_PATH",
    "COMMITTED_CLAIMS",
    "core_manifest_reader",
    "load_claims",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
CLAIMS_RELATIVE_PATH = Path("config") / "incident-fleet-evidence.json"
# The claims this code was released with, never a file the caller's working directory holds.
COMMITTED_CLAIMS = Path(__file__).resolve().parents[1] / CLAIMS_RELATIVE_PATH
_CORE_REPOSITORY = "livespec"
_MANIFEST_PATH = ".livespec-fleet-manifest.jsonc"
_REQUIRED = (
    "repository",
    "surface",
    "disposition",
    "manifest_sha256",
    "source_path",
    "release_build",
    "proof_ref",
    "owner",
    "incident_item",
    "cumulative_scope",
    "normal_factory_proof",
)


def _claim(*, entry: object) -> CapabilityEvidence | None:
    if not isinstance(entry, dict):
        return None
    record = cast("dict[str, object]", entry)
    reason = record.get("reason", "")
    if (
        set(record) - {*_REQUIRED, "reason"}
        or not all(isinstance(record.get(key), str) for key in _REQUIRED)
        or not isinstance(reason, str)
    ):
        return None
    text = cast("dict[str, str]", record)
    return CapabilityEvidence(
        repository=text["repository"],
        surface=text["surface"],
        disposition=text["disposition"],
        manifest_sha256=text["manifest_sha256"],
        source_path=text["source_path"],
        release_build=text["release_build"],
        serving_build="",
        proof_ref=text["proof_ref"],
        owner=text["owner"],
        incident_item=text["incident_item"],
        cumulative_scope=text["cumulative_scope"],
        normal_factory_proof=text["normal_factory_proof"],
        reason=reason,
    )


def load_claims(*, path: Path) -> Result[tuple[CapabilityEvidence, ...], str]:
    """Read the committed claims; an absent file holds no claims, a malformed one is refused."""
    if not path.is_file():
        return Success(())
    try:
        parsed = cast("object", strict_json(text=path.read_text(encoding="utf-8"), limit=None))
    except (OSError, ValueError, IncidentJsonRefusalError) as unreadable:
        return Failure(f"{path} is unreadable: {unreadable}")
    document = cast("dict[str, object]", parsed) if isinstance(parsed, dict) else {}
    entries = document.get("evidence")
    if document.get("schema") != 1 or not isinstance(entries, list):
        return Failure(f"{path} must be an object with schema 1 and an evidence list")
    claims = tuple(_claim(entry=entry) for entry in cast("list[object]", entries))
    if any(claim is None for claim in claims):
        return Failure(f"{path} holds an entry that is malformed or carries a serving_build")
    return Success(cast("tuple[CapabilityEvidence, ...]", claims))


def core_manifest_reader(*, owner: str, run: CommandRunner) -> Callable[[], str | None]:
    """Each call is a fresh read of livespec core's default branch over the git transport."""

    def read() -> str | None:
        text = git_file_text(run=run, owner=owner, repo=_CORE_REPOSITORY, path=_MANIFEST_PATH)
        return None if isinstance(text, IOFailure) else unsafe_perform_io(text.unwrap())

    return read
