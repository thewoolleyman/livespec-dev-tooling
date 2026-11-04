"""The runner-only uv source is supplied by pool infrastructure, not workflows."""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROXY_MANIFEST = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "warm-cache" / "pypi-proxy" / "pypi-proxy.yaml"
)
_HOOK_TEMPLATE = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "arc" / "hook-pod-template.yaml"
_WRAPPER = re.compile(
    r"^  name: pypi-proxy-uv-wrapper\n  namespace: ci-warm-cache\ndata:\n  uv: \|\n"
    r"(?P<body>.*?)(?=^---)",
    re.MULTILINE | re.DOTALL,
)


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


def _wrapper_source() -> str:
    """Read the ConfigMap's executable payload, keeping its shell body executable."""
    matched = _WRAPPER.search(_PROXY_MANIFEST.read_text(encoding="utf-8"))
    assert matched is not None, "the PyPI proxy manifest must carry the uv wrapper ConfigMap"
    return textwrap.dedent(matched.group("body"))


def test_a_healthy_hp_source_routes_locked_wheels_without_public_downloads(
    *, tmp_path: Path
) -> None:
    """The hp install sees the pool URL, never the public wheel URL."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    lock = workspace / "uv.lock"
    public_url = "https://files.pythonhosted.org/packages/example/example-1.0.whl"
    proxy_url = (
        "http://pypi-proxy.ci-warm-cache.svc.cluster.local:8081/packages/example/example-1.0.whl"
    )
    lock.write_text(public_url + "\n", encoding="utf-8")

    wrapper = tmp_path / "uv"
    wrapper.write_text(_wrapper_source(), encoding="utf-8")
    wrapper.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    curl.chmod(0o755)
    real_uv = tmp_path / "real-uv"
    observed = tmp_path / "observed-lock"
    real_uv.write_text(
        '#!/bin/sh\ncat uv.lock > "$UV_OBSERVED_LOCK"\nexit 17\n',
        encoding="utf-8",
    )
    real_uv.chmod(0o755)

    result = subprocess.run(
        [str(wrapper), "sync", "--all-groups"],
        cwd=workspace,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "CI_RUNNER_NODE_NAME": "hp-xubuntu",
            "CI_RUNNER_REAL_UV": str(real_uv),
            "PYPI_FILES_PROXY": "http://pypi-proxy.ci-warm-cache.svc.cluster.local:8081",
            "UV_OBSERVED_LOCK": str(observed),
            "PATH": f"{bin_dir}:/usr/bin:/bin",
        },
        text=True,
    )

    assert result.returncode == 17, result.stderr
    assert observed.read_text(encoding="utf-8") == proxy_url + "\n"
    assert public_url not in observed.read_text(encoding="utf-8")
    assert lock.read_text(encoding="utf-8") == public_url + "\n"
    assert "locked Python packages through" in result.stderr


def test_an_unreachable_hp_source_falls_back_to_public_pypi_and_preserves_uvs_outcome(
    *, tmp_path: Path
) -> None:
    """A proxy outage must not turn a workflow package install into a pool outage."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    lock = workspace / "uv.lock"
    public_url = "https://files.pythonhosted.org/packages/example/example-1.0.whl"
    lock.write_text(public_url + "\n", encoding="utf-8")
    original = lock.read_text(encoding="utf-8")

    wrapper = tmp_path / "uv"
    wrapper.write_text(_wrapper_source(), encoding="utf-8")
    wrapper.chmod(0o755)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    curl = bin_dir / "curl"
    curl.write_text("#!/bin/sh\nexit 22\n", encoding="utf-8")
    curl.chmod(0o755)
    real_uv = tmp_path / "real-uv"
    observed = tmp_path / "observed-lock"
    real_uv.write_text(
        '#!/bin/sh\ncat uv.lock > "$UV_OBSERVED_LOCK"\nexit 17\n',
        encoding="utf-8",
    )
    real_uv.chmod(0o755)

    result = subprocess.run(
        [str(wrapper), "sync", "--all-groups"],
        cwd=workspace,
        capture_output=True,
        check=False,
        env={
            **os.environ,
            "CI_RUNNER_NODE_NAME": "hp-xubuntu",
            "CI_RUNNER_REAL_UV": str(real_uv),
            "PYPI_FILES_PROXY": "http://pypi-proxy.ci-warm-cache.svc.cluster.local:8081",
            "UV_OBSERVED_LOCK": str(observed),
            "PATH": f"{bin_dir}:/usr/bin:/bin",
        },
        text=True,
    )

    assert result.returncode == 17, result.stderr
    assert observed.read_text(encoding="utf-8") == original
    assert lock.read_text(encoding="utf-8") == original
    assert "installing from public PyPI" in result.stderr
