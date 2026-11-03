"""Pressure-stall telemetry is installed consistently across every execution target."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPOSITORY_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "pressure_telemetry"
_SCRIPT = _ROLE / "files" / "pressure-telemetry.sh"
_TASKS = _ROLE / "tasks" / "main.yml"
_SERVICE = _ROLE / "templates" / "pressure-telemetry.service.j2"
_TIMER = _ROLE / "templates" / "pressure-telemetry.timer.j2"
_CI_POOL_PLAY = _ANSIBLE / "ci-pool.yml"
_DEV_HOST_PLAY = _ANSIBLE / "dev-host.yml"


def test_pressure_emitter_sends_every_psi_line_directly_from_each_execution_target() -> None:
    """Every host gets all PSI resources, fields, fail-closed reads, and a one-minute timer."""
    assert _SCRIPT.is_file(), "the pressure emitter must be committed with its Ansible role"
    assert _TASKS.is_file(), "the pressure role must converge its script and systemd units"
    assert _SERVICE.is_file(), "the emitter needs the collector-managed ingest-key environment"
    assert _TIMER.is_file(), "the emitter needs a timer no slower than once per minute"

    script = _SCRIPT.read_text(encoding="utf-8")
    for resource in ("cpu", "memory", "io"):
        assert f"/proc/pressure/{resource}" in script
    for line in ("some", "full"):
        assert line in script
    for field in ("avg10", "avg60", "avg300"):
        assert field in script
    assert "host.name" in script
    assert "https://api.honeycomb.io/v1/metrics" in script
    assert "missing pressure file" in script
    assert "return 1" in script

    service = _SERVICE.read_text(encoding="utf-8")
    assert "EnvironmentFile=/etc/otel-collector/.env" in service
    assert "HONEYCOMB_INGEST_KEY_LIVESPEC" in service

    timer = _TIMER.read_text(encoding="utf-8")
    assert "OnUnitActiveSec=60s" in timer
    assert "AccuracySec=1s" in timer

    for play in (_CI_POOL_PLAY, _DEV_HOST_PLAY):
        assert "role: pressure_telemetry" in play.read_text(encoding="utf-8")

    tasks = _TASKS.read_text(encoding="utf-8")
    assert "ansible.builtin.copy:" in tasks
    assert "ansible.builtin.template:" in tasks
