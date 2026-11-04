"""The runner-only uv source is supplied by pool infrastructure, not workflows."""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROXY_MANIFEST = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "warm-cache" / "pypi-proxy" / "pypi-proxy.yaml"
)
_HOOK_TEMPLATE = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "arc" / "hook-pod-template.yaml"


def test_hp_runner_only_jobs_get_a_read_only_uv_proxy_wrapper() -> None:
    """The wrapper routes frozen wheel URLs without giving a job a write surface."""
    proxy = _PROXY_MANIFEST.read_text(encoding="utf-8")
    template = _HOOK_TEMPLATE.read_text(encoding="utf-8")

    assert "name: pypi-proxy-uv-wrapper" in proxy
    assert "https://files.pythonhosted.org/packages/" in proxy
    assert "http://pypi-proxy.ci-warm-cache.svc.cluster.local:8081/packages/" in proxy
    assert "name: pypi-proxy-uv-wrapper" in template
    assert "mountPath: /opt/ci-runner/uv-proxy" in template
    assert "readOnly: true" in template
    assert "value: /opt/ci-runner/uv-proxy:" in template
