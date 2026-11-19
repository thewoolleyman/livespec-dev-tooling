"""A claims replacement landing just before the claims replace is never overwritten."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from livespec_dev_tooling._incident_fleet_capabilities import SURFACE_CAPABILITY
from livespec_dev_tooling.incident_fleet_refresh import refresh

_FIXTURES = Path(__file__).parent / "fixtures" / "incident_fleet"


def test_refresh_refuses_a_claims_replacement_landing_after_the_audit_snapshot_check(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    claims = tmp_path / "claims.json"
    document = json.loads((_FIXTURES / "claims-wellformed.json").read_text(encoding="utf-8"))
    _ = claims.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    builds = {
        (entry["repository"], SURFACE_CAPABILITY[entry["surface"]]): entry["release_build"]
        for entry in document["evidence"]
    }
    replaced = json.loads(json.dumps(document))
    replaced["evidence"][0]["release_build"] = "v9.9.9"
    replacement = json.dumps(replaced, indent=2) + "\n"
    fixture = tmp_path / "core-fleet-manifest.jsonc"
    original_write_text = Path.write_text
    replaced_once: list[bool] = []

    def write_text_after_snapshot_check(self: Path, data: str, *args: Any, **kwargs: Any) -> int:
        # The first temporary file written is the earliest write after the snapshot comparison.
        if self.name.startswith(".") and not replaced_once:
            replaced_once.append(True)
            _ = original_write_text(claims, replacement, encoding="utf-8")
        return original_write_text(self, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", write_text_after_snapshot_check)

    def read_serving(*, repository: str, capability: str) -> str | None:
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
