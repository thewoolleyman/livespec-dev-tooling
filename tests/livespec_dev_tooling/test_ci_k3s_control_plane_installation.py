"""Installation contract for the k3s control-plane telemetry timer."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_OBSERVABILITY = _REPO_ROOT / "ci-runner" / "observability"
_ROLE_DEFAULTS = _REPO_ROOT / "ansible" / "roles" / "ci_observability" / "defaults" / "main.yml"


def _read(*, path: Path) -> str:
    """Read one committed deployment source file."""
    assert path.is_file(), f"expected {path.relative_to(_REPO_ROOT)} to be committed"
    return path.read_text(encoding="utf-8")


def test_control_plane_emitter_is_armed_every_minute_with_read_only_identity() -> None:
    """The Ansible role installs and arms a root unit without an admin kubeconfig."""
    service = _OBSERVABILITY / "ci-k3s-control-plane-gauges.service"
    timer = _OBSERVABILITY / "ci-k3s-control-plane-gauges.timer"
    service_text = _read(path=service)
    timer_text = _read(path=timer)
    defaults = _read(path=_ROLE_DEFAULTS)

    assert "ExecStart=/usr/local/lib/ci-runner/ci-k3s-control-plane-gauges.sh" in service_text
    assert "KUBECONFIG=/etc/otel-collector/kubeconfig" in service_text
    assert "/etc/rancher/k3s/k3s.yaml" not in service_text
    assert "OnUnitActiveSec=1min" in timer_text
    for filename in (service.name, timer.name, "ci-k3s-control-plane-gauges.sh"):
        assert filename in defaults
