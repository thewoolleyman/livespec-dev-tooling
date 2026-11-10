"""Evidence values for the installed fleet's incident capability audit."""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = ["CapabilityEvidence", "FleetAudit", "SurfaceDisposition"]


@dataclass(frozen=True, kw_only=True)
class CapabilityEvidence:
    """One independently verified receipt, bound to the manifest and serving build.

    These fields are claims until the audit's independent evidence reader
    authenticates them. A release name or a successful source test is not
    evidence of an installed controller or consumer.
    """

    repository: str
    surface: str
    disposition: str
    manifest_sha256: str
    source_path: str
    release_build: str
    serving_build: str
    proof_ref: str
    owner: str
    incident_item: str
    cumulative_scope: str
    normal_factory_proof: str
    reason: str = ""


@dataclass(frozen=True, kw_only=True)
class SurfaceDisposition:
    repository: str
    surface: str
    disposition: str
    reason: str
    evidence: CapabilityEvidence | None = None


@dataclass(frozen=True, kw_only=True)
class FleetAudit:
    """A report, never an instruction to enable or mutate a consumer."""

    manifest_sha256: str
    rows: tuple[SurfaceDisposition, ...]
    findings: tuple[str, ...]
    ready_repositories: tuple[str, ...]

    @property
    def complete(self) -> bool:
        """All consumers and surfaces are classified by authenticated evidence."""
        return bool(self.rows) and not self.findings

    def permits_enablement(self, *, repository: str) -> bool:
        """Only a ready consumer is enabled; a normal or instruction-only one never is."""
        return repository in self.ready_repositories
