"""The removal of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

`homelab-worker/remove-worker.sh` is the counterpart of `join-worker.sh`: it takes a host's worker
out of whatever cluster the caller's `kubectl` reaches, so that the next join is a fresh enrollment.
These run it under the system `/bin/bash` against a stub `kubectl` and a stub `limactl` that plays
the worker VM over a mocked state root on disk, and assert:

- an uncordoned Node, or a Node still carrying a pod no DaemonSet owns, is refused with no write;
- the removal stops the kubelet, deletes the Node, clears the node credentials and the delivered
  enrollment, then converges the worker queues, in that order, and keeps every other state file;
- a rerun for a Node already gone still clears the credentials and converges the queues;
- a failed read (kubectl or the VM) is named, and nothing is changed;
- an undeclared host or an unknown argument is refused before any cluster or VM call.

Every value here is the stub's own; none is a production value.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_HW = Path(__file__).resolve().parents[2] / "homelab-worker"
_SCRIPT = _HW / "remove-worker.sh"
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"

# The Node is the file $STUB_STATE/node, holding its spec.unschedulable value; the pods on it
# are the lines of $STUB_STATE/pods. KUBECTL_FAILS names the read ("node" or "pods") that fails.
_STUB_KUBECTL = """#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\\n' "$*" >> "$s/calls.log"
case "$1 $2" in
  "get node")
    [ "$KUBECTL_FAILS" != node ] || { echo "Connection closed" >&2; exit 255; }
    [ ! -f "$s/node" ] || printf '%s %s' "$3" "$(cat "$s/node")" ;;
  "get pods")
    [ "$KUBECTL_FAILS" != pods ] || { echo "Connection closed" >&2; exit 255; }
    cat "$s/pods" 2>/dev/null ;;
  "delete node") rm -f "$s/node" ;;
esac
exit 0
"""

# The worker container is the file $STUB_STATE/container, holding its State.Running value. `rm`
# really runs, against the mocked state root.
_STUB_LIMACTL = """#!/bin/bash
s="$STUB_STATE"
printf 'limactl %s\\n' "$*" >> "$s/calls.log"
[ -z "$VM_UNREACHABLE" ] || exit 1
shift 5
case "$1 $2" in
  "docker inspect") cat "$s/container" 2>/dev/null || exit 1 ;;
  "rm -rf") exec "$@" ;;
