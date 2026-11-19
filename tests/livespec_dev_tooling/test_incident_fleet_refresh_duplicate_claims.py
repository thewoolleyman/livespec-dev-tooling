"""A duplicate (repository, surface) claim is never rebound on the first claim's evidence."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from livespec_dev_tooling._incident_fleet_capabilities import SURFACE_CAPABILITY
from livespec_dev_tooling.incident_fleet_refresh import refresh

_FIXTURES = Path(__file__).parent / "fixtures" / "incident_fleet"


def test_refresh_lists_a_duplicate_claim_for_a_consumer_reread_and_leaves_it_unchanged(
    tmp_path: Path,
) -> None:
    document = json.loads((_FIXTURES / "claims-wellformed.json").read_text(encoding="utf-8"))
    first = document["evidence"][0]
    duplicate = {**first, "release_build": "v9.9.9"}
    document["evidence"].append(duplicate)
    claims = tmp_path / "claims.json"
    claims.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    manifest = (_FIXTURES / "core-fleet-manifest.jsonc").read_text(encoding="utf-8") + "\n"
    fixture = tmp_path / "core-fleet-manifest.jsonc"
    builds = {
        (entry["repository"], SURFACE_CAPABILITY[entry["surface"]]): entry["release_build"]
        for entry in document["evidence"][:-1]
    }

    def read_serving(*, repository: str, capability: str) -> str | None:
        return builds.get((repository, capability))

    result = refresh(
        claims_path=claims,
        manifest_fixture_path=fixture,
        read_manifest=lambda: manifest,
        read_serving=read_serving,
    )

    identity = hashlib.sha256(manifest.encode()).hexdigest()
    after = json.loads(claims.read_text(encoding="utf-8"))["evidence"]
    assert not result.ok
    assert [claim.release_build for claim, _reason in result.needs_consumer_reread] == ["v9.9.9"]
    assert len(result.rebound) == len(document["evidence"]) - 1
    assert after[0]["manifest_sha256"] == identity
    assert after[-1] == duplicate
