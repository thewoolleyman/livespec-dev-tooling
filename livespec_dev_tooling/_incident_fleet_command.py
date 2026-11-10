"""The incident fleet audit command: authenticate, read serving versions, report.

The command reads livespec core's committed fleet manifest twice, independently, so the
identity it audits is the identity core's master serves. Claims in the committed
evidence file are never serving evidence: every row's serving build is replaced by what
the injected serving reader reads from the installed consumer or the running independent
controller (an unavailable read leaves it empty), and each claim is checked against a
second, independent read before it counts. It creates no credential, lifecycle record or
activation effect.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Protocol

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402

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
from livespec_dev_tooling.incident_fleet_serving import ServingReader  # noqa: E402

__all__: list[str] = ["FleetReport", "exit_code", "render_report", "run_fleet_audit"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-3wcldx
_NONE = "-"


@dataclass(frozen=True, kw_only=True)
class FleetReport:
    """The audit plus every serving version read for it ("" when the read was unavailable)."""

    audit: FleetAudit
    readings: tuple[tuple[str, str, str], ...]


def _digest(*, text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _unauthenticated(*, digest: str, cause: str) -> FleetReport:
    audit = FleetAudit(
        manifest_sha256=digest,
        rows=(),
        findings=(f"manifest membership or committed identity is unauthenticated: {cause}",),
        ready_repositories=(),
    )
    return FleetReport(audit=audit, readings=())


def _applicable_consumers(*, manifest: Manifest) -> tuple[str, ...]:
    return tuple(f"{manifest.owner}/{m.repo}" for m in manifest.members) + tuple(
        f"{manifest.owner}/{a.repo}"
        for a in manifest.adopters
        if a.profile != ("instruction-only",)
    )


def _guidance_consumers(*, manifest: Manifest) -> tuple[str, ...]:
    return tuple(
        f"{manifest.owner}/{a.repo}"
        for a in manifest.adopters
        if a.profile == ("instruction-only",)
    )


def _confirmed(*, read_manifest: Callable[[], str | None], candidate_digest: str) -> bool:
    """Re-read core's master: the audited identity must be the one it serves now."""
    confirmed = read_manifest()
    return confirmed is not None and _digest(text=confirmed) == candidate_digest


class _Cached(Protocol):
    def __call__(self, *, repository: str, capability: str) -> str: ...


def _once(*, read: ServingReader) -> tuple[_Cached, dict[tuple[str, str], str]]:
    """Read each (repository, capability) once; remember what was read ("" if unavailable)."""
    seen: dict[tuple[str, str], str] = {}

    def cached(*, repository: str, capability: str) -> str:
        key = (repository, capability)
        if key not in seen:
            seen[key] = read(repository=repository, capability=capability) or ""
        return seen[key]

    return cached, seen


def run_fleet_audit(
    *,
    read_manifest: Callable[[], str | None],
    claims: tuple[CapabilityEvidence, ...],
    read_serving: ServingReader,
) -> FleetReport:
    """Audit the installed fleet against core's committed manifest identity."""
    text = read_manifest()
    if text is None:
        return _unauthenticated(digest="", cause="livespec core master read unavailable")
    digest = _digest(text=text)
    parsed = parse_manifest(source=text)
    if isinstance(parsed, Failure):
        return _unauthenticated(digest=digest, cause=parsed.failure().reason)
    manifest = parsed.unwrap()
    served, readings = _once(read=read_serving)
    verified, _ = _once(read=read_serving)

    def capability_of(*, surface: str) -> str:
        return SURFACE_CAPABILITY.get(surface, "")

    audit = audit_incident_fleet(
        manifest=manifest,
        manifest_sha256=digest,
        evidence=tuple(
            replace(
                claim,
                serving_build=served(
                    repository=claim.repository, capability=capability_of(surface=claim.surface)
                ),
            )
            for claim in claims
        ),
        verify_manifest=lambda _candidate, candidate_digest: _confirmed(
            read_manifest=read_manifest, candidate_digest=candidate_digest
        ),
        verify_evidence=lambda row: (
            verified(repository=row.repository, capability=capability_of(surface=row.surface))
            == row.serving_build
        ),
    )
    if not audit.rows:
        return _unauthenticated(
            digest=digest, cause="core's master did not confirm this membership and identity"
        )
    lacking = tuple(
        f"{repository}: lacks serving-version evidence for {', '.join(missing)}"
        for repository in _applicable_consumers(manifest=manifest)
        if (
            missing := [
                c for c in CAPABILITIES if served(repository=repository, capability=c) == ""
            ]
        )
    )
    for repository in _guidance_consumers(manifest=manifest):
        # An instruction-only adopter carries guidance surfaces only; the hooks serving them
        # are read and printed, but its missing read is already named by its unclassified rows.
        _ = served(repository=repository, capability="driver-hooks")
    return FleetReport(
        audit=replace(audit, findings=audit.findings + lacking),
        readings=tuple(sorted((r, c, v) for (r, c), v in readings.items())),
    )


def _row_lines(*, audit: FleetAudit) -> tuple[str, ...]:
    return tuple(
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


def render_report(*, report: FleetReport) -> tuple[str, ...]:
    """Rows, then the serving version read for each consumer and capability, findings, ready."""
    audit = report.audit
    ready = tuple(f"ready\t{repository}" for repository in audit.ready_repositories)
    return (
        f"manifest\t{audit.manifest_sha256 or _NONE}",
        *_row_lines(audit=audit),
        *(f"serving\t{r}\t{c}\t{v or _NONE}" for r, c, v in report.readings),
        *(f"finding\t{finding}" for finding in audit.findings),
        *(ready or (f"ready\t{_NONE}",)),
    )


def exit_code(*, report: FleetReport) -> int:
    """Zero only when every row is classified and no finding stands."""
    return 0 if report.audit.complete else 1
