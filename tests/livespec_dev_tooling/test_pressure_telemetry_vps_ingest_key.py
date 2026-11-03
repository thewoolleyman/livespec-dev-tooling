"""The dev host receives the same direct-OTLP credential as every pool target."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_VPS_HOST_VARS = _REPOSITORY_ROOT / "ansible" / "inventory" / "host_vars" / "vps.yml"


def test_dev_host_collector_converges_the_livespec_ingest_key_for_pressure_telemetry() -> None:
    """The direct emitter must not depend on an untracked hand-placed key on vps."""
    host_vars = _VPS_HOST_VARS.read_text(encoding="utf-8")
    assert "otel_collector_env_from_controller:\n  - HONEYCOMB_INGEST_KEY_LIVESPEC" in host_vars
