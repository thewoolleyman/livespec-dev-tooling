"""Membership and instruction-only boundaries cannot invent incident capability."""

from __future__ import annotations

from dataclasses import replace

import pytest

from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence
from livespec_dev_tooling.fleet._context import Adopter, FleetMember
from livespec_dev_tooling.fleet.contract import Manifest
from livespec_dev_tooling.incident_fleet_audit import audit_incident_fleet


def _instruction_manifest() -> Manifest:
    return Manifest(
        owner="example",
        members=(),
        adopters=(Adopter(repo="notes", profile=("instruction-only",), posture="none"),),
    )


def _guidance(*, surface: str) -> CapabilityEvidence:
    return CapabilityEvidence(
        repository="example/notes",
        surface=surface,
        disposition="implemented",
        manifest_sha256="a" * 64,
        source_path="AGENTS.md",
        release_build="guidance@v1",
        serving_build="guidance@v1",
        proof_ref="independent-guidance-proof",
        owner="notes-owner",
        incident_item="",
        cumulative_scope="",
        normal_factory_proof="",
    )


@pytest.mark.parametrize("case", ["owner", "digest", "truthy-verifier"])
def test_invalid_manifest_never_consults_claimed_evidence(case: str) -> None:
    source = _instruction_manifest()
    checked: list[CapabilityEvidence] = []
    result = audit_incident_fleet(
        manifest=replace(source, owner="") if case == "owner" else source,
        manifest_sha256="invalid" if case == "digest" else "a" * 64,
        evidence=(_guidance(surface="Operator factory routing"),),
        verify_manifest=lambda _manifest, _digest: 1 if case == "truthy-verifier" else True,
        verify_evidence=lambda receipt: checked.append(receipt) is None,
    )
    assert not result.complete
    assert not result.rows
    assert not result.ready_repositories
    assert not checked


def test_instruction_only_membership_still_requires_both_installed_guidance_proofs() -> None:
    result = audit_incident_fleet(
        manifest=_instruction_manifest(),
        manifest_sha256="a" * 64,
        evidence=(),
        verify_manifest=lambda _manifest, _digest: True,
        verify_evidence=lambda _receipt: pytest.fail("no evidence exists to verify"),
    )
    assert len(result.rows) == 37
    assert len(result.findings) == 2
    assert sum(row.disposition == "not-applicable" for row in result.rows) == 35
    assert not result.permits_enablement(repository="example/notes")


def test_instruction_only_guidance_needs_no_imaginary_factory_or_incident() -> None:
    result = audit_incident_fleet(
        manifest=_instruction_manifest(),
        manifest_sha256="a" * 64,
        evidence=tuple(
            _guidance(surface=surface)
            for surface in ("Agent tool and stop guards", "Operator factory routing")
        ),
        verify_manifest=lambda _manifest, _digest: True,
        verify_evidence=lambda _receipt: True,
    )
    assert result.complete
    assert not result.ready_repositories
    assert not result.permits_enablement(repository="example/notes")


def test_runtime_claim_for_instruction_only_profile_is_a_visible_contradiction() -> None:
    result = audit_incident_fleet(
        manifest=_instruction_manifest(),
        manifest_sha256="a" * 64,
        evidence=tuple(
            _guidance(surface=surface)
            for surface in (
                "Agent tool and stop guards",
                "Operator factory routing",
                "CI matrix/batch/direct action",
            )
        ),
        verify_manifest=lambda _manifest, _digest: True,
        verify_evidence=lambda _receipt: True,
    )
    assert not result.complete
    assert len(result.findings) == 1
    assert "CI matrix/batch/direct action" in result.findings[0]
    assert not result.ready_repositories


def test_runtime_adopters_receive_the_full_surface_universe() -> None:
    source = Manifest(
        owner="example",
        members=(FleetMember(repo="tooling", repo_class="enforcement-suite"),),
        adopters=(Adopter(repo="consumer", profile=("baseline",), posture="released"),),
    )
    result = audit_incident_fleet(
        manifest=source,
        manifest_sha256="a" * 64,
        evidence=(),
        verify_manifest=lambda _manifest, _digest: True,
        verify_evidence=lambda _receipt: pytest.fail("no evidence exists to verify"),
    )
    assert len(result.rows) == len(result.findings) == 74
    assert {row.repository for row in result.rows} == {"example/tooling", "example/consumer"}
    assert all(row.disposition == "unclassified" for row in result.rows)
    assert not result.ready_repositories
