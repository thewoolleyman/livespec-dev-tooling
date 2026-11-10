"""Audit incident surfaces across the canonical manifest, without enabling them."""

from __future__ import annotations

import re
from collections.abc import Callable

from livespec_dev_tooling._incident_fleet_types import (
    CapabilityEvidence,
    FleetAudit,
    SurfaceDisposition,
)
from livespec_dev_tooling.fleet.contract import Manifest

__all__: list[str] = ["SURFACES", "audit_incident_fleet"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-wlrlt2
# These are the ratified 37 distinct launch, authority and evidence surfaces.
# Runtime audit must survive archival of its originating planning thread.
SURFACES: tuple[str, ...] = (
    "Hook installation and wiring",
    "Pre-commit before mode selection",
    "Commit-msg and TDD",
    "Pre-push",
    "Explicit commands and parallel aggregation",
    "Fast-gate timing",
    "Focused test selection",
    "Touched-file coverage",
    "Full coverage producers/consumers",
    "Normal evidence caches",
    "Delegated pre-commit",
    "Delegated push/replay/explicit gates",
    "Gate renderer and pod",
    "Credential/environment boundaries",
    "Agent tool and stop guards",
    "PR mode transport",
    "CI matrix/batch/direct action",
    "CI dependency/aggregate/merge context",
    "Parity/completeness enforcement",
    "Spec enforcement and debt",
    "Workflow-edit authorization",
    "PR factory provenance",
    "Retrospective bypass audit",
    "Operator factory routing",
    "Incident ownership transfer",
    "Branch/PR resolution",
    "Acceptance and completion",
    "Normal master context",
    "First-failure observer",
    "Emergency revert and merge authority",
    "Existing reconciler coordination",
    "Recovery dependency independence",
    "Failed-run retention",
    "Late regression/cleanup",
    "Release and distribution",
    "Generated projects",
    "Closure/proof/archive",
)


_GUIDANCE_SURFACES = frozenset({"Agent tool and stop guards", "Operator factory routing"})
_DISPOSITIONS = frozenset({"implemented", "deliberately-normal", "not-applicable"})


def _consumers(*, manifest: Manifest) -> tuple[tuple[str, bool], ...]:
    return tuple((f"{manifest.owner}/{m.repo}", False) for m in manifest.members) + tuple(
        (f"{manifest.owner}/{a.repo}", a.profile == ("instruction-only",))
        for a in manifest.adopters
    )


def _valid(*, row: CapabilityEvidence, manifest_sha256: str, instruction_only: bool) -> bool:
    if (
        row.manifest_sha256 != manifest_sha256
        or row.disposition not in _DISPOSITIONS
        or not all((row.source_path, row.proof_ref, row.owner))
    ):
        return False
    if row.disposition == "not-applicable":
        return bool(row.reason)
    if not row.release_build or row.release_build != row.serving_build:
        return False
    if row.disposition == "deliberately-normal":
        return bool(row.reason)
    return instruction_only or (
        bool(row.incident_item and row.normal_factory_proof)
        and re.fullmatch(r"[0-9a-f]{64}", row.cumulative_scope) is not None
    )


def _index_evidence(
    *, evidence: tuple[CapabilityEvidence, ...], consumers: tuple[tuple[str, bool], ...]
) -> tuple[dict[tuple[str, str], CapabilityEvidence], tuple[str, ...]]:
    expected = {repository for repository, _instruction_only in consumers}
    indexed: dict[tuple[str, str], CapabilityEvidence] = {}
    findings: list[str] = []
    for row in evidence:
        key = (row.repository, row.surface)
        if row.repository not in expected or row.surface not in SURFACES:
            findings.append(f"foreign evidence: {row.repository}: {row.surface}")
        elif key in indexed:
            findings.append(f"duplicate evidence: {row.repository}: {row.surface}")
        else:
            indexed[key] = row
    return indexed, tuple(findings)


def _consumer_rows(
    *,
    repository: str,
    instruction_only: bool,
    manifest_sha256: str,
    indexed: dict[tuple[str, str], CapabilityEvidence],
    verify_evidence: Callable[[CapabilityEvidence], bool],
) -> tuple[SurfaceDisposition, ...]:
    rows: list[SurfaceDisposition] = []
    for surface in SURFACES:
        evidence = indexed.get((repository, surface))
        inapplicable = instruction_only and surface not in _GUIDANCE_SURFACES
        if inapplicable and evidence is None:
            rows.append(
                SurfaceDisposition(
                    repository=repository,
                    surface=surface,
                    disposition="not-applicable",
                    reason="authenticated instruction-only profile has no runtime obligation",
                )
            )
        elif (
            not inapplicable
            and evidence is not None
            and _valid(
                row=evidence,
                manifest_sha256=manifest_sha256,
                instruction_only=instruction_only,
            )
            and verify_evidence(evidence) is True
        ):
            rows.append(
                SurfaceDisposition(
                    repository=repository,
                    surface=surface,
                    disposition=evidence.disposition,
                    reason=evidence.reason,
                    evidence=evidence,
                )
            )
        else:
            rows.append(
                SurfaceDisposition(
                    repository=repository,
                    surface=surface,
                    disposition="unclassified",
                    reason="missing, contradictory, stale or unauthenticated serving proof",
                    evidence=evidence,
                )
            )
    return tuple(rows)


def audit_incident_fleet(
    *,
    manifest: Manifest,
    manifest_sha256: str,
    evidence: tuple[CapabilityEvidence, ...],
    verify_manifest: Callable[[Manifest, str], bool],
    verify_evidence: Callable[[CapabilityEvidence], bool],
) -> FleetAudit:
    """Expand authenticated current membership, including every declared adopter.

    Verifiers are independently installed readers of committed membership and
    released serving proof, not candidate labels or caller-supplied receipt
    parsers. They must return False when their authoritative read is unavailable.
    This function creates no credentials, lifecycle records or activation effects.
    """
    consumers = _consumers(manifest=manifest)
    names = tuple(repository for repository, _instruction_only in consumers)
    if (
        not manifest.owner
        or not names
        or len(set(names)) != len(names)
        or re.fullmatch(r"[0-9a-f]{64}", manifest_sha256) is None
        or verify_manifest(manifest, manifest_sha256) is not True
    ):
        return FleetAudit(
            manifest_sha256=manifest_sha256,
            rows=(),
            findings=("manifest membership or committed identity is unauthenticated",),
            ready_repositories=(),
        )
    indexed, invalid_evidence = _index_evidence(evidence=evidence, consumers=consumers)
    rows = tuple(
        row
        for repository, instruction_only in consumers
        for row in _consumer_rows(
            repository=repository,
            instruction_only=instruction_only,
            manifest_sha256=manifest_sha256,
            indexed=indexed,
            verify_evidence=verify_evidence,
        )
    )
    findings = invalid_evidence + tuple(
        f"{row.repository}: {row.surface}: {row.reason}"
        for row in rows
        if row.disposition == "unclassified"
    )
    unready = {row.repository for row in rows if row.disposition == "unclassified"}
    ready = (
        ()
        if invalid_evidence
        else tuple(
            repository
            for repository, instruction_only in consumers
            if not instruction_only
            and repository not in unready
            and not any(
                row.repository == repository and row.disposition == "deliberately-normal"
                for row in rows
            )
        )
    )
    return FleetAudit(
        manifest_sha256=manifest_sha256,
        rows=rows,
        findings=findings,
        ready_repositories=ready,
    )
