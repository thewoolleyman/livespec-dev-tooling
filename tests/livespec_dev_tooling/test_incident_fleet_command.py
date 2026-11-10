"""The incident fleet audit command: rows, findings, authentication and the ready list."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace

from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence, FleetAudit
from livespec_dev_tooling.incident_fleet_audit import SURFACES
from livespec_dev_tooling.incident_fleet_command import exit_code, render_report, run_fleet_audit

MANIFEST = (
    '{"owner": "example",'
    ' "fleet": [{"repo": "tooling", "class": "enforcement-suite"},'
    ' {"repo": "other", "class": "enforcement-suite"}],'
    ' "adopters": [{"repo": "notes", "profile": ["instruction-only"], "posture": "none"}]}'
)
DIGEST = hashlib.sha256(MANIFEST.encode()).hexdigest()
GUIDANCE = ("Agent tool and stop guards", "Operator factory routing")


def _claim(*, repository: str, surface: str) -> CapabilityEvidence:
    return CapabilityEvidence(
        repository=repository,
        surface=surface,
        disposition="implemented",
        manifest_sha256=DIGEST,
        source_path="installed/component.py",
        release_build="v1.0.0",
        serving_build="",
        proof_ref="independent-host-proof:receipt-1",
        owner="controller-owner",
        incident_item="" if repository.endswith("notes") else "incident-1",
        cumulative_scope="" if repository.endswith("notes") else "b" * 64,
        normal_factory_proof="" if repository.endswith("notes") else "factory:scope",
    )


def _claims() -> tuple[CapabilityEvidence, ...]:
    return (
        *(
            _claim(repository=repository, surface=surface)
            for repository in ("example/tooling", "example/other")
            for surface in SURFACES
        ),
        *(_claim(repository="example/notes", surface=surface) for surface in GUIDANCE),
    )


def _serving(
    *, unreadable: frozenset[tuple[str, str]] = frozenset()
) -> Callable[[str, str], str | None]:
    return lambda repository, capability: (
        None if (repository, capability) in unreadable else "v1.0.0"
    )


def _run(
    *,
    texts: tuple[str | None, ...] = (MANIFEST, MANIFEST),
    claims: tuple[CapabilityEvidence, ...] | None = None,
    unreadable: frozenset[tuple[str, str]] = frozenset(),
) -> FleetAudit:
    reads = iter(texts)
    return run_fleet_audit(
        read_manifest=lambda: next(reads, None),
        claims=_claims() if claims is None else claims,
        read_serving=_serving(unreadable=unreadable),
    )


def test_prints_one_row_per_surface_and_consumer_with_its_disposition_and_serving_version() -> None:
    audit = _run()
    lines = render_report(audit=audit)
    rows = [line for line in lines if line.startswith("row\t")]
    assert len(rows) == 37 * 3
    assert "row\texample/tooling\tHook installation and wiring\timplemented\tv1.0.0" in rows
    assert "row\texample/notes\tPre-push\tnot-applicable\t-" in rows
    assert "ready\texample/other" in lines
    assert "ready\texample/tooling" in lines
    assert exit_code(audit=audit) == 0


def test_exits_non_zero_naming_the_surface_and_consumer_of_every_unclassified_row() -> None:
    audit = _run(claims=_claims()[:-1])
    lines = render_report(audit=audit)
    assert "row\texample/notes\tOperator factory routing\tunclassified\t-" in lines
    assert any(
        line.startswith("finding\texample/notes: Operator factory routing:") for line in lines
    )
    assert exit_code(audit=audit) != 0
    assert "ready\texample/notes" not in lines


def test_an_unauthenticated_manifest_is_reported_with_zero_ready_repositories() -> None:
    for texts in (
        (None,),
        (MANIFEST, None),
        (MANIFEST, MANIFEST.replace("other", "moved")),
        ("{",),
    ):
        audit = _run(texts=texts)
        lines = render_report(audit=audit)
        assert audit.rows == ()
        assert audit.ready_repositories == ()
        assert any("unauthenticated" in line for line in lines if line.startswith("finding\t"))
        assert not any(line.startswith("ready\t") and line != "ready\t-" for line in lines)
        assert "ready\t-" in lines
        assert exit_code(audit=audit) != 0


def test_a_consumer_lacking_serving_evidence_is_left_out_and_named_with_what_it_lacks() -> None:
    audit = _run(unreadable=frozenset({("example/tooling", "independent-controller")}))
    lines = render_report(audit=audit)
    assert audit.ready_repositories == ("example/other",)
    assert "row\texample/tooling\tFirst-failure observer\tunclassified\t-" in lines
    assert (
        "finding\texample/tooling: lacks serving-version evidence for independent-controller"
        in lines
    )
    assert exit_code(audit=audit) != 0


def test_a_stale_manifest_identity_in_a_claim_is_unclassified() -> None:
    stale = tuple(replace(claim, manifest_sha256="c" * 64) for claim in _claims())
    audit = _run(claims=stale)
    assert audit.rows
    assert audit.ready_repositories == ()
    assert all(row.disposition != "implemented" for row in audit.rows)
