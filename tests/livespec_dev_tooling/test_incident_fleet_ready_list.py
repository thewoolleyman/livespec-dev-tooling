"""The audit's ready list is per consumer: one unproven consumer is left out, not everyone."""

from __future__ import annotations

from dataclasses import replace

from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence, FleetAudit
from livespec_dev_tooling.fleet._context import FleetMember
from livespec_dev_tooling.fleet.contract import Manifest
from livespec_dev_tooling.incident_fleet_audit import SURFACES, audit_incident_fleet


def _receipt(*, repository: str, surface: str) -> CapabilityEvidence:
    return CapabilityEvidence(
        repository=repository,
        surface=surface,
        disposition="implemented",
        manifest_sha256="a" * 64,
        source_path="installed/component.py",
        release_build="v1.0.0",
        serving_build="v1.0.0",
        proof_ref="independent-host-proof:receipt-1",
        owner="controller-owner",
        incident_item="incident-1",
        cumulative_scope="b" * 64,
        normal_factory_proof="factory:original-cumulative-scope",
    )


def test_a_consumer_without_proof_is_left_out_of_the_ready_list_and_others_stay() -> None:
    manifest = Manifest(
        owner="example",
        members=(
            FleetMember(repo="tooling", repo_class="enforcement-suite"),
            FleetMember(repo="other", repo_class="enforcement-suite"),
        ),
        adopters=(),
    )
    result = audit_incident_fleet(
        manifest=manifest,
        manifest_sha256="a" * 64,
        evidence=tuple(_receipt(repository="example/tooling", surface=s) for s in SURFACES),
        verify_manifest=lambda _manifest, _digest: True,
        verify_evidence=lambda _receipt: True,
    )
    assert result.ready_repositories == ("example/tooling",)
    assert result.permits_enablement(repository="example/tooling")
    assert not result.permits_enablement(repository="example/other")
    assert all(finding.startswith("example/other:") for finding in result.findings)
    assert len(result.findings) == len(SURFACES)


def _audit(*, evidence: tuple[CapabilityEvidence, ...]) -> FleetAudit:
    return audit_incident_fleet(
        manifest=Manifest(
            owner="example",
            members=(FleetMember(repo="tooling", repo_class="enforcement-suite"),),
            adopters=(),
        ),
        manifest_sha256="a" * 64,
        evidence=evidence,
        verify_manifest=lambda _manifest, _digest: True,
        verify_evidence=lambda _receipt: True,
    )


def _not_applicable(*, surface: str, serving_build: str = "v1.0.0") -> CapabilityEvidence:
    return replace(
        _receipt(repository="example/tooling", surface=surface),
        disposition="not-applicable",
        reason="this consumer has no such surface (justification bound to the manifest)",
        serving_build=serving_build,
    )


def test_a_consumer_claiming_every_surface_not_applicable_is_never_ready() -> None:
    result = _audit(evidence=tuple(_not_applicable(surface=s) for s in SURFACES))
    assert all(row.disposition == "not-applicable" for row in result.rows)
    assert result.ready_repositories == ()
    assert not result.permits_enablement(repository="example/tooling")


def test_not_applicable_rows_alongside_one_implemented_row_do_not_block_readiness() -> None:
    evidence = (
        _receipt(repository="example/tooling", surface=SURFACES[0]),
        *(_not_applicable(surface=s) for s in SURFACES[1:]),
    )
    result = _audit(evidence=evidence)
    assert result.findings == ()
    assert result.ready_repositories == ("example/tooling",)


def test_a_not_applicable_claim_with_a_stale_serving_version_is_unclassified() -> None:
    evidence = (
        _not_applicable(surface=SURFACES[0], serving_build="v0.0.1"),
        *(_receipt(repository="example/tooling", surface=s) for s in SURFACES[1:]),
    )
    result = _audit(evidence=evidence)
    assert result.rows[0].disposition == "unclassified"
    assert result.ready_repositories == ()


def test_a_not_applicable_claim_bound_to_another_manifest_identity_is_unclassified() -> None:
    evidence = (
        replace(_not_applicable(surface=SURFACES[0]), manifest_sha256="c" * 64),
        *(_receipt(repository="example/tooling", surface=s) for s in SURFACES[1:]),
    )
    result = _audit(evidence=evidence)
    assert result.rows[0].disposition == "unclassified"
    assert result.ready_repositories == ()


def test_a_not_applicable_claim_without_a_justification_is_unclassified() -> None:
    evidence = (
        replace(_not_applicable(surface=SURFACES[0]), reason=""),
        *(_receipt(repository="example/tooling", surface=s) for s in SURFACES[1:]),
    )
    assert _audit(evidence=evidence).rows[0].disposition == "unclassified"
