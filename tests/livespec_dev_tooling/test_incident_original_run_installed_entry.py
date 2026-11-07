"""The operator entrance runs from the controller's installation, with no operator tooling."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import pytest

from livespec_dev_tooling import incident_original_run_entry as entry
from livespec_dev_tooling.incident_forge_reads import ForgeReads

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-jvfb7x


def test_installed_ports_use_the_manifest_reader_and_the_app_read_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _ = (tmp_path / "reader.env").write_text("BEADS_DOLT_PASSWORD=tenant\n")
    installation = cast(
        "Any",
        SimpleNamespace(
            repository="owner/repo",
            repo=tmp_path / "reference",
            state=tmp_path / "state",
            reader=("/opt/venv/bin/python", "/opt/reader/incident_authority.py"),
            config=tmp_path / "controller.json",
        ),
    )
    spawn = Mock(return_value=subprocess.CompletedProcess([], 0, stdout=b"[]"))
    monkeypatch.setattr(subprocess, "run", spawn)
    ports = entry.installed_ports(installation=installation)
    listing = ports.canonical.ledger(["comments", "incident-1", "--json"])
    facts = (
        listing == "[]",
        spawn.call_args.args[0] == ["bd", "comments", "incident-1", "--json"],
        spawn.call_args.kwargs["cwd"] == installation.repo,
        spawn.call_args.kwargs["env"]["BEADS_DOLT_PASSWORD"] == "tenant",
        isinstance(cast("Any", ports.read).read, ForgeReads),
    )
    assert all(facts), facts
