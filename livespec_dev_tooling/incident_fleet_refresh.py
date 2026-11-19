"""Refresh committed incident-fleet manifest bindings from fresh fleet reads.

The refresh is deliberately narrower than a mechanical manifest re-key.  It
first substitutes the newly read manifest identity in memory, then uses the
same independent serving-evidence read as the fleet audit.  Only claims whose
own row still classifies are written back to the committed claims file.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402

from livespec_dev_tooling._incident_fleet_command import _digest, run_fleet_audit  # noqa: E402
from livespec_dev_tooling._incident_fleet_sources import load_claims  # noqa: E402
from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence  # noqa: E402
from livespec_dev_tooling.incident_fleet_serving import ServingReader  # noqa: E402
from livespec_dev_tooling.incident_strict_json import (  # noqa: E402
    IncidentJsonRefusalError,
    strict_json,
)

__all__: list[str] = ["RefreshResult", "refresh"]


@dataclass(frozen=True, kw_only=True)
class RefreshResult:
    """The mutations safely made and claims that still require a consumer read."""

    rebound: tuple[CapabilityEvidence, ...]
    needs_consumer_reread: tuple[tuple[CapabilityEvidence, str], ...]
    failure: str = ""

    @property
    def ok(self) -> bool:
        return not self.failure and not self.needs_consumer_reread


def _atomic_write(*, path: Path, text: str) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        _ = temporary.write_text(text, encoding="utf-8")
        _ = temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _document(*, path: Path) -> dict[str, object] | None:
    try:
        document = strict_json(text=path.read_text(encoding="utf-8"), limit=None)
    except (OSError, ValueError, IncidentJsonRefusalError):
        return None
    return cast("dict[str, object]", document) if isinstance(document, dict) else None


def _unclassified_reason(*, claim: CapabilityEvidence, rows: dict[tuple[str, str], str]) -> str:
    return rows.get(
        (claim.repository, claim.surface),
        "the refreshed manifest no longer names this consumer and surface",
    )


def refresh(  # noqa: PLR0911
    *,
    claims_path: Path,
    manifest_fixture_path: Path,
    read_manifest: Callable[[], str | None],
    read_serving: ServingReader,
) -> RefreshResult:
    """Regenerate the manifest fixture and rebind only independently proved claims.

    A manifest read is accepted only if the audit's own second read confirms the
    same identity.  This prevents committing a fixture for a manifest that has
    already moved while its consumers were being checked.
    """
    manifest_text = read_manifest()
    if manifest_text is None:
        return RefreshResult(
            rebound=(), needs_consumer_reread=(), failure="core manifest read unavailable"
        )
    claims_result = load_claims(path=claims_path)
    if isinstance(claims_result, Failure):
        return RefreshResult(
            rebound=(),
            needs_consumer_reread=(),
            failure=f"committed claims unreadable: {claims_result.failure()}",
        )
    document = _document(path=claims_path)
    entries_value = document.get("evidence") if document is not None else None
    claims = claims_result.unwrap()
    if not isinstance(entries_value, list):
        return RefreshResult(
            rebound=(),
            needs_consumer_reread=(),
            failure="committed claims changed while being read",
        )
    entries = cast("list[object]", entries_value)
    if len(entries) != len(claims):
        return RefreshResult(
            rebound=(),
            needs_consumer_reread=(),
            failure="committed claims changed while being read",
        )

    identity = _digest(text=manifest_text)
    candidates = tuple(replace(claim, manifest_sha256=identity) for claim in claims)
    report = run_fleet_audit(
        read_manifest=read_manifest, claims=candidates, read_serving=read_serving
    )
    if not report.audit.rows or report.audit.manifest_sha256 != identity:
        return RefreshResult(
            rebound=(),
            needs_consumer_reread=(),
            failure="core manifest changed or could not be authenticated during refresh",
        )

    reasons = {
        (row.repository, row.surface): row.reason
        for row in report.audit.rows
        if row.disposition == "unclassified"
    }
    row_keys = {(row.repository, row.surface) for row in report.audit.rows}
    rebound: list[CapabilityEvidence] = []
    rereads: list[tuple[CapabilityEvidence, str]] = []
    for claim, raw_entry in zip(claims, entries, strict=True):
        if not isinstance(raw_entry, dict):
            return RefreshResult(
                rebound=(),
                needs_consumer_reread=(),
                failure="committed claims changed while being read",
            )
        entry = cast("dict[str, object]", raw_entry)
        reason = _unclassified_reason(claim=claim, rows=reasons)
        if (claim.repository, claim.surface) in reasons or (
            claim.repository,
            claim.surface,
        ) not in row_keys:
            rereads.append((claim, reason))
            continue
        entry["manifest_sha256"] = identity
        rebound.append(replace(claim, manifest_sha256=identity))

    # The fixture records the exact committed core text that supplied the new
    # identity.  It is updated even when some claims need a later consumer read.
    _atomic_write(path=manifest_fixture_path, text=manifest_text)
    if rebound:
        _atomic_write(path=claims_path, text=json.dumps(document, indent=2) + "\n")
    return RefreshResult(rebound=tuple(rebound), needs_consumer_reread=tuple(rereads))