esac
exit 0
"""

_CLEARED = (
    "kubelet/kubeconfig",
    "kubelet/pki/kubelet-client-current.pem",
    "kubelet/pki/kubelet-server-current.pem",
    "enrollment/bootstrap-kubeconfig",
    "enrollment/client-ca.crt",
)
_KEPT = (
    "containerd/io.containerd.metadata.v1.bolt/meta.db",
    "kubelet/pods/a/volume",
    "kubelet/cpu_manager_state",
    "tailscale/tailscaled.state",
    "telemetry/config.yaml",
    "telemetry/.env",
    "ci/storage/pvc-a/file",
    "enrollment/kubelet-config.yaml",
    "enrollment/kubelet.env",
)


@dataclass(frozen=True, kw_only=True)
class _Env:
    state: Path
    bin_dir: Path
    root: Path


def _exe(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    """A cordoned, idle, registered worker with a running container and a populated state root."""
    state = tmp_path / "stub"
    (state / "hosts").mkdir(parents=True)
    (state / "hosts" / f"{_HOST}.env").write_text("WORKER_HOST_OS=Darwin\n", encoding="utf-8")
    (state / "calls.log").write_text("", encoding="utf-8")
    (state / "node").write_text("true", encoding="utf-8")
    (state / "pods").write_text(
        "kube-system/flannel-x Running DaemonSet\nci/done-job-x Succeeded Job\n", encoding="utf-8"
    )
    (state / "container").write_text("true\n", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(path=bin_dir / "kubectl", body=_STUB_KUBECTL)
    _exe(path=bin_dir / "limactl", body=_STUB_LIMACTL)
    _exe(
        path=bin_dir / "worker-queues",
        body='#!/bin/bash\nprintf "worker-queues\\n" >> "$STUB_STATE/calls.log"\n',
    )
    root = tmp_path / "w"
    for name in (*_CLEARED, *_KEPT):
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text("x", encoding="utf-8")
    return _Env(state=state, bin_dir=bin_dir, root=root)


def _run(
    *,
    env: _Env,
    args: list[str] | None = None,
    kubectl_fails: str = "",
    vm_unreachable: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "/bin/bash",
            str(_SCRIPT),
            *([_HOST, "--state-root", str(env.root)] if args is None else args),
        ],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{env.bin_dir}:/usr/bin:/bin",
            "HOMELAB_WORKER_HOSTS_DIR": str(env.state / "hosts"),
            "STUB_STATE": str(env.state),
            "WORKER_QUEUES_CONVERGE": str(env.bin_dir / "worker-queues"),
            "KUBECTL_FAILS": kubectl_fails,
            "VM_UNREACHABLE": "1" if vm_unreachable else "",
        },
        check=False,
        timeout=60,
    )


def _calls(*, env: _Env) -> list[str]:
    return (env.state / "calls.log").read_text(encoding="utf-8").splitlines()


def _writes(*, env: _Env) -> list[str]:
    """Every recorded call that changes the cluster, the VM or the queues."""
    return [
        c
        for c in _calls(env=env)
        if c.startswith("kubectl delete")
        or " systemctl " in c
        or " rm " in c
        or c == "worker-queues"
    ]


def _index(*, env: _Env, fragment: str) -> int:
    [index] = [i for i, c in enumerate(_calls(env=env)) if fragment in c]
    return index


def _assert_untouched(*, env: _Env) -> None:
    assert _writes(env=env) == []
    assert (env.state / "node").exists()
    assert all((env.root / name).exists() for name in (*_CLEARED, *_KEPT))


def test_an_uncordoned_node_is_refused_and_nothing_is_changed(env: _Env) -> None:
    (env.state / "node").write_text("", encoding="utf-8")
    result = _run(env=env)
    assert result.returncode != 0
    assert f"Node {_WORKER} is not cordoned" in result.stderr
    assert "Nothing was changed" in result.stderr
    _assert_untouched(env=env)


@pytest.mark.parametrize("phase", ["Running", "Pending"])
def test_a_pod_no_daemonset_owns_refuses_the_removal_and_is_named(env: _Env, phase: str) -> None:
    with (env.state / "pods").open("a", encoding="utf-8") as pods:
        pods.write(f"arc-runners/runner-abc {phase} EphemeralRunner\nci/bare-pod {phase} \n")
    result = _run(env=env)
    assert result.returncode != 0
    assert "arc-runners/runner-abc ci/bare-pod" in result.stderr
    assert "flannel-x" not in result.stderr
    assert "done-job-x" not in result.stderr
    _assert_untouched(env=env)


def test_the_removal_stops_the_kubelet_deletes_the_node_clears_and_converges_in_order(
    env: _Env,
) -> None:
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    in_vm = f"limactl shell --workdir / {_WORKER} sudo "
    assert f"{in_vm}docker exec {_WORKER} systemctl stop kubelet" in _calls(env=env)
    assert f"kubectl delete node {_WORKER} --wait --ignore-not-found" in _calls(env=env)
    order = [
        _index(env=env, fragment="systemctl stop kubelet"),
        _index(env=env, fragment="kubectl delete node"),
        _index(env=env, fragment=" rm -rf "),
        _index(env=env, fragment="worker-queues"),
    ]
    assert order == sorted(order)
    reads = ("kubectl get ", f"{in_vm}true", f"{in_vm}docker inspect ")
    assert all(c.startswith(reads) for c in _calls(env=env)[: order[0]])
    assert not (env.state / "node").exists()


def test_the_removal_clears_only_the_credentials_and_keeps_all_other_state(env: _Env) -> None:
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert [name for name in _CLEARED if (env.root / name).exists()] == []
    assert not (env.root / "kubelet" / "pki").exists()
    assert [name for name in _KEPT if not (env.root / name).exists()] == []
    [clear] = [c for c in _calls(env=env) if " rm -rf " in c]
    assert clear.split(" rm -rf -- ")[1].split() == [
        f"{env.root}/kubelet/kubeconfig",
        f"{env.root}/kubelet/pki",
        f"{env.root}/enrollment/bootstrap-kubeconfig",
        f"{env.root}/enrollment/client-ca.crt",
    ]


def test_the_removal_ends_with_the_join_command_that_rejoins_the_worker(env: _Env) -> None:
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-2:] == [
        f"remove-worker:   homelab-worker/join-worker.sh {_HOST} --api-server <url>"
        f" --server-ca <file> --state-root {env.root}",
        "remove-worker: The rejoined worker registers under the admission hold;"
        f" homelab-worker/lift-admission-hold.sh {_HOST} lifts it.",
    ]


def test_a_rerun_with_the_node_already_gone_still_clears_and_converges(env: _Env) -> None:
    (env.state / "node").unlink()
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "not registered" in result.stdout
    assert not [c for c in _calls(env=env) if c.startswith("kubectl delete")]
    assert [name for name in _CLEARED if (env.root / name).exists()] == []
    assert _calls(env=env)[-1] == "worker-queues"
    again = _run(env=env)
    assert again.returncode == 0, again.stdout + again.stderr
    assert _calls(env=env)[-1] == "worker-queues"


@pytest.mark.parametrize("container", [None, "false\n"])
def test_an_absent_or_stopped_container_has_no_kubelet_to_stop(
    env: _Env, container: str | None
) -> None:
    if container is None:
        (env.state / "container").unlink()
    else:
        (env.state / "container").write_text(container, encoding="utf-8")
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not [c for c in _calls(env=env) if " systemctl " in c]
    assert "absent or stopped" in result.stdout
    assert not (env.state / "node").exists()
    assert [name for name in _CLEARED if (env.root / name).exists()] == []


@pytest.mark.parametrize(
    ("read", "named"),
    [("node", f"could not read Node {_WORKER}"), ("pods", "could not read the pods on Node")],
)
def test_a_failed_kubectl_read_is_named_and_nothing_is_changed(
    env: _Env, read: str, named: str
) -> None:
    result = _run(env=env, kubectl_fails=read)
    assert result.returncode != 0
    assert named in result.stderr
    assert "nothing was changed" in result.stderr
    _assert_untouched(env=env)


def test_an_unreachable_vm_is_named_before_the_node_is_deleted(env: _Env) -> None:
    result = _run(env=env, vm_unreachable=True)
    assert result.returncode != 0
    assert f"could not reach VM {_WORKER}" in result.stderr
    _assert_untouched(env=env)


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["gamma"], "is not declared"),
        (["Bad_Host"], "is not a valid host name"),
        ([_HOST, "--mode", "x"], "unknown argument"),
        ([_HOST, "--state-root"], "needs a value"),
        ([_HOST, "--state-root", "relative/dir"], "is not an absolute directory path"),
        ([], "usage: remove-worker <host>"),
    ],
)
def test_bad_arguments_are_refused_before_any_cluster_or_vm_call(
    env: _Env, args: list[str], message: str
) -> None:
    result = _run(env=env, args=args)
    assert result.returncode != 0
    assert message in result.stderr
    assert _calls(env=env) == []
