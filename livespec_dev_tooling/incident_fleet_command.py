"""The incident fleet audit command: authenticate, read serving versions, report.

The command reads livespec core's committed fleet manifest twice, independently,
so the identity it audits is the identity core's master serves. Claims in the
committed evidence file are never serving evidence: every row's serving build is
overwritten by what the injected serving reader reads from the installed consumer
or the running independent controller, and an unavailable read leaves it empty.
It creates no credential, lifecycle record or activation effect.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure, Success  # noqa: E402

from livespec_dev_tooling._incident_fleet_capabilities import (  # noqa: E402
    CAPABILITIES,
    SURFACE_CAPABILITY,
)
from livespec_dev_tooling._incident_fleet_types import (  # noqa: E402
    CapabilityEvidence,
    FleetAudit,
)
from livespec_dev_tooling.fleet.contract import Manifest, parse_manifest  # noqa: E402
from livespec_dev_tooling.incident_fleet_audit import audit_incident_fleet  # noqa: E402

__all__: list[str] = ["exit_code", "render_report", "run_fleet_audit"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
_NONE = "-"


def _digest(*, text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _unauthenticated(*, digest: str, cause: str) -> FleetAudit:
    return FleetAudit(
        manifest_sha256=digest,
        rows=(),
        findings=(f"manifest membership or committed identity is unauthenticated: {cause}",),
        ready_repositories=(),
    )


def _applicable_consumers(*, manifest: Manifest) -> tuple[str, ...]:
    return tuple(f"{manifest.owner}/{m.repo}" for m in manifest.members) + tuple(
        f"{manifest.owner}/{a.repo}"
        for a in manifest.adopters
        if a.profile != ("instruction-only",)
    )


def _confirmed(
    *, read_manifest: Callable[[], str | None], candidate: Manifest, candidate_digest: str
) -> bool:
    """Re-read core's master: the audited identity must be the one it serves now."""
    confirmed = read_manifest()
    return (
        confirmed is not None
        and _digest(text=confirmed) == candidate_digest
        and parse_manifest(source=confirmed) == Success(candidate)
    )


def _served(*, read_serving: Callable[[str, str], str | None], row: CapabilityEvidence) -> str:
    capability = SURFACE_CAPABILITY.get(row.surface, "")
    return read_serving(row.repository, capability) or ""


def run_fleet_audit(
    *,
    read_manifest: Callable[[], str | None],
    claims: tuple[CapabilityEvidence, ...],
    read_serving: Callable[[str, str], str | None],
) -> FleetAudit:
    """Audit the installed fleet against core's committed manifest identity."""
    text = read_manifest()
    if text is None:
        return _unauthenticated(digest="", cause="livespec core master read unavailable")
    digest = _digest(text=text)
    parsed = parse_manifest(source=text)
    if isinstance(parsed, Failure):
        return _unauthenticated(digest=digest, cause=parsed.failure().reason)
    manifest = parsed.unwrap()

    audit = audit_incident_fleet(
        manifest=manifest,
        manifest_sha256=digest,
        evidence=tuple(
            replace(claim, serving_build=_served(read_serving=read_serving, row=claim))
            for claim in claims
        ),
        verify_manifest=lambda candidate, candidate_digest: _confirmed(
            read_manifest=read_manifest, candidate=candidate, candidate_digest=candidate_digest
        ),
        verify_evidence=lambda row: row.serving_build != ""
        and _served(read_serving=read_serving, row=row) == row.serving_build,
    )
    if not audit.rows:
        return audit
    lacking = {
        repository: tuple(c for c in CAPABILITIES if read_serving(repository, c) is None)
        for repository in _applicable_consumers(manifest=manifest)
    }
    missing = {repository: caps for repository, caps in lacking.items() if caps}
    return replace(
        audit,
        findings=audit.findings
        + tuple(
            f"{repository}: lacks serving-version evidence for {', '.join(caps)}"
            for repository, caps in missing.items()
        ),
        ready_repositories=tuple(r for r in audit.ready_repositories if r not in missing),
    )


def render_report(*, audit: FleetAudit) -> tuple[str, ...]:
    """One tab-separated line per row, finding and ready repository."""
    rows = tuple(
        "\t".join(
            (
                "row",
                row.repository,
                row.surface,
                row.disposition,
                (row.evidence.serving_build if row.evidence else "") or _NONE,
            )
        )
        for row in audit.rows
    )
    ready = tuple(f"ready\t{repository}" for repository in audit.ready_repositories)
    return (
        f"manifest\t{audit.manifest_sha256 or _NONE}",
        *rows,
        *(f"finding\t{finding}" for finding in audit.findings),
        *(ready or (f"ready\t{_NONE}",)),
    )


def exit_code(*, audit: FleetAudit) -> int:
    """Zero only when every row is classified and no finding stands."""
    return 0 if audit.complete else 1
