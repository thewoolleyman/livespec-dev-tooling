"""A same-length claims replacement between reads is never rebound on the old claims' evidence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from returns.result import Success

from livespec_dev_tooling import incident_fleet_refresh
from livespec_dev_tooling._incident_fleet_capabilities import SURFACE_CAPABILITY
from livespec_dev_tooling._incident_fleet_sources import load_claims
from livespec_dev_tooling.incident_fleet_refresh import refresh

_FIXTURES = Path(__file__).parent / "fixtures" / "incident_fleet"


def test_refresh_refuses_a_same_length_replacement_whose_own_evidence_was_never_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claims = tmp_path / "claims.json"
    original = (_FIXTURES / "claims-wellformed.json").read_text(encoding="utf-8")
    claims.write_text(original, encoding="utf-8")
    loaded = load_claims(path=claims)
    assert isinstance(loaded, Success)
    builds = {
        (claim.repository, SURFACE_CAPABILITY[claim.surface]): claim.release_build
        for claim in loaded.unwrap()
    }
    monkeypatch.setattr(incident_fleet_refresh, "load_claims", lambda **_kwargs: loaded)

    document = json.loads(original)
    document["evidence"][0]["release_build"] = "v9.9.9"
    replacement = json.dumps(document, indent=2) + "\n"
    claims.write_text(replacement, encoding="utf-8")
    fixture = tmp_path / "core-fleet-manifest.jsonc"

    def read_serving(*, repository: str, capability: str) -> str | None:
        return builds.get((repository, capability))

    manifest = (_FIXTURES / "core-fleet-manifest.jsonc").read_text(encoding="utf-8") + "\n"
    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: manifest,
        read_serving=read_serving,
    )

    assert result.failure == "committed claims changed while being read"
    assert claims.read_text(encoding="utf-8") == replacement
