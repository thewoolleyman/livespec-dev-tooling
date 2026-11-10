"""The audit's ready list is per consumer: one unproven consumer is left out, not everyone."""

from __future__ import annotations

from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence
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
