"""Refresh committed incident-fleet manifest bindings from fresh fleet reads.

The refresh is deliberately narrower than a mechanical manifest re-key.  It
first substitutes the newly read manifest identity in memory, then uses the
same independent serving-evidence read as the fleet audit.  Only claims whose
own row still classifies are written back to the committed claims file.
"""

from __future__ import annotations

import copy
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
from livespec_dev_tooling._incident_fleet_sources import _claim, load_claims  # noqa: E402
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


_DUPLICATE_REASON = (
    "another claim already names this consumer and surface, so this claim's own evidence "
    "was never independently read"
)


def _always_unchanged() -> bool:
    return True


def _atomic_write(
    *, path: Path, text: str, unchanged: Callable[[], bool] = _always_unchanged
) -> bool:
    """Replace `path` with `text` unless `unchanged` fails right before the replace."""
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        _ = temporary.write_text(text, encoding="utf-8")
        if not unchanged():
            return False
        _ = temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return True


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


def _partition(
    *,
    claims: tuple[CapabilityEvidence, ...],
    entries: list[dict[str, object]],
    identity: str,
    reasons: dict[tuple[str, str], str],
    row_keys: set[tuple[str, str]],
) -> tuple[list[CapabilityEvidence], list[tuple[CapabilityEvidence, str]]]:
    """Rebind each independently proved claim's entry; list every other claim for a re-read."""
    rebound: list[CapabilityEvidence] = []
    rereads: list[tuple[CapabilityEvidence, str]] = []
    # The audit judges one row per (repository, surface), so only the first
    # claim for a key has had its own evidence read; later duplicates have not.
    judged: set[tuple[str, str]] = set()
    for claim, entry in zip(claims, entries, strict=True):
        key = (claim.repository, claim.surface)
        if key in judged:
            rereads.append((claim, _DUPLICATE_REASON))
            continue
        judged.add(key)
        if key in reasons or key not in row_keys:
            rereads.append((claim, _unclassified_reason(claim=claim, rows=reasons)))
            continue
        entry["manifest_sha256"] = identity
        rebound.append(replace(claim, manifest_sha256=identity))
    return rebound, rereads


def _failed(*, reason: str) -> RefreshResult:
    return RefreshResult(rebound=(), needs_consumer_reread=(), failure=reason)


def _claim_entries(
    *, document: dict[str, object] | None, claims: tuple[CapabilityEvidence, ...]
) -> list[dict[str, object]] | None:
    """Return the raw claim entries only when each one is exactly its parsed claim."""
    entries = document.get("evidence") if document is not None else None
    if not isinstance(entries, list):
        return None
    raw = cast("list[object]", entries)
    if len(raw) != len(claims) or not all(isinstance(entry, dict) for entry in raw):
        return None
    # A replacement of the same length would still pair, so each raw entry must
    # parse to exactly the claim the audit is about to read evidence for.
    if any(_claim(entry=entry) != claim for entry, claim in zip(raw, claims, strict=True)):
        return None
    return cast("list[dict[str, object]]", raw)


def _write(
    *,
    claims_path: Path,
    manifest_fixture_path: Path,
    manifest_text: str,
    document: dict[str, object] | None,
    audited: dict[str, object] | None,
    result: RefreshResult,
) -> RefreshResult:
    """Write the rebound claims, then the fixture, each only if nothing else moved."""
    # Every claim field outside the rebound manifest bindings must still be the
    # audited snapshot, or this write would revert a replacement nothing audited.
    # The claims replace goes first and re-checks the snapshot immediately before
    # it, so no other write can land between that check and the replace.
    if result.rebound and not _atomic_write(
        path=claims_path,
        text=json.dumps(document, indent=2) + "\n",
        unchanged=lambda: _document(path=claims_path) == audited,
    ):
        return _failed(reason="committed claims changed during refresh")

    # The fixture records the exact committed core text that supplied the new
    # identity.  It is updated even when some claims need a later consumer read.
    _ = _atomic_write(path=manifest_fixture_path, text=manifest_text)
    return result


def refresh(
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
        return _failed(reason="core manifest read unavailable")
    claims_result = load_claims(path=claims_path)
    if isinstance(claims_result, Failure):
        return _failed(reason=f"committed claims unreadable: {claims_result.failure()}")
    document = _document(path=claims_path)
    claims = claims_result.unwrap()
    entries = _claim_entries(document=document, claims=claims)
    if entries is None:
        return _failed(reason="committed claims changed while being read")
    audited = copy.deepcopy(document)

    identity = _digest(text=manifest_text)
    candidates = tuple(replace(claim, manifest_sha256=identity) for claim in claims)
    report = run_fleet_audit(
        read_manifest=read_manifest, claims=candidates, read_serving=read_serving
    )
    if not report.audit.rows or report.audit.manifest_sha256 != identity:
        return _failed(reason="core manifest changed or could not be authenticated during refresh")

    reasons = {
        (row.repository, row.surface): row.reason
        for row in report.audit.rows
        if row.disposition == "unclassified"
    }
    row_keys = {(row.repository, row.surface) for row in report.audit.rows}
    rebound, rereads = _partition(
        claims=claims,
        entries=entries,
        identity=identity,
        reasons=reasons,
        row_keys=row_keys,
    )

    return _write(
        claims_path=claims_path,
        manifest_fixture_path=manifest_fixture_path,
        manifest_text=manifest_text,
        document=document,
        audited=audited,
        result=RefreshResult(rebound=tuple(rebound), needs_consumer_reread=tuple(rereads)),
    )
