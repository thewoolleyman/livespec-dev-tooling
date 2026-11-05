"""Joining a worker to the isolated fixture of `SPECIFICATION/non-functional-requirements.md`.

"Every production cluster network or control-plane change a worker needs MUST ... be proved
against an isolated K3s fixture ..." (§"Homelab worker nodes"). `homelab-worker/fixture/
join-fixture-worker.sh` enrolls a worker into that fixture through the production RBAC, token
mint, networking agents and container step. These run it under the system `/bin/bash` against a
stub `limactl` that plays the VM, its Docker and the fixture's kubectl, and assert:

- it refuses an undeclared host, and a VM with no running fixture, before any cluster change;
- it applies the production RBAC and agents, pointed at the fixture's server and the worker's
  eth0, and converges the worker on the fixture network apart from its production state;
- the enrollment reaches the VM only on stdin, never in an argument;
- it waits for the Node and refuses to finish until a serving CSR is approved.
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
_SCRIPT = _HW / "fixture" / "join-fixture-worker.sh"
_WORKER = "macbook-m4-max-homelab-worker"
_CERT = "-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----"

_STUB_LIMACTL = """#!/bin/bash
s="$STUB_STATE"
printf 'limactl %s\\n' "$*" >> "$s/calls.log"
shift 5
case "$1 $2" in
  "docker inspect") cat "$s/server-running" ;;
  "docker exec")
    shift 2
    [ "$1" = "-i" ] && shift
    shift
    case "$1" in
      cat) printf '%s\\n' "$STUB_CERT" ;;
      kubectl)
        shift
        case "$1 $2" in
          "apply -f") cat >> "$s/applied.yaml"; printf -- '---\\n' >> "$s/applied.yaml" ;;
          "get configmap") printf '%s' "$STUB_CERT" ;;
          "get node") echo 172.18.0.4 ;;
          "get csr") : ;;
        esac ;;
    esac ;;
  "bash -s") cat > "$s/converge-stdin" ;;
  "install -m") cat > "$s/delivered-${5##*/}" ;;
esac
"""


@dataclass(frozen=True, kw_only=True)
class _Mac:
    state: Path
    bin_dir: Path


@pytest.fixture
def mac(tmp_path: Path) -> _Mac:
    state = tmp_path / "stub"
    state.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    limactl = bin_dir / "limactl"
    limactl.write_text(_STUB_LIMACTL, encoding="utf-8")
    limactl.chmod(limactl.stat().st_mode | stat.S_IXUSR)
    (state / "calls.log").write_text("", encoding="utf-8")
    (state / "server-running").write_text("true\n", encoding="utf-8")
    return _Mac(state=state, bin_dir=bin_dir)


def _run(*, mac: _Mac, host: str = "macbook-m4-max") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), host],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{mac.bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(mac.state),
            "STUB_CERT": _CERT,
            "WAIT_SECONDS": "0",
            "POLL_SECONDS": "1",
        },
        check=False,
        timeout=120,
    )


def _calls(*, mac: _Mac) -> list[str]:
    return (mac.state / "calls.log").read_text(encoding="utf-8").splitlines()


def test_an_undeclared_host_is_refused_before_any_vm_call(mac: _Mac) -> None:
    result = _run(mac=mac, host="macbook-pro")
    assert result.returncode != 0
    assert "is not declared" in result.stderr
    assert _calls(mac=mac) == []


def test_a_vm_without_a_running_fixture_is_refused_before_any_cluster_change(mac: _Mac) -> None:
    (mac.state / "server-running").write_text("false\n", encoding="utf-8")
    result = _run(mac=mac)
    assert result.returncode != 0
    assert "run k3s-fixture.sh up first" in result.stderr
    assert [c for c in _calls(mac=mac) if "kubectl" in c] == []


def test_the_worker_joins_the_fixture_through_the_production_path(mac: _Mac) -> None:
    result = _run(mac=mac)
    assert result.returncode != 0
    assert f"Node {_WORKER} registered" in result.stdout
    assert "no serving CSR" in result.stderr
    applied = (mac.state / "applied.yaml").read_text(encoding="utf-8")
    for name in (
        "homelab-worker-bootstrap",
        "homelab-worker-flannel",
        "homelab-worker-kube-proxy",
        "homelab-worker-kube-router",
        "bootstrap-token-",
    ):
        assert f"name: {name}" in applied
    assert "api-server-host: k3d-hw-fixture-server-0" in applied
    assert "flannel-iface: eth0" in applied
    assert "api-server-host: poweredge" not in applied
    converges = [c for c in _calls(mac=mac) if " bash -s -- " in c]
    assert (
        converges
        == [
            f"limactl shell --workdir / {_WORKER} sudo bash -s -- {_WORKER} macbook-m4-max "
            + (_HW / "image" / "ref").read_text(encoding="utf-8").splitlines()[-1]
            + " /mnt/lima-hwdata/fixture-worker k3d-hw-fixture"
        ]
        * 2
    )
    assert (mac.state / "converge-stdin").read_text(encoding="utf-8") == (
        _HW / "vm" / "converge-worker-container.sh"
    ).read_text(encoding="utf-8")


def test_the_enrollment_reaches_the_vm_only_on_stdin(mac: _Mac) -> None:
    _run(mac=mac)
    kubeconfig = (mac.state / "delivered-bootstrap-kubeconfig").read_text(encoding="utf-8")
    token = re.search(r"token: (\S+)", kubeconfig)
    assert token
    assert "server: https://k3d-hw-fixture-server-0:6443" in kubeconfig
    assert (mac.state / "delivered-client-ca.crt").read_text(encoding="utf-8") == f"{_CERT}\n"
    assert all(token.group(1) not in c for c in _calls(mac=mac))
    assert all(token.group(1).split(".")[1] not in c for c in _calls(mac=mac))
