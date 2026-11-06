"""The production join of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

`homelab-worker/join-worker.sh` enrolls a host's worker into whatever cluster the caller's `kubectl`
reaches. These run it under the system `/bin/bash` against a stub `kubectl` and a stub `limactl`
that plays the worker VM, with a mocked server CA and cluster ConfigMap, and assert:

- it applies the enrollment RBAC, the three networking agents and the given cluster ConfigMap;
- it mints against the given API server and delivers the enrollment into the VM only on stdin,
  under the given state root;
- the worker converges twice (before and after delivery), on the given worker network if any,
  then the Node is awaited and its serving CSR approval attempted;
- a rerun for a registered Node mints and delivers nothing;
- an undeclared host or a missing or unknown argument is refused before any cluster or VM call.

Every value here is the stub's own; none is a production value.
"""

from __future__ import annotations

import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_HW = Path(__file__).resolve().parents[2] / "homelab-worker"
_SCRIPT = _HW / "join-worker.sh"
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"
_LAN = "10.99.0.21/24"
_API = "https://api.cluster.test:7443"
_CERT = "-----BEGIN CERTIFICATE-----\nstub\n-----END CERTIFICATE-----"
_CLUSTER_CONFIG = """apiVersion: v1
kind: ConfigMap
metadata:
  name: homelab-worker-cluster
  namespace: kube-system
data:
  api-server-host: api.cluster.test
  api-server-port: "7443"
  flannel-iface: test0
"""

_STUB_KUBECTL = """#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\\n' "$*" >> "$s/calls.log"
case "$1 $2" in
  "apply -f") cat >> "$s/applied.yaml"; printf -- '---\\n' >> "$s/applied.yaml" ;;
  "get configmap") printf '%s' "$STUB_CERT" ;;
  "get node") [ -f "$s/node-registered" ] || exit 1; echo 10.99.0.4 ;;
  "get nodes") : ;;
  "get csr") : ;;
esac
exit 0
"""

_STUB_LIMACTL = """#!/bin/bash
s="$STUB_STATE"
printf 'limactl %s\\n' "$*" >> "$s/calls.log"
shift 5
case "$1 $2" in
  "bash -s")
    cat > "$s/converge-stdin"
    n=$(($(cat "$s/converges" 2>/dev/null || echo 0) + 1))
    echo "$n" > "$s/converges"
    if [ "$n" -ge 2 ]; then touch "$s/node-registered"; fi ;;
  "install -m") cat > "$s/delivered-${5##*/}" ;;
esac
"""


@dataclass(frozen=True, kw_only=True)
class _Env:
    state: Path
    bin_dir: Path
    ca: Path
    cluster: Path


