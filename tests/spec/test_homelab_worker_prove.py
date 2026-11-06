"""The worker proof of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

`homelab-worker/prove-worker.sh` proves a worker joined to whatever cluster the caller's `kubectl`
reaches, against a peer node the caller names. These run it under the system `/bin/bash` against a
stub `kubectl` that emulates the API server's reach to the worker's kubelet and NetworkPolicy
enforcement in files, and assert:

- the default proof passes only when every check holds, and fails naming the check that does not;
- `--expect-streaming-failure` is the negative control: it passes only when logs and exec on the
  worker fail;
- cluster DNS is checked at the address the cluster's kube-dns Service reports;
- the proof pods tolerate the admission hold, are pinned to the worker and the peer, and use an
  image pinned by digest, and the proof namespace is deleted;
- an undeclared host, a missing peer or an unknown argument is refused before any cluster call.

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

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "prove-worker.sh"
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"
_PEER = "peer-node-1"
_DNS = "10.99.0.53"

_STUB_KUBECTL = f"""#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\\n' "$*" >> "$s/calls.log"
case "$1" in
  apply)
    body="$(cat)"
    printf '%s\\n---\\n' "$body" >> "$s/applied.yaml"
    case "$body" in *"kind: NetworkPolicy"*) [ "$STUB_ENFORCED" = 1 ] && touch "$s/policy" ;; esac ;;
  wait) : ;;
  get)
    if [ "$2" = --raw ]; then
      if [ "$STUB_TUNNEL_ONLY" = 1 ]; then echo 'proxy error 502' >&2; exit 1; fi
      echo '{{"node":{{"nodeName":"x"}}}}'; exit 0
    fi
    if [ "$2" = service ]; then echo {_DNS}; exit 0; fi
    case "$5" in
      server-worker) echo 10.99.5.10 ;;
      *) echo 10.99.1.20 ;;
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
      *10.99.5.10*) [ -f "$s/policy" ] && {{ echo 'download timed out' >&2; exit 1; }} ;;
    esac
    case "$1" in
      echo) echo exec-ok ;;
      wget) [ "$STUB_DNS" = 0 ] && case "$*" in *svc.cluster.local*) exit 1 ;; esac; echo proof-ok ;;
      nslookup) [ "$STUB_DNS" = 0 ] && exit 1; [ "$3" = {_DNS} ] || exit 1; echo ok ;;
      ping) [ "$STUB_MTU" = 0 ] && exit 1; echo '3 packets received' ;;
    esac ;;
  delete)
    [ "$2" = networkpolicy ] && rm -f "$s/policy" ;;
