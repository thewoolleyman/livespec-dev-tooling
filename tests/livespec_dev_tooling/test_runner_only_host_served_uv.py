"""The runner-only uv source is supplied by pool infrastructure, not workflows."""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PYPI_PROXY_MANIFEST = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "warm-cache" / "pypi-proxy" / "pypi-proxy.yaml"
)
_WRAPPER_MANIFEST = (
    _REPO_ROOT
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "warm-cache"
    / "pypi-proxy"
    / "pypi-proxy-uv-wrapper.yaml"
)
_HOOK_TEMPLATE = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "arc" / "hook-pod-template.yaml"
_WARM_CACHE_CONVERGE = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "warm-cache" / "converge-warm-cache.sh"
)
_STACK_CONVERGE = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "reconstruct" / "converge-ci-stack.sh"
)
_WRAPPER = re.compile(
    r"^  name: pypi-proxy-uv-wrapper\n(?:  namespace: [^\n]+\n)?data:\n  uv: \|\n"
    r"(?P<body>.*?)(?=^---)",
    re.MULTILINE | re.DOTALL,
)


def test_hp_runner_only_jobs_get_a_read_only_uv_proxy_wrapper() -> None:
    """The wrapper routes frozen wheel URLs without giving a job a write surface."""
    source = _WRAPPER_MANIFEST if _WRAPPER_MANIFEST.is_file() else _PYPI_PROXY_MANIFEST
    proxy = source.read_text(encoding="utf-8")
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
    source = _WRAPPER_MANIFEST if _WRAPPER_MANIFEST.is_file() else _PYPI_PROXY_MANIFEST
    matched = _WRAPPER.search(source.read_text(encoding="utf-8"))
    assert matched is not None, "the PyPI proxy manifest must carry the uv wrapper ConfigMap"
    return textwrap.dedent(matched.group("body"))


def test_the_ci_stack_publishes_the_shared_uv_wrapper_for_every_consumer() -> None:
    """The same wrapper definition is present before ARC creates a workflow pod."""
    assert _WRAPPER_MANIFEST.is_file()
    wrapper_definition = _WRAPPER_MANIFEST.read_text(encoding="utf-8")
    proxy = _PYPI_PROXY_MANIFEST.read_text(encoding="utf-8")
    warm_cache_converge = _WARM_CACHE_CONVERGE.read_text(encoding="utf-8")
    stack_converge = _STACK_CONVERGE.read_text(encoding="utf-8")
    template = _HOOK_TEMPLATE.read_text(encoding="utf-8")

    assert "namespace:" not in wrapper_definition
    assert "name: pypi-proxy-uv-wrapper" not in proxy
    assert (
        'run kubectl -n "${NAMESPACE}" apply -f '
        '"${SCRIPT_DIR}/pypi-proxy/pypi-proxy-uv-wrapper.yaml"'
    ) in warm_cache_converge
    assert (
        'kubectl -n "$RUNNERS_NAMESPACE" apply -f '
        '"${WARM_CACHE_DIR}/pypi-proxy/pypi-proxy-uv-wrapper.yaml"'
    ) in stack_converge
    assert (
        "    - name: pypi-proxy-uv-wrapper\n"
        "      configMap:\n"
        "        name: pypi-proxy-uv-wrapper\n"
        "        optional: false\n"
        "        defaultMode: 365"
    ) in template
    assert (
        "value: /opt/ci-runner/uv-proxy:/root/.cargo/bin:/root/.local/share/mise/shims:" in template
    )


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


def _mise_layout(*, root: Path, triple: str) -> tuple[Path, Path]:
    """Lay out a wrapper mount and one architecture's mise uv install, as a pool node has them."""
    wrapper_dir = root / "opt" / "ci-runner" / "uv-proxy"
    wrapper_dir.mkdir(parents=True)
    wrapper = wrapper_dir / "uv"
    wrapper.write_text(_wrapper_source(), encoding="utf-8")
    wrapper.chmod(0o755)
    install_dir = (
        root / "root" / ".local" / "share" / "mise" / "installs" / "uv" / "0.9.26" / f"uv-{triple}"
    )
    install_dir.mkdir(parents=True)
    real_uv = install_dir / "uv"
    real_uv.write_text(f'#!/bin/sh\nprintf "{triple} uv %s\\n" "$*"\nexit 0\n', encoding="utf-8")
    real_uv.chmod(0o755)
    return wrapper_dir, install_dir


@pytest.mark.parametrize(
    ("triple", "node"),
    [
        ("aarch64-unknown-linux-musl", "macbook-m4-max-homelab-worker"),
        ("x86_64-unknown-linux-musl", "poweredge-xubuntu"),
    ],
)
def test_off_hp_the_wrapper_runs_the_first_uv_on_path_outside_its_own_mount(
    *, tmp_path: Path, triple: str, node: str
) -> None:
    """On either node architecture the wrapper delegates to that node's own uv, not a fixed path."""
    wrapper_dir, install_dir = _mise_layout(root=tmp_path, triple=triple)
    environment = {key: value for key, value in os.environ.items() if key != "CI_RUNNER_REAL_UV"}

    result = subprocess.run(
        [str(wrapper_dir / "uv"), "--version"],
        cwd=tmp_path,
        capture_output=True,
        check=False,
        env={
            **environment,
            "CI_RUNNER_NODE_NAME": node,
            "PATH": f"{wrapper_dir}:{install_dir}:/usr/bin:/bin",
        },
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{triple} uv --version\n"


def test_the_wrapper_and_the_job_path_name_no_architecture_specific_uv_install() -> None:
    """The shared wrapper and the workflow PATH hold on every node architecture the pool runs."""
    template = _HOOK_TEMPLATE.read_text(encoding="utf-8")
    path_line = next(
        line
        for line in template.splitlines()
        if line.strip().startswith("value: /opt/ci-runner/uv-proxy:")
    )

    assert "x86_64" not in _wrapper_source()
    assert "/mise/installs/uv/" not in _wrapper_source()
    assert "x86_64" not in path_line
    assert "/mise/installs/uv/" not in path_line
    assert "/root/.local/share/mise/shims" in path_line