def _exe(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    state = tmp_path / "stub"
    (state / "hosts").mkdir(parents=True)
    (state / "hosts" / f"{_HOST}.env").write_text(
        f"WORKER_HOST_OS=Darwin\nWORKER_LAN_ADDRESS={_LAN}\n", encoding="utf-8"
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(path=bin_dir / "kubectl", body=_STUB_KUBECTL)
    _exe(path=bin_dir / "limactl", body=_STUB_LIMACTL)
    (state / "calls.log").write_text("", encoding="utf-8")
    ca = tmp_path / "server-ca.crt"
    ca.write_text(f"{_CERT}\n", encoding="utf-8")
    cluster = tmp_path / "cluster.yaml"
    cluster.write_text(_CLUSTER_CONFIG, encoding="utf-8")
    return _Env(state=state, bin_dir=bin_dir, ca=ca, cluster=cluster)


def _args(env: _Env, *extra: str) -> list[str]:
    return [
        _HOST,
        "--api-server",
        _API,
        "--server-ca",
        str(env.ca),
        "--cluster-config",
        str(env.cluster),
        *extra,
    ]


def _run(*, env: _Env, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{env.bin_dir}:/usr/bin:/bin",
            "HOMELAB_WORKER_HOSTS_DIR": str(env.state / "hosts"),
            "STUB_STATE": str(env.state),
            "STUB_CERT": _CERT,
            "WAIT_SECONDS": "0",
            "POLL_SECONDS": "1",
        },
        check=False,
        timeout=120,
    )


def _calls(*, env: _Env) -> list[str]:
    return (env.state / "calls.log").read_text(encoding="utf-8").splitlines()


def test_the_join_applies_the_cluster_objects_and_converges_around_the_delivery(
    env: _Env,
) -> None:
    result = _run(env=env, args=_args(env, "--state-root", "/srv/w", "--worker-network", "net1"))
    assert result.returncode != 0
    assert f"Node {_WORKER} registered" in result.stdout
    assert "no serving CSR" in result.stderr
    applied = (env.state / "applied.yaml").read_text(encoding="utf-8")
    for name in (
        "homelab-worker-bootstrap",
        "homelab-worker-flannel",
        "homelab-worker-kube-proxy",
        "homelab-worker-kube-router",
        "bootstrap-token-",
    ):
        assert f"name: {name}" in applied
    assert _CLUSTER_CONFIG in applied
    image = (_HW / "image" / "ref").read_text(encoding="utf-8").splitlines()[-1]
    converges = [c for c in _calls(env=env) if " bash -s -- " in c]
    expected = f"limactl shell --workdir / {_WORKER} sudo bash -s -- "
    assert converges == [f"{expected}{_WORKER} {_HOST} {image} /srv/w net1"] * 2
    assert (env.state / "converge-stdin").read_text(encoding="utf-8") == (
        _HW / "vm" / "converge-worker-container.sh"
    ).read_text(encoding="utf-8")
    installs = [c for c in _calls(env=env) if " install -m 0600 " in c]
    assert all("/srv/w/enrollment/" in c for c in installs)
    assert installs


def test_the_enrollment_targets_the_given_api_server_and_reaches_the_vm_only_on_stdin(
    env: _Env,
) -> None:
    _run(env=env, args=_args(env))
    kubeconfig = (env.state / "delivered-bootstrap-kubeconfig").read_text(encoding="utf-8")
    token = re.search(r"token: (\S+)", kubeconfig)
    assert token
    assert f"server: {_API}" in kubeconfig
    assert (env.state / "delivered-client-ca.crt").read_text(encoding="utf-8") == f"{_CERT}\n"
    assert all(token.group(1) not in c for c in _calls(env=env))
    assert all(token.group(1).split(".")[1] not in c for c in _calls(env=env))


def test_a_rerun_for_a_registered_node_mints_and_delivers_nothing(env: _Env) -> None:
    (env.state / "node-registered").write_text("", encoding="utf-8")
    result = _run(env=env, args=_args(env))
    assert result.returncode == 0, result.stdout + result.stderr
    assert "already registered" in result.stdout
    applied = (env.state / "applied.yaml").read_text(encoding="utf-8")
    assert "bootstrap-token-" not in applied
    assert not list(env.state.glob("delivered-*"))
    assert len([c for c in _calls(env=env) if " bash -s -- " in c]) == 1


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["gamma", "--api-server", _API, "--server-ca", "/x"], "is not declared"),
        ([_HOST, "--server-ca", "/x"], "--api-server is required"),
        ([_HOST, "--api-server", _API], "--server-ca is required"),
        ([_HOST, "--api-server", _API, "--server-ca", "/nonexistent"], "is not a file"),
        ([_HOST, "--api-server", _API, "--mode", "x"], "unknown argument"),
    ],
)
def test_bad_arguments_are_refused_before_any_cluster_or_vm_call(
    env: _Env, args: list[str], message: str
) -> None:
    result = _run(env=env, args=args)
    assert result.returncode != 0
    assert message in result.stderr
    assert _calls(env=env) == []


def test_without_a_worker_network_the_worker_converges_at_its_declared_lan_address(
    env: _Env,
) -> None:
    _run(env=env, args=_args(env, "--state-root", "/srv/w"))
    converges = [c for c in _calls(env=env) if " bash -s -- " in c]
    assert converges
    lan_ip = _LAN.split("/")[0]
    assert all(c.endswith(f" /srv/w host:{lan_ip}") for c in converges)


def test_a_host_declaring_no_lan_address_converges_without_a_network_argument(
    env: _Env,
) -> None:
    (env.state / "hosts" / f"{_HOST}.env").write_text("WORKER_HOST_OS=Darwin\n", encoding="utf-8")
    _run(env=env, args=_args(env, "--state-root", "/srv/w"))
    converges = [c for c in _calls(env=env) if " bash -s -- " in c]
    assert converges
    assert all(c.endswith(" /srv/w") for c in converges)