esac
exit 0
"""

_STUB_PF_SHELL = """#!/bin/bash
printf 'pfsh %s\\n' "$*" >> "$STUB_STATE/calls.log"
[ "$STUB_TUNNEL_ONLY" = 1 ] && exit 1
exit 0
"""


@dataclass(frozen=True, kw_only=True)
class _Env:
    state: Path
    bin_dir: Path


def _exe(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    state = tmp_path / "stub"
    (state / "hosts").mkdir(parents=True)
    (state / "hosts" / f"{_HOST}.env").write_text("WORKER_HOST_OS=Darwin\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(path=bin_dir / "kubectl", body=_STUB_KUBECTL)
    _exe(path=bin_dir / "pfsh", body=_STUB_PF_SHELL)
    (state / "calls.log").write_text("", encoding="utf-8")
    return _Env(state=state, bin_dir=bin_dir)


def _prove(
    *,
    env: _Env,
    args: list[str],
    tunnel_only: str,
    enforced: str = "1",
    dns: str = "1",
    mtu: str = "1",
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{env.bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(env.state),
            "HOMELAB_WORKER_HOSTS_DIR": str(env.state / "hosts"),
            "PORT_FORWARD_SHELL": str(env.bin_dir / "pfsh"),
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


_ALL_CHECKS = (
    "logs-on-worker",
    "exec-on-worker",
    "logs-on-peer-node",
    "kubelet-stats-on-worker",
    "port-forward-to-worker",
    "pod-to-pod-worker-to-peer",
    "pod-to-pod-peer-to-worker",
    "large-tcp-worker-to-peer",
    "large-tcp-peer-to-worker",
    "large-icmp-worker-to-peer",
    "clusterip-and-dns-from-worker",
    "cluster-dns-from-worker",
    "networkpolicy-deny-on-worker",
    "networkpolicy-lifted-on-worker",
)


def test_the_proof_passes_every_check_on_a_reachable_enforcing_worker(env: _Env) -> None:
    result = _prove(env=env, args=[_HOST, "--peer-node", _PEER], tunnel_only="0")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _proofs(result) == dict.fromkeys(_ALL_CHECKS, "PASS")
    assert "PASSED" in result.stdout


def test_cluster_dns_is_checked_at_the_kube_dns_service_address(env: _Env) -> None:
    _prove(env=env, args=[_HOST, "--peer-node", _PEER], tunnel_only="0")
    calls = (env.state / "calls.log").read_text(encoding="utf-8")
    assert "kubectl get service --namespace kube-system kube-dns" in calls
    assert f"nslookup kubernetes.default.svc.cluster.local {_DNS}" in calls


@pytest.mark.parametrize(
    ("tunnel_only", "enforced", "dns", "mtu", "failing"),
    [
        ("1", "1", "1", "1", "logs-on-worker"),
        ("1", "1", "1", "1", "port-forward-to-worker"),
        ("0", "0", "1", "1", "networkpolicy-deny-on-worker"),
        ("0", "1", "0", "1", "cluster-dns-from-worker"),
        ("0", "1", "1", "0", "large-icmp-worker-to-peer"),
    ],
)
def test_the_proof_fails_naming_any_check_that_fails(
    env: _Env, tunnel_only: str, enforced: str, dns: str, mtu: str, failing: str
) -> None:
    result = _prove(
        env=env,
        args=[_HOST, "--peer-node", _PEER],
        tunnel_only=tunnel_only,
        enforced=enforced,
        dns=dns,
        mtu=mtu,
    )
    assert result.returncode != 0
    assert _proofs(result)[failing] == "FAIL"
    assert "FAILED" in result.stderr


def test_the_negative_control_passes_only_when_streaming_to_the_worker_fails(env: _Env) -> None:
    args = [_HOST, "--peer-node", _PEER, "--expect-streaming-failure"]
    control = _prove(env=env, args=args, tunnel_only="1")
    assert control.returncode == 0, control.stdout + control.stderr
    assert _proofs(control) == {"logs-on-worker": "PASS", "exec-on-worker": "PASS"}
    reachable = _prove(env=env, args=args, tunnel_only="0")
    assert reachable.returncode != 0
    assert _proofs(reachable) == {"logs-on-worker": "FAIL", "exec-on-worker": "FAIL"}


def test_the_proof_pods_tolerate_the_hold_are_pinned_and_use_a_digest_pinned_image(
    env: _Env,
) -> None:
    _prove(env=env, args=[_HOST, "--peer-node", _PEER], tunnel_only="0")
    applied = (env.state / "applied.yaml").read_text(encoding="utf-8")
    assert applied.count(f"nodeName: {_WORKER}") == 2
    assert applied.count(f"nodeName: {_PEER}") == 2
    assert applied.count("key: homelab-worker.livespec.dev/admission") == 4
    images = set(re.findall(r"image: (\S+)", applied))
    assert images
    assert all(re.fullmatch(r"\S+@sha256:[0-9a-f]{64}", image) for image in images)
    calls = (env.state / "calls.log").read_text(encoding="utf-8")
    assert "kubectl delete namespace hw-proof" in calls


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["gamma", "--peer-node", _PEER], "is not declared"),
        ([_HOST], "--peer-node is required"),
        ([_HOST, "--peer-node", _PEER, "--mode", "x"], "unknown argument"),
    ],
)
def test_bad_arguments_are_refused_before_any_cluster_call(
    env: _Env, args: list[str], message: str
) -> None:
    result = _prove(env=env, args=args, tunnel_only="0")
    assert result.returncode != 0
    assert message in result.stderr
    assert (env.state / "calls.log").read_text(encoding="utf-8") == ""
