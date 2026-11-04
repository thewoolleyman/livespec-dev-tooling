"""Fleet-wide admission fails closed on missing, stale or unauthenticated proof."""

from __future__ import annotations

from dataclasses import replace

import pytest

from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence, FleetAudit
from livespec_dev_tooling.fleet._context import Adopter, FleetMember
from livespec_dev_tooling.fleet.contract import Manifest
from livespec_dev_tooling.incident_fleet_audit import SURFACES, audit_incident_fleet


def manifest(*, instructions: bool = False) -> Manifest:
    return Manifest(
        owner="example",
        members=(FleetMember(repo="tooling", repo_class="enforcement-suite"),),
        adopters=(Adopter(repo="notes", profile=("instruction-only",), posture="none"),)
        if instructions
        else (),
    )


def receipt(*, repository: str = "example/tooling", surface: str) -> CapabilityEvidence:
    return CapabilityEvidence(
        repository=repository,
        surface=surface,
        disposition="implemented",
        manifest_sha256="a" * 64,
        source_path="installed/component.py",
        release_build="tooling@v1.0.0",
        serving_build="tooling@v1.0.0",
        proof_ref="independent-host-proof:receipt-1",
        owner="controller-owner",
        incident_item="incident-1",
        cumulative_scope="b" * 64,
        normal_factory_proof="factory:original-cumulative-scope",
    )


def all_receipts() -> tuple[CapabilityEvidence, ...]:
    return tuple(receipt(surface=surface) for surface in SURFACES)


def audit(*, receipts: tuple[CapabilityEvidence, ...]) -> FleetAudit:
    return audit_incident_fleet(
        manifest=manifest(),
        manifest_sha256="a" * 64,
        evidence=receipts,
        verify_manifest=lambda _manifest, _digest: True,
        verify_evidence=lambda _receipt: True,
    )


def test_every_published_surface_is_unclassified_without_serving_proof() -> None:
    result = audit(receipts=())
    assert len(result.rows) == 37
    assert {row.surface for row in result.rows} == set(SURFACES)
    assert all(row.disposition == "unclassified" for row in result.rows)
    assert len(result.findings) == 37
    assert not result.permits_enablement(repository="example/tooling")


def test_exact_independently_verified_complete_scope_is_required_for_enablement() -> None:
    result = audit(receipts=all_receipts())
    assert result.complete
    assert result.permits_enablement(repository="example/tooling")
    assert not result.permits_enablement(repository="example/foreign")
    assert all(row.evidence is not None for row in result.rows)


@pytest.mark.parametrize(
    "change",
    [
        {"manifest_sha256": "c" * 64},
        {"serving_build": "tooling@v0.9.0"},
        {"release_build": ""},
        {"source_path": ""},
        {"proof_ref": ""},
        {"owner": ""},
        {"incident_item": ""},
        {"cumulative_scope": ""},
        {"normal_factory_proof": ""},
        {"disposition": "green"},
    ],
)
def test_source_only_or_stale_claims_cannot_enable(change: dict[str, str]) -> None:
    original = all_receipts()
    result = audit(receipts=(replace(original[0], **change), *original[1:]))
    assert not result.complete
    assert not result.permits_enablement(repository="example/tooling")
    assert result.findings


def test_callbacks_must_return_actual_true_and_claims_alone_are_insufficient() -> None:
    for verifier in (lambda _receipt: False, lambda _receipt: 1):
        result = audit_incident_fleet(
            manifest=manifest(),
            manifest_sha256="a" * 64,
            evidence=all_receipts(),
            verify_manifest=lambda _manifest, _digest: True,
            verify_evidence=verifier,
        )
        assert not result.complete
        assert not result.ready_repositories


def test_normal_disposition_is_visible_but_never_permission_to_enable() -> None:
    original = all_receipts()
    normal = replace(
        original[0], disposition="deliberately-normal", reason="unsupported alternate store"
    )
    result = audit(receipts=(normal, *original[1:]))
    assert result.complete
    assert result.rows[0].disposition == "deliberately-normal"
    assert not result.permits_enablement(repository="example/tooling")
    assert not audit(receipts=(replace(normal, reason=""), *original[1:])).complete


def test_explicit_inapplicability_requires_verified_reason() -> None:
    original = all_receipts()
    not_applicable = replace(
        original[0], disposition="not-applicable", reason="no such launcher in this consumer"
    )
    assert audit(receipts=(not_applicable, *original[1:])).complete
    assert not audit(receipts=(replace(not_applicable, reason=""), *original[1:])).complete


def test_instruction_only_adopters_owe_guidance_without_invented_tenants_or_ci() -> None:
    instruction_surfaces = ("Agent tool and stop guards", "Operator factory routing")
    receipts = (
        *all_receipts(),
        *(
            replace(
                receipt(repository="example/notes", surface=surface),
                cumulative_scope="",
                normal_factory_proof="",
            )
            for surface in instruction_surfaces
        ),
    )
    result = audit_incident_fleet(
        manifest=manifest(instructions=True),
        manifest_sha256="a" * 64,
        evidence=receipts,
        verify_manifest=lambda _manifest, _digest: True,
        verify_evidence=lambda _receipt: True,
    )
    assert result.complete
    assert len(result.rows) == 74
    rows = tuple(row for row in result.rows if row.repository == "example/notes")
    assert sum(row.disposition == "implemented" for row in rows) == 2
    assert sum(row.disposition == "not-applicable" for row in rows) == 35
    assert not result.permits_enablement(repository="example/notes")


def test_foreign_duplicate_and_unknown_surface_receipts_are_refused() -> None:
    original = all_receipts()
    for extra in (
        original[0],
        replace(original[0], repository="example/foreign"),
        replace(original[0], surface="omitted-custom-workflow"),
    ):
        result = audit(receipts=(*original, extra))
        assert not result.complete
        assert not result.ready_repositories


def test_manifest_authentication_empty_membership_and_cross_list_duplicates_refuse() -> None:
    for source, verifier in (
        (manifest(), lambda _manifest, _digest: False),
        (Manifest(owner="example", members=(), adopters=()), lambda _manifest, _digest: True),
        (
            replace(
                manifest(),
                adopters=(Adopter(repo="tooling", profile=("baseline",), posture="pinned"),),
            ),
            lambda _manifest, _digest: True,
        ),
    ):
        result = audit_incident_fleet(
            manifest=source,
            manifest_sha256="a" * 64,
            evidence=all_receipts(),
            verify_manifest=verifier,
            verify_evidence=lambda _receipt: True,
        )
        assert not result.complete
        assert not result.permits_enablement(repository="example/tooling")
