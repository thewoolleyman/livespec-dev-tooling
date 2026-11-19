"""The manifest refresher preserves the audit's independent evidence requirement."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from returns.result import Success

from livespec_dev_tooling import incident_fleet_refresh
from livespec_dev_tooling._incident_fleet_capabilities import SURFACE_CAPABILITY
from livespec_dev_tooling._incident_fleet_sources import load_claims
from livespec_dev_tooling.incident_fleet_refresh import refresh

_FIXTURES = Path(__file__).parent / "fixtures" / "incident_fleet"
_CLAIMS = _FIXTURES / "claims-wellformed.json"
_MANIFEST = _FIXTURES / "core-fleet-manifest.jsonc"


def _prepared(tmp_path: Path) -> tuple[Path, Path, str]:
    claims = tmp_path / "claims.json"
    claims.write_text(_CLAIMS.read_text(encoding="utf-8"), encoding="utf-8")
    refreshed = _MANIFEST.read_text(encoding="utf-8") + "\n"
    fixture = tmp_path / "core-fleet-manifest.jsonc"
    fixture.write_text("old fixture\n", encoding="utf-8")
    return claims, fixture, refreshed


def _serving(*, claims_path: Path, unreadable_capability: str = ""):
    loaded = load_claims(path=claims_path)
    assert isinstance(loaded, Success)
    builds = {
        (claim.repository, SURFACE_CAPABILITY[claim.surface]): claim.release_build
        for claim in loaded.unwrap()
    }

    def read(*, repository: str, capability: str) -> str | None:
        return None if capability == unreadable_capability else builds.get((repository, capability))

    return read


def test_refresh_rebinds_only_manifest_bindings_after_independent_evidence_reads(
    tmp_path: Path,
) -> None:
    claims, fixture, manifest = _prepared(tmp_path)
    before = json.loads(claims.read_text(encoding="utf-8"))

    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: manifest,
        read_serving=_serving(claims_path=claims),
    )

    identity = hashlib.sha256(manifest.encode()).hexdigest()
    assert result.ok
    assert len(result.rebound) == len(before["evidence"])
    assert result.needs_consumer_reread == ()
    assert fixture.read_text(encoding="utf-8") == manifest
    after = json.loads(claims.read_text(encoding="utf-8"))
    for old, new in zip(before["evidence"], after["evidence"], strict=True):
        assert {key: value for key, value in new.items() if key != "manifest_sha256"} == {
            key: value for key, value in old.items() if key != "manifest_sha256"
        }
        assert new["manifest_sha256"] == identity


def test_refresh_leaves_an_unproved_claim_bound_to_its_existing_manifest(tmp_path: Path) -> None:
    claims, fixture, manifest = _prepared(tmp_path)
    before = json.loads(claims.read_text(encoding="utf-8"))
    capability = SURFACE_CAPABILITY[before["evidence"][0]["surface"]]

    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: manifest,
        read_serving=_serving(claims_path=claims, unreadable_capability=capability),
    )

    assert not result.ok
    assert [
        (claim.repository, claim.surface) for claim, _reason in result.needs_consumer_reread
    ] == [
        (claim["repository"], claim["surface"])
        for claim in before["evidence"]
        if SURFACE_CAPABILITY[claim["surface"]] == capability
    ]
    after = json.loads(claims.read_text(encoding="utf-8"))
    assert [
        after_claim
        for before_claim, after_claim in zip(before["evidence"], after["evidence"], strict=True)
        if SURFACE_CAPABILITY[before_claim["surface"]] == capability
    ] == [
        before_claim
        for before_claim in before["evidence"]
        if SURFACE_CAPABILITY[before_claim["surface"]] == capability
    ]
    assert fixture.read_text(encoding="utf-8") == manifest


def test_refresh_refuses_when_the_fresh_core_manifest_cannot_be_read(tmp_path: Path) -> None:
    claims, fixture, _manifest = _prepared(tmp_path)
    before_claims = claims.read_text(encoding="utf-8")
    before_fixture = fixture.read_text(encoding="utf-8")

    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: None,
        read_serving=_serving(claims_path=claims),
    )

    assert result.failure == "core manifest read unavailable"
    assert result.rebound == ()
    assert result.needs_consumer_reread == ()
    assert claims.read_text(encoding="utf-8") == before_claims
    assert fixture.read_text(encoding="utf-8") == before_fixture


def test_refresh_refuses_when_the_core_manifest_moves_during_evidence_revalidation(
    tmp_path: Path,
) -> None:
    claims, fixture, manifest = _prepared(tmp_path)
    before_claims = claims.read_text(encoding="utf-8")
    before_fixture = fixture.read_text(encoding="utf-8")
    later_manifest = _MANIFEST.read_text(encoding="utf-8")
    reads = iter((manifest, later_manifest, later_manifest))

    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: next(reads),
        read_serving=_serving(claims_path=claims),
    )

    assert result.failure == "core manifest changed or could not be authenticated during refresh"
    assert claims.read_text(encoding="utf-8") == before_claims
    assert fixture.read_text(encoding="utf-8") == before_fixture


def test_refresh_rewrites_no_claim_file_when_every_claim_needs_a_consumer_reread(
    tmp_path: Path,
) -> None:
    claims, fixture, manifest = _prepared(tmp_path)
    before_claims = claims.read_text(encoding="utf-8")

    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: manifest,
        read_serving=lambda **_kwargs: None,
    )

    assert not result.ok
    assert len(result.needs_consumer_reread) == len(json.loads(before_claims)["evidence"])
    assert result.rebound == ()
    assert claims.read_text(encoding="utf-8") == before_claims
    assert fixture.read_text(encoding="utf-8") == manifest


def test_refresh_refuses_an_unreadable_committed_claims_file(tmp_path: Path) -> None:
    claims, fixture, manifest = _prepared(tmp_path)
    serving = _serving(claims_path=claims)
    _ = claims.write_text("{", encoding="utf-8")

    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: manifest,
        read_serving=serving,
    )

    assert result.failure.startswith("committed claims unreadable:")


def test_refresh_refuses_claim_documents_that_change_between_validation_and_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claims, fixture, manifest = _prepared(tmp_path)
    loaded = load_claims(path=claims)
    assert isinstance(loaded, Success)
    serving = _serving(claims_path=claims)
    monkeypatch.setattr(incident_fleet_refresh, "load_claims", lambda **_kwargs: loaded)

    _ = claims.write_text('{"schema": 1, "evidence": {}}', encoding="utf-8")
    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: manifest,
        read_serving=serving,
    )
    assert result.failure == "committed claims changed while being read"

    _ = claims.write_text('{"schema": 1, "evidence": []}', encoding="utf-8")
    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: manifest,
        read_serving=serving,
    )
    assert result.failure == "committed claims changed while being read"

    _ = claims.write_text('{"schema": 1, "evidence": [1, 2, 3]}', encoding="utf-8")
    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: manifest,
        read_serving=serving,
    )
    assert result.failure == "committed claims changed while being read"


def test_refresh_helpers_clean_up_a_failed_atomic_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "fixture.json"

    def refuse_replace(self: Path, destination: Path) -> Path:
        _ = (self, destination)
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(Path, "replace", refuse_replace)
    with pytest.raises(OSError, match="simulated replacement failure"):
        incident_fleet_refresh._atomic_write(path=target, text="new fixture")  # noqa: SLF001

    assert not list(tmp_path.glob(".fixture.json.*.tmp"))
    assert incident_fleet_refresh._document(path=target) is None  # noqa: SLF001
