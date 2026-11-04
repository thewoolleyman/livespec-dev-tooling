"""The independent controller process refuses unprovisioned startup before binding."""

from __future__ import annotations

import json
import sys

from livespec_dev_tooling import incident_observer_service

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-47ij37


def test_missing_host_installation_refuses_before_http_or_state_creation(
    tmp_path, monkeypatch, capsys
):
    missing = tmp_path / "unprovisioned.json"
    monkeypatch.setattr(sys, "argv", ["observer-service", "--config", str(missing)])
    assert incident_observer_service.main() == 2
    assert json.loads(capsys.readouterr().out)["status"] == "refused"
    assert not missing.exists()
    assert list(tmp_path.iterdir()) == []
