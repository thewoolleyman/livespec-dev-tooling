"""The fixture proof of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

`homelab-worker/fixture/prove-fixture-worker.sh` proves a worker joined to the isolated fixture at
the fixture's egress-selector-mode. These run it under the system `/bin/bash` against a stub
`limactl` that plays the fixture's kubectl, with the API server's reach to a kubelet without a K3s
agent tunnel and NetworkPolicy enforcement on the worker emulated in files, and assert:

- `agent` is the negative control: it passes only when logs and exec on the worker fail;
- `disabled` passes only when logs, exec, port-forward and kubelet stats on the worker, logs on
  the K3s node, pod-to-pod both ways, ClusterIP, DNS and a NetworkPolicy deny (allowed, denied,
  allowed again) all hold;
- the proof pods tolerate the admission hold and are pinned to the worker and a K3s node;
- an undeclared host or an unknown mode is refused before any cluster call.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "homelab-worker" / "fixture" / "prove-fixture-worker.sh"
)
_WORKER = "macbook-m4-max-homelab-worker"

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
    *, mac: _Mac, mode: str, tunnel_only: str, enforced: str = "1", dns: str = "1"
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), "macbook-m4-max", mode],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{mac.bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(mac.state),
            "STUB_TUNNEL_ONLY": tunnel_only,
            "STUB_ENFORCED": enforced,
            "STUB_DNS": dns,
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


def test_the_disabled_mode_proof_passes_every_check_on_the_worker(mac: _Mac) -> None:
    result = _prove(mac=mac, mode="disabled", tunnel_only="0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _proofs(result) == dict.fromkeys(
        (
            "logs-on-worker",
            "exec-on-worker",
            "logs-on-k3s-node",
            "kubelet-stats-on-worker",
            "port-forward-to-worker",
            "pod-to-pod-worker-to-k3s",
            "pod-to-pod-k3s-to-worker",
            "clusterip-and-dns-from-worker",
            "dns-10.43.0.10-from-worker",
            "networkpolicy-deny-on-worker",
            "networkpolicy-lifted-on-worker",
        ),
        "PASS",
    )
    assert "PASSED" in result.stdout


@pytest.mark.parametrize(
    ("tunnel_only", "enforced", "dns", "failing"),
    [
        ("1", "1", "1", "logs-on-worker"),
        ("0", "0", "1", "networkpolicy-deny-on-worker"),
        ("0", "1", "0", "dns-10.43.0.10-from-worker"),
    ],
)
def test_the_disabled_mode_proof_fails_when_any_check_fails(
    mac: _Mac, tunnel_only: str, enforced: str, dns: str, failing: str
) -> None:
    result = _prove(mac=mac, mode="disabled", tunnel_only=tunnel_only, enforced=enforced, dns=dns)
    assert result.returncode != 0
    assert _proofs(result)[failing] == "FAIL"
    assert "FAILED" in result.stderr


def test_the_proof_pods_tolerate_the_hold_and_are_pinned_to_both_node_kinds(mac: _Mac) -> None:
    _prove(mac=mac, mode="disabled", tunnel_only="0")
    applied = (mac.state / "applied.yaml").read_text(encoding="utf-8")
    assert applied.count(f"nodeName: {_WORKER}") == 2
    assert applied.count("nodeName: k3d-hw-fixture-agent-0") == 2
    assert applied.count("key: homelab-worker.livespec.dev/admission") == 4
    assert "busybox:1.37.0@sha256:" in applied
    calls = (mac.state / "calls.log").read_text(encoding="utf-8")
    assert "kubectl delete namespace hw-proof" in calls


@pytest.mark.parametrize(
    ("args", "message"),
    [(["macbook-pro", "agent"], "is not declared"), (["macbook-m4-max", "cluster"], "is not")],
)
def test_an_undeclared_host_or_unknown_mode_is_refused_before_any_cluster_call(
    mac: _Mac, args: list[str], message: str
) -> None:
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        env={"PATH": f"{mac.bin_dir}:/usr/bin:/bin", "STUB_STATE": str(mac.state)},
        check=False,
        timeout=60,
    )
    assert result.returncode != 0
    assert message in result.stderr
    assert (mac.state / "calls.log").read_text(encoding="utf-8") == ""
