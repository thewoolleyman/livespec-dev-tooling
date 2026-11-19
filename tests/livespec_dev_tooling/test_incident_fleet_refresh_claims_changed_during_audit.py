"""A claims replacement during the serving-evidence audit is never overwritten from the stale snapshot."""

from __future__ import annotations

import json
from pathlib import Path

from livespec_dev_tooling._incident_fleet_capabilities import SURFACE_CAPABILITY
from livespec_dev_tooling.incident_fleet_refresh import refresh

_FIXTURES = Path(__file__).parent / "fixtures" / "incident_fleet"


def test_refresh_refuses_to_overwrite_claims_replaced_during_the_serving_audit(
    tmp_path: Path,
) -> None:
    claims = tmp_path / "claims.json"
    document = json.loads((_FIXTURES / "claims-wellformed.json").read_text(encoding="utf-8"))
    claims.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    builds = {
        (entry["repository"], SURFACE_CAPABILITY[entry["surface"]]): entry["release_build"]
        for entry in document["evidence"]
    }
    replaced = json.loads(json.dumps(document))
    replaced["evidence"][0]["release_build"] = "v9.9.9"
    replacement = json.dumps(replaced, indent=2) + "\n"
    fixture = tmp_path / "core-fleet-manifest.jsonc"

    def read_serving(*, repository: str, capability: str) -> str | None:
        claims.write_text(replacement, encoding="utf-8")
        return builds.get((repository, capability))

    manifest = (_FIXTURES / "core-fleet-manifest.jsonc").read_text(encoding="utf-8") + "\n"
    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: manifest,
        read_serving=read_serving,
    )

    assert result.failure == "committed claims changed during refresh"
    assert not result.rebound
    assert claims.read_text(encoding="utf-8") == replacement
    assert not fixture.exists()
