"""The incident fleet manifest refresh is a committed operator command."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]


def test_the_manifest_refresh_is_a_committed_incident_fleet_command() -> None:
    justfile = _REPO_ROOT / "justfile"

    assert "incident-fleet-refresh:" in justfile.read_text(encoding="utf-8")
