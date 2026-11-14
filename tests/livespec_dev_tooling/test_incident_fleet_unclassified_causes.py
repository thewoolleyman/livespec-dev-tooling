"""Every unclassified row of the fleet audit names the specific evidence it is missing.

A claimless row, a claim bound to another manifest, a stale release build, an unreadable
serving version and an unconfirmed re-read are different gaps with different remedies, so
the command's findings name each one rather than one fixed sentence for all
(livespec-dev-tooling-v46q5g).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import replace

import pytest

from livespec_dev_tooling._incident_fleet_command import (
    exit_code,
    render_report,
    run_fleet_audit,
)
from livespec_dev_tooling._incident_fleet_types import CapabilityEvidence
from livespec_dev_tooling.incident_fleet_serving import ServingReader

_MANIFEST = (
    '{"owner": "example",'
    ' "fleet": [{"repo": "tooling", "class": "enforcement-suite"}],'
    ' "adopters": [{"repo": "notes", "profile": ["instruction-only"], "posture": "none"}]}'
)
_DIGEST = hashlib.sha256(_MANIFEST.encode()).hexdigest()
_CLAIM = CapabilityEvidence(
    repository="example/tooling",
    surface="Pre-push",
    disposition="implemented",
    manifest_sha256=_DIGEST,
    source_path="installed/component.py",
    release_build="v1.0.0",
    serving_build="",
    proof_ref="independent-host-proof:receipt-1",
    owner="controller-owner",
    incident_item="incident-1",
    cumulative_scope="b" * 64,
    normal_factory_proof="factory:scope",
)


def _steady(*, repository: str, capability: str) -> str | None:
    del repository, capability
    return "v1.0.0"


def _unreadable(*, repository: str, capability: str) -> str | None:
    del repository, capability
    return None


def _moving() -> ServingReader:
    """The first read of each capability sees v1.0.0; the independent re-read sees v2.0.0."""
    seen: set[tuple[str, str]] = set()

    def read(*, repository: str, capability: str) -> str | None:
        key = (repository, capability)
        if key in seen:
            return "v2.0.0"
        seen.add(key)
        return "v1.0.0"

    return read


_CASES: dict[str, tuple[tuple[CapabilityEvidence, ...], Callable[[], ServingReader], str, str]] = {
    "no-claim": (
        (),
        lambda: _steady,
        "example/tooling: Pre-push",
        "no committed claim for this consumer and surface",
    ),
    "instruction-only-runtime-claim": (
        (replace(_CLAIM, repository="example/notes"),),
        lambda: _steady,
        "example/notes: Pre-push",
        "claim for a runtime surface the instruction-only profile does not carry",
    ),
    "other-manifest": (
        (replace(_CLAIM, manifest_sha256="c" * 64),),
        lambda: _steady,
        "example/tooling: Pre-push",
        f"claim is bound to manifest {'c' * 64}, not the committed identity {_DIGEST}",
    ),
    "unknown-disposition": (
        (replace(_CLAIM, disposition="maybe"),),
        lambda: _steady,
        "example/tooling: Pre-push",
        "claim names no known disposition: maybe",
    ),
    "no-owner": (
        (replace(_CLAIM, owner=""),),
        lambda: _steady,
        "example/tooling: Pre-push",
        "claim lacks a source path, proof reference, owner or release build",
    ),
    "no-reason": (
        (replace(_CLAIM, disposition="not-applicable"),),
        lambda: _steady,
        "example/tooling: Pre-push",
        "claim gives no reason for not-applicable",
    ),
    "implemented-without-incident": (
        (replace(_CLAIM, incident_item=""),),
        lambda: _steady,
        "example/tooling: Pre-push",
        "implemented claim lacks its incident item, normal factory proof or scope digest",
    ),
    "serving-unreadable": (
        (_CLAIM,),
        lambda: _unreadable,
        "example/tooling: Pre-push",
        "serving version unreadable: no installed serving build was read (unverified)",
    ),
    "stale-release-build": (
        (replace(_CLAIM, release_build="v0.0.1"),),
        lambda: _steady,
        "example/tooling: Pre-push",
        "claim release build v0.0.1 is not the serving version read v1.0.0",
    ),
    "unconfirmed-re-read": (
        (_CLAIM,),
        _moving,
        "example/tooling: Pre-push",
        "serving version v1.0.0 not confirmed by an independent re-read",
    ),
}


@pytest.mark.parametrize("case", sorted(_CASES))
def test_an_unclassified_row_names_its_specific_missing_evidence(case: str) -> None:
    claims, serving, row, cause = _CASES[case]
    reads = iter((_MANIFEST, _MANIFEST))
    report = run_fleet_audit(
        read_manifest=lambda: next(reads, None),
        claims=claims,
        read_serving=serving(),
    )
    repository, surface = row.split(": ")
    lines = render_report(report=report)
    assert any(line.startswith(f"row\t{repository}\t{surface}\tunclassified\t") for line in lines)
    assert f"finding\t{row}: {cause}" in lines
    assert exit_code(report=report) != 0
