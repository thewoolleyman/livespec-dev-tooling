"""The VXLAN offload sweep, both directions, on a homelab worker (plan homelab-k8s-worker-nodes, livespec-dev-tooling-ko26ez).

`homelab-worker/prove-vxlan-offload.sh <host> --peer-node <node>` toggles one NIC offload at a time on a
homelab WORKER node and times a 32 MiB pod-network download into it and out of it under each. These
run it under `/bin/bash` against a stub `kubectl` that keeps each offload setting as a file and answers
the inbound download fast only while lima0's rx checksumming is off and the outbound download fast
only while lima0's tx-udp_tnl-segmentation is off, and assert:

- the sweep times the baseline and every candidate alone in both directions, never two toggles at
  once, and names the candidate that recovers each direction;
- every setting is read before the run and after the restore, with one receipt line each, and a
  restore that does not stick fails loudly and leaves the tuning pod in place;
- a setting ethtool reports as [fixed] is never toggled;
- the privileged hostNetwork tuning pod is placed only on a homelab worker node, by nodeSelector, and a
  Node without the worker class label is refused before anything is created.

Every value here is the stub's own; none is a production value.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

# Integration tier: each test runs the real script under /bin/bash against a stub kubectl.
pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "prove-vxlan-offload.sh"
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"
_PEER = "peer-node-1"

_INITIAL = {
    "lima0/rx-checksumming": "on",
    "lima0/generic-receive-offload": "on",
    "lima0/rx-udp-gro-forwarding": "off",
    "lima0/rx-gro-list": "off",
    "flannel.1/generic-receive-offload": "on",
    "lima0/tx-checksumming": "on",
    "lima0/tcp-segmentation-offload": "on",
    "lima0/generic-segmentation-offload": "on",
    "lima0/tx-udp_tnl-segmentation": "on",
    "flannel.1/tx-checksum-ip-generic": "on",
    "flannel.1/tcp-segmentation-offload": "on",
    "flannel.1/generic-segmentation-offload": "on",
    "flannel.1/tx-udp_tnl-segmentation": "off",
}

_STUB = r"""#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\n' "$*" >> "$s/calls.log"
feature_of() {
  case "$1" in
    rx) echo rx-checksumming ;;
    gro) echo generic-receive-offload ;;
    tx) echo tx-checksumming ;;
    tso) echo tcp-segmentation-offload ;;
    gso) echo generic-segmentation-offload ;;
    *) echo "$1" ;;
  esac
}
case "$1" in
  get)
    case "$2" in
      node) printf '%s' "$STUB_CLASS" ;;
      configmap) printf 'lima0' ;;
      pod) printf '10.99.1.20' ;;
    esac ;;
  apply) cat >> "$s/applied.yaml" ;;
  wait) exit 0 ;;
  delete) exit 0 ;;
  exec)
    pod="$4"
    shift 5
    if [ "$pod" = tune ]; then
      iface="$3"
      if [ "$2" = -k ]; then
        for f in "$s/nic/$iface"/*; do
          name="$(basename "$f")"
          if [ "$iface/$name" = "$STUB_FIXED" ]; then
            printf '%s: %s [fixed]\n' "$name" "$(cat "$f")"
          else
            printf '%s: %s\n' "$name" "$(cat "$f")"
          fi
        done
      else
        feature="$(feature_of "$4")"
        [ -f "$s/nic/$iface/$feature" ] || exit 1
        if [ "$5" = on ] && [ "$iface/$feature" = "$STUB_STICKY" ]; then exit 0; fi
        printf '%s' "$5" > "$s/nic/$iface/$feature"
      fi
      exit 0
    fi
    # the client's timed download: count settings that differ from the initial state
    changed=0
    while read -r key want; do
      [ "$(cat "$s/nic/$key")" = "$want" ] || changed=$((changed + 1))
    done < "$s/initial"
    [ "$changed" -le 1 ] || echo stacked >> "$s/stacked"
    echo "$pod" >> "$s/clients"
    if [ "$pod" = client-out ]; then
      fast="$(cat "$s/nic/lima0/tx-udp_tnl-segmentation")"
    else
      fast="$(cat "$s/nic/lima0/rx-checksumming")"
    fi
    if [ "$fast" = off ]; then echo '100.00 101.00'; else echo '100.00 200.00'; fi ;;
esac
exit 0
"""


def _run(
    *,
    tmp_path: Path,
    args: list[str] | None = None,
    worker_class: str = "worker",
    fixed: str = "",
    sticky: str = "",
) -> tuple[subprocess.CompletedProcess[str], Path]:
    state = tmp_path / "state"
    for key, value in _INITIAL.items():
        path = state / "nic" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value, encoding="utf-8")
    (state / "initial").write_text(
        "".join(f"{key} {value}\n" for key, value in _INITIAL.items()), encoding="utf-8"
    )
    (state / "calls.log").write_text("", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "kubectl"
    stub.write_text(_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    hosts = tmp_path / "hosts"
    hosts.mkdir(exist_ok=True)
    (hosts / f"{_HOST}.env").write_text("WORKER_HOST_OS=Darwin\n", encoding="utf-8")
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), *(args if args is not None else [_HOST, "--peer-node", _PEER])],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(state),
            "STUB_CLASS": worker_class,
            "STUB_FIXED": fixed,
            "STUB_STICKY": sticky,
            "HOMELAB_WORKER_HOSTS_DIR": str(hosts),
        },
        check=False,
        timeout=120,
    )
    return result, state


def _calls(state: Path) -> str:
    return (state / "calls.log").read_text(encoding="utf-8")


def test_the_sweep_times_each_candidate_alone_and_names_the_one_that_recovers(
    tmp_path: Path,
) -> None:
    result, state = _run(tmp_path=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert "PROOF-INFO offload in baseline 327 KiB/s (32768 KiB in 100.00 s)" in out
    assert "PROOF-INFO offload out baseline 327 KiB/s (32768 KiB in 100.00 s)" in out
    assert "PROOF-INFO offload in lima0:rx=off 32768 KiB/s (32768 KiB in 1.00 s)" in out
    assert "PROOF-INFO offload out lima0:rx=off 327 KiB/s" in out
    assert "PROOF-INFO offload in lima0:gro=off 327 KiB/s" in out
    assert "PROOF-INFO offload in flannel.1:tx-checksum-ip-generic=off 327 KiB/s" in out
    assert "PROOF-INFO offload in flannel.1:gro=off 327 KiB/s" in out
    assert "PROOF-INFO offload lima0:rx-udp-gro-forwarding=off already-off" in out
    assert "PROOF-INFO offload lima0:rx-gro-list=off already-off" in out
    assert not (state / "stacked").exists()


def test_the_sweep_times_the_outbound_direction_and_names_the_transmit_offload_that_recovers_it(
    tmp_path: Path,
) -> None:
    result, state = _run(tmp_path=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    out = result.stdout
    assert (
        "PROOF-INFO offload out lima0:tx-udp_tnl-segmentation=off 32768 KiB/s (32768 KiB in 1.00 s)"
        in out
    )
    assert "PROOF-INFO offload in lima0:tx-udp_tnl-segmentation=off 327 KiB/s" in out
    for label in (
        "lima0:tx=off",
        "lima0:tso=off",
        "lima0:gso=off",
        "flannel.1:tso=off",
        "flannel.1:gso=off",
    ):
        assert f"PROOF-INFO offload out {label} 327 KiB/s" in out
    assert "PROOF-INFO offload flannel.1:tx-udp_tnl-segmentation=off already-off" in out
    clients = (state / "clients").read_text(encoding="utf-8").split()
    assert clients.count("client") == clients.count("client-out") > 1
    assert not (state / "stacked").exists()


def test_every_setting_is_read_back_after_the_restore_with_a_receipt(tmp_path: Path) -> None:
    result, state = _run(tmp_path=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    receipts = [line for line in result.stdout.splitlines() if line.startswith("PROOF-RECEIPT ")]
    assert len(receipts) == len(_INITIAL)
    assert all(line.endswith(" ok") for line in receipts)
    assert "PROOF-RECEIPT lima0 rx-checksumming before=on after=on ok" in receipts
    for key, value in _INITIAL.items():
        assert (state / "nic" / key).read_text(encoding="utf-8") == value
    assert "PROOF-INFO before lima0 rx-checksumming on" in result.stdout
    assert "kubectl delete namespace hw-offload-proof" in _calls(state)


def test_a_restore_that_does_not_stick_fails_loudly_and_leaves_the_tuning_pod(
    tmp_path: Path,
) -> None:
    result, state = _run(tmp_path=tmp_path, sticky="lima0/generic-receive-offload")
    assert result.returncode != 0
    assert (
        "PROOF-RECEIPT lima0 generic-receive-offload before=on after=off MISMATCH" in result.stdout
    )
    assert "RESTORE MISMATCH" in result.stderr
    assert "delete namespace" not in _calls(state)


def test_a_fixed_setting_is_reported_unsupported_and_never_toggled(tmp_path: Path) -> None:
    result, state = _run(tmp_path=tmp_path, fixed="flannel.1/tx-checksum-ip-generic")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "PROOF-INFO offload flannel.1:tx-checksum-ip-generic=off unsupported (fixed)"
        in result.stdout
    )
    assert "ethtool -K flannel.1 tx-checksum-ip-generic" not in _calls(state)


def test_the_privileged_tuning_pod_is_placed_only_on_a_homelab_worker_node(tmp_path: Path) -> None:
    result, state = _run(tmp_path=tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    applied = (state / "applied.yaml").read_text(encoding="utf-8")
    tune = applied.split("name: tune", 1)[1].split("---", 1)[0]
    assert "hostNetwork: true" in tune
    assert "privileged: true" in tune
    assert "homelab-worker.livespec.dev/class: worker" in tune
    assert f"kubernetes.io/hostname: {_WORKER}" in tune
    assert "nodeName" not in tune
    server = applied.split("name: server\n", 1)[1].split("---", 1)[0]
    assert "privileged" not in server
    assert "hostNetwork" not in server
    assert f"nodeName: {_PEER}" in server
    server_out = applied.split("name: server-out", 1)[1].split("---", 1)[0]
    assert "privileged" not in server_out
    assert "hostNetwork" not in server_out
    assert f"kubernetes.io/hostname: {_WORKER}" in server_out
    client_out = applied.split("name: client-out", 1)[1]
    assert "privileged" not in client_out
    assert "hostNetwork" not in client_out
    assert f"nodeName: {_PEER}" in client_out


def test_a_node_without_the_worker_class_is_refused_before_anything_is_created(
    tmp_path: Path,
) -> None:
    result, state = _run(tmp_path=tmp_path, worker_class="")
    assert result.returncode != 0
    assert "runs only on homelab worker nodes" in result.stderr
    assert not (state / "applied.yaml").exists()
    assert "ethtool" not in _calls(state)


@pytest.mark.parametrize(
    "args",
    [["undeclared", "--peer-node", _PEER], [_HOST], [_HOST, "--peer-node", _PEER, "--x"]],
)
def test_bad_arguments_are_refused_before_any_cluster_call(tmp_path: Path, args: list[str]) -> None:
    result, state = _run(tmp_path=tmp_path, args=args)
    assert result.returncode != 0
    assert _calls(state) == ""
