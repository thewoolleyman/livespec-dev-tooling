"""Fixture proof wrapper, `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

`homelab-worker/fixture/prove-fixture-worker.sh` runs the production proof, `prove-worker.sh`
(its checks are tested in `test_homelab_worker_prove.py`), against the isolated fixture. These run
it under the system `/bin/bash` against a stub `limactl` that plays the fixture's kubectl, and
assert only what the wrapper adds:

- every kubectl call and the port-forward check run inside the fixture's server container;
- the peer node is the fixture's K3s agent node;
- `agent` is the negative control: it passes only when logs and exec on the worker fail;
- `disabled` runs the full proof and fails when the worker is unreachable;
- an undeclared host or an unknown mode is refused before any cluster call.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []


def _mock_hosts(root: Path, *names: str) -> Path:
    """A hosts directory declaring only the made-up hosts the test names."""
    hosts = root / "hosts"
    hosts.mkdir(parents=True, exist_ok=True)
    for name in names:
        (hosts / f"{name}.env").write_text("WORKER_HOST_OS=Darwin\n", encoding="utf-8")
    return hosts


_SCRIPT = (
    Path(__file__).resolve().parents[2] / "homelab-worker" / "fixture" / "prove-fixture-worker.sh"
)
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"

_STUB_LIMACTL = """#!/bin/bash
s="$STUB_STATE"
printf 'limactl %s\\n' "$*" >> "$s/calls.log"
shift 10
case "$1" in
  apply)
    body="$(cat)"
    printf '%s\\n---\\n' "$body" >> "$s/applied.yaml"
    case "$body" in *"kind: NetworkPolicy"*) [ "$STUB_ENFORCED" = 1 ] && touch "$s/policy" ;; esac ;;
  wait) : ;;
  -c)
    if [ "$STUB_TUNNEL_ONLY" = 1 ]; then echo 'error upgrading connection' >&2; exit 1; fi
    echo proof-ok ;;
  get)
    if [ "$2" = --raw ]; then
      if [ "$STUB_TUNNEL_ONLY" = 1 ]; then echo 'proxy error 502' >&2; exit 1; fi
      echo '{"node":{"nodeName":"x"}}'; exit 0
    fi
    if [ "$2" = service ]; then echo 10.99.0.53; exit 0; fi
    case "$5" in
      server-worker) echo 10.42.5.10 ;;
      *) echo 10.42.1.20 ;;
    esac ;;
  logs)
    if [ "$4" = client-worker ] && [ "$STUB_TUNNEL_ONLY" = 1 ]; then
      echo 'failed to find Session for client' >&2; exit 1
    fi
    echo proof-ready ;;
  exec)
    pod="$4"
    shift 5
    if [ "$pod" = client-worker ] && [ "$STUB_TUNNEL_ONLY" = 1 ]; then
      echo 'failed to find Session for client' >&2; exit 1
    fi
    case "$*" in
      *10.42.5.10*) [ -f "$s/policy" ] && { echo 'download timed out' >&2; exit 1; } ;;
    esac
    case "$1" in
      echo) echo exec-ok ;;
      wget) [ "$STUB_DNS" = 0 ] && case "$*" in *svc.cluster.local*) exit 1 ;; esac; echo proof-ok ;;
      nslookup) [ "$STUB_DNS" = 0 ] && exit 1; echo 'Address: 10.43.0.1' ;;
      ping) [ "$STUB_MTU" = 0 ] && exit 1; echo '3 packets received' ;;
    esac ;;
  delete)
    [ "$2" = networkpolicy ] && rm -f "$s/policy" ;;
esac
exit 0
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
    return _Mac(state=state, bin_dir=bin_dir)


def _prove(
    *, mac: _Mac, mode: str, tunnel_only: str, enforced: str = "1", dns: str = "1", mtu: str = "1"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), _HOST, mode],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{mac.bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(mac.state),
            "HOMELAB_WORKER_HOSTS_DIR": str(_mock_hosts(mac.state, _HOST)),
            "STUB_TUNNEL_ONLY": tunnel_only,
            "STUB_ENFORCED": enforced,
            "STUB_DNS": dns,
            "STUB_MTU": mtu,
            "POLICY_SETTLE_SECONDS": "0",
        },
        check=False,
        timeout=120,
    )


def _proofs(result: subprocess.CompletedProcess[str]) -> dict[str, str]:
    lines = [line.split() for line in result.stdout.splitlines() if line.startswith("PROOF ")]
    return {words[1]: words[2] for words in lines}


def test_the_agent_mode_negative_control_passes_only_when_the_worker_is_unreachable(
    mac: _Mac,
) -> None:
    control = _prove(mac=mac, mode="agent", tunnel_only="1")
    assert control.returncode == 0, control.stdout + control.stderr
    assert _proofs(control) == {"logs-on-worker": "PASS", "exec-on-worker": "PASS"}
    reachable = _prove(mac=mac, mode="agent", tunnel_only="0")
    assert reachable.returncode != 0
    assert _proofs(reachable) == {"logs-on-worker": "FAIL", "exec-on-worker": "FAIL"}


def test_the_disabled_mode_runs_the_full_proof_inside_the_fixture(mac: _Mac) -> None:
    result = _prove(mac=mac, mode="disabled", tunnel_only="0")
    assert result.returncode == 0, result.stdout + result.stderr
    proofs = _proofs(result)
    assert len(proofs) > 2
    assert set(proofs.values()) == {"PASS"}
    calls = (mac.state / "calls.log").read_text(encoding="utf-8").splitlines()
    assert calls
    assert all(
        c.startswith(
            f"limactl shell --workdir / {_WORKER} sudo docker exec -i k3d-hw-fixture-server-0 "
        )
        for c in calls
    )
    assert any(" sh -c kubectl port-forward " in c for c in calls)
    applied = (mac.state / "applied.yaml").read_text(encoding="utf-8")
    assert applied.count("nodeName: k3d-hw-fixture-agent-0") == 2


def test_the_disabled_mode_fails_when_the_worker_is_unreachable(mac: _Mac) -> None:
    result = _prove(mac=mac, mode="disabled", tunnel_only="1")
    assert result.returncode != 0
    assert _proofs(result)["logs-on-worker"] == "FAIL"
    assert "FAILED" in result.stderr


@pytest.mark.parametrize(
    ("args", "message"),
    [(["gamma", "agent"], "is not declared"), ([_HOST, "cluster"], "is not")],
)
def test_an_undeclared_host_or_unknown_mode_is_refused_before_any_cluster_call(
    mac: _Mac, args: list[str], message: str
) -> None:
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{mac.bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(mac.state),
            "HOMELAB_WORKER_HOSTS_DIR": str(_mock_hosts(mac.state, _HOST)),
        },
        check=False,
        timeout=60,
    )
    assert result.returncode != 0
    assert message in result.stderr
    assert (mac.state / "calls.log").read_text(encoding="utf-8") == ""
