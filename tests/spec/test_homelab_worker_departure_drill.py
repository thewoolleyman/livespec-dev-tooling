"""The departure drill of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

"Departure and rejoin" requires that work on a worker that leaves without warning is not lost, and
that the worker rejoins and re-enrolls with no operator step. `homelab-worker/departure-drill.sh`
is the measured departure. These run it under the system `/bin/bash` against a stub `kubectl`, a
stub `limactl` that plays the worker VM, and a stub `sleep` that returns at once, and assert:

- an undeclared host, a bad mode, a bad hold or a bad argument is refused before any call;
- an absent, NotReady or cordoned Node, a failed read or an unreachable VM is refused, and the
  worker never departs;
- power-loss mode forces the VM off, holds, then starts it, in that order, and writes nothing else;
- network-loss mode takes the VM's LAN interface down and up, and never stops the VM;
- the hold lasts the asked time and names the moment Ready left True;
- each captured pod is classified from the read-back, a sibling that already existed is not taken
  for a replacement, and each owning Job's counts are printed before and after;
- a Node that does not return Ready, or returns with another uid, label, churn-slot value or
  taint, fails the run, as does a hold in which Ready never left True;
- a collector whose recorded endpoint is not on the current cni0 address, or does not listen,
  fails the run on a COLLECTOR line;
- a step that fails after the departure still attempts the return.

Every value here is the stub's own; none is a production value.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.hang_guard import run_under_hang_guard

__all__: list[str] = []

pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "departure-drill.sh"
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"
_OTHER = "beta"
_CLASS = "homelab-worker.livespec.dev/class=worker:NoSchedule"
_IN_VM = f"limactl shell --workdir / {_WORKER} sudo "

# The cluster has three phases: before the departure, away (the file $STUB_STATE/departed
# exists) and back (the file $STUB_STATE/returned exists). A read answers from "<file>.away" or
# "<file>.back" in those phases when that file exists, and from "<file>" otherwise. The Node is
# the file "node", holding every field after its name; the pods are the lines of "pods"; a Job
# is "jobs/<namespace>.<name>". KUBECTL_FAILS names the read that fails: "node", "pods" (before
# the departure) or "pods.away".
_STUB_KUBECTL = """#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\\n' "$*" >> "$s/calls.log"
phase=""
[ ! -f "$s/departed" ] || phase=".away"
[ ! -f "$s/returned" ] || phase=".back"
pick() { if [ -f "$1$phase" ]; then cat "$1$phase"; elif [ -f "$1" ]; then cat "$1"; fi; }
case "$1 $2" in
  "get node")
    [ "$KUBECTL_FAILS" != node ] || { echo "Connection closed" >&2; exit 255; }
    body="$(pick "$s/node")"
    [ -z "$body" ] || printf '%s|%s' "$3" "$body" ;;
  "get pods")
    [ "$KUBECTL_FAILS" != "pods$phase" ] || { echo "Connection closed" >&2; exit 255; }
    pick "$s/pods" ;;
  "get job") pick "$s/jobs/$5.$3" ;;
esac
exit 0
"""

# `stop` and `ip link set ... down` are the departure, `start` and `... up` the return. The
# worker container is the file "container", its cni0 address line the file "cni0", and its
# listening sockets the file "listeners". `cat` really runs, against the mocked state root.
_STUB_LIMACTL = """#!/bin/bash
s="$STUB_STATE"
printf 'limactl %s\\n' "$*" >> "$s/calls.log"
case "$1" in
  stop) : > "$s/departed"; exit 0 ;;
  start)
    [ -z "$START_FAILS" ] || exit 1
    : > "$s/returned"; exit 0 ;;
esac
[ -z "$VM_UNREACHABLE" ] || exit 1
shift 5
case "$*" in
  "ip link set dev lima0 down") : > "$s/departed" ;;
  "ip link set dev lima0 up") : > "$s/returned" ;;
  "docker inspect "*) cat "$s/container" ;;
  "cat "*) exec "$@" ;;
  *"addr show dev cni0")
    if [ -f "$s/returned" ] && [ -f "$s/cni0.back" ]; then cat "$s/cni0.back"; else cat "$s/cni0"; fi ;;
  *"ss -Hltn")
    # "listeners.back" is what listens from the SECOND read after the return on.
    if [ -f "$s/returned" ] && [ -f "$s/listeners.back" ]; then
      n="$(($(cat "$s/ss.count" 2>/dev/null || echo 0) + 1))"
      echo "$n" > "$s/ss.count"
      if [ "$n" -ge 2 ]; then cat "$s/listeners.back"; else cat "$s/listeners"; fi
    else
      cat "$s/listeners"
    fi ;;
esac
exit 0
"""

_STUB_SLEEP = """#!/bin/bash
printf 'sleep %s\\n' "$*" >> "$STUB_STATE/calls.log"
"""

# namespace|name|uid|phase|node|owner kinds|owner names|restart counts
_PODS_BEFORE = (
    f"ci|gate-a-1|u-gate-1|Running|{_WORKER}|Job|gate-a|0",
    f"arc|runner-b|u-runner|Running|{_WORKER}|EphemeralRunner|runner-b|1 2",
    f"ci|done-c-1|u-done|Succeeded|{_WORKER}|Job|done-c|0",
    f"ci|bare|u-bare|Running|{_WORKER}|||0",
    f"ci|crash-d-1|u-crash|Running|{_WORKER}|Job|crash-d|0",
    f"kube-system|flannel-x|u-flannel-x|Running|{_WORKER}|DaemonSet|flannel|0",
    f"kube-system|flannel-y|u-flannel-y|Running|{_OTHER}|DaemonSet|flannel|0",
)
_PODS_AWAY = (
    f"ci|gate-a-1|u-gate-1|Running|{_WORKER}|Job|gate-a|0",
    f"ci|gate-a-2|u-gate-2|Running|{_OTHER}|Job|gate-a|0",
    f"arc|runner-b|u-runner|Running|{_WORKER}|EphemeralRunner|runner-b|1 2",
    f"ci|done-c-1|u-done|Succeeded|{_WORKER}|Job|done-c|0",
    f"ci|crash-d-1|u-crash|Failed|{_WORKER}|Job|crash-d|0",
    f"kube-system|flannel-x|u-flannel-x|Running|{_WORKER}|DaemonSet|flannel|0",
    f"kube-system|flannel-y|u-flannel-y|Running|{_OTHER}|DaemonSet|flannel|0",
)


@dataclass(frozen=True, kw_only=True)
class _Env:
    state: Path
    bin_dir: Path
    root: Path


def _exe(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _node(
    *,
    uid: str = "u-node",
    ready: str = "True",
    unschedulable: str = "",
    role: str = "arc-runner-host",
    slots: str = "6",
    taints: str = f"{_CLASS} ",
) -> str:
    """Every field of the stub Node after its name, as the script's jsonpath prints them."""
    return f"{uid}|{ready}|{unschedulable}|{role}|true|4000|{slots}|{taints}"


@pytest.fixture
def env(tmp_path: Path) -> _Env:
    """A Ready, uncordoned, enrolled worker carrying pods, which goes Unknown while it is away."""
    state = tmp_path / "stub"
    (state / "hosts").mkdir(parents=True)
    (state / "jobs").mkdir()
    (state / "hosts" / f"{_HOST}.env").write_text("WORKER_HOST_OS=Darwin\n", encoding="utf-8")
    (state / "calls.log").write_text("", encoding="utf-8")
    (state / "node").write_text(_node(), encoding="utf-8")
    (state / "node.away").write_text(_node(ready="Unknown"), encoding="utf-8")
    (state / "pods").write_text("\n".join(_PODS_BEFORE) + "\n", encoding="utf-8")
    (state / "pods.away").write_text("\n".join(_PODS_AWAY) + "\n", encoding="utf-8")
    (state / "jobs" / "ci.gate-a").write_text("j-gate||0|1|", encoding="utf-8")
    (state / "jobs" / "ci.done-c").write_text("j-done|1|||", encoding="utf-8")
    (state / "jobs" / "ci.crash-d").write_text("j-crash|||1|", encoding="utf-8")
    (state / "jobs" / "ci.crash-d.away").write_text("", encoding="utf-8")
    (state / "container").write_text("true\n", encoding="utf-8")
    (state / "cni0").write_text(
        "5: cni0    inet 10.9.5.1/24 brd 10.9.5.255 scope global cni0\n", encoding="utf-8"
    )
    (state / "listeners").write_text(
        "LISTEN 0 4096 127.0.0.1:10248 0.0.0.0:*\nLISTEN 0 4096 10.9.5.1:4319 0.0.0.0:*\n",
        encoding="utf-8",
    )
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(path=bin_dir / "kubectl", body=_STUB_KUBECTL)
    _exe(path=bin_dir / "limactl", body=_STUB_LIMACTL)
    _exe(path=bin_dir / "sleep", body=_STUB_SLEEP)
    root = tmp_path / "w"
    (root / "telemetry").mkdir(parents=True)
    (root / "telemetry" / "node.env").write_text(
        f"WORKER_NODE_NAME={_WORKER}\nOTLP_PODS_ENDPOINT=10.9.5.1:4319\n", encoding="utf-8"
    )
    return _Env(state=state, bin_dir=bin_dir, root=root)


def _run(
    *,
    env: _Env,
    args: list[str] | None = None,
    mode: str = "power-loss",
    hold: str = "60",
    wait: str = "30",
    stub_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    default = [
        _HOST,
        "--confirm-depart",
        _WORKER,
        "--mode",
        mode,
        "--hold-seconds",
        hold,
        "--state-root",
        str(env.root),
    ]
    return run_under_hang_guard(
        ["/bin/bash", str(_SCRIPT), *(default if args is None else args)],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{env.bin_dir}:/usr/bin:/bin",
            "HOMELAB_WORKER_HOSTS_DIR": str(env.state / "hosts"),
            "STUB_STATE": str(env.state),
            "POLL_SECONDS": "25",
            "WAIT_SECONDS": wait,
            "KUBECTL_FAILS": "",
            "VM_UNREACHABLE": "",
            "START_FAILS": "",
            **({} if stub_env is None else stub_env),
        },
        check=False,
    )


def _calls(*, env: _Env) -> list[str]:
    return (env.state / "calls.log").read_text(encoding="utf-8").splitlines()


def _changes(*, env: _Env) -> list[str]:
    """Every recorded call that is not a read or a sleep."""
    reads = (
        "kubectl get ",
        "sleep ",
        f"{_IN_VM}true",
        f"{_IN_VM}cat ",
        f"{_IN_VM}docker inspect ",
        f"{_IN_VM}docker exec {_WORKER} ip -4 -o addr show dev cni0",
        f"{_IN_VM}docker exec {_WORKER} ss -Hltn",
        f"{_IN_VM}ip link show dev lima0",
    )
    return [c for c in _calls(env=env) if not c.startswith(reads)]


def _report(*, result: subprocess.CompletedProcess[str], subject: str) -> str:
    """The one line of the run's report that names <subject>."""
    [line] = [text for text in result.stdout.splitlines() if subject in text]
    return line


@pytest.mark.parametrize(
    ("args", "message"),
    [
        (["gamma"], "is not declared"),
        (["Bad_Host"], "is not a valid host name"),
        ([_HOST, "--mode", "sleep"], "is not power-loss or network-loss"),
        ([_HOST, "--hold-seconds", "ten"], "is not a whole number of seconds"),
        ([_HOST, "--hold-seconds", "060"], "is not a whole number of seconds"),
        ([_HOST, "--hold-seconds", "59"], "is outside 60 to 3600 seconds"),
        ([_HOST, "--hold-seconds", "3601"], "is outside 60 to 3600 seconds"),
        ([_HOST, "--hold-seconds", "99999999999999999999"], "is outside 60 to 3600 seconds"),
        ([_HOST, "--drain", "yes"], "unknown argument"),
        ([_HOST, "--mode"], "needs a value"),
        ([_HOST, "--state-root", "relative/dir"], "is not an absolute directory path"),
        ([], "usage: departure-drill <host> --confirm-depart <host>-homelab-worker"),
        ([_HOST], f"it needs --confirm-depart {_WORKER} (got 'nothing')"),
        (
            [_HOST, "--confirm-depart", f"{_OTHER}-homelab-worker"],
            f"it needs --confirm-depart {_WORKER} (got '{_OTHER}-homelab-worker')",
        ),
        ([_HOST, "--confirm-depart", _HOST], f"it needs --confirm-depart {_WORKER}"),
    ],
)
def test_bad_arguments_are_refused_before_any_cluster_or_vm_call(
    env: _Env, args: list[str], message: str
) -> None:
    result = _run(env=env, args=args)
    assert result.returncode != 0
    assert message in result.stderr
    assert _calls(env=env) == []


@pytest.mark.parametrize(
    ("node", "message"),
    [
        (_node(unschedulable="true"), f"Node {_WORKER} is cordoned"),
        (_node(ready="False"), f"Node {_WORKER} is not Ready (its Ready condition is 'False')"),
        ("", f"Node {_WORKER} is not registered"),
    ],
)
def test_a_cordoned_notready_or_absent_node_is_refused_and_the_worker_never_departs(
    env: _Env, node: str, message: str
) -> None:
    (env.state / "node").write_text(node, encoding="utf-8")
    result = _run(env=env)
    assert result.returncode != 0
    assert message in result.stderr
    assert "Nothing was changed" in result.stderr
    assert _changes(env=env) == []


@pytest.mark.parametrize(
    ("stub_env", "mode", "message"),
    [
        ({"KUBECTL_FAILS": "node"}, "power-loss", f"could not read Node {_WORKER}"),
        ({"KUBECTL_FAILS": "pods"}, "power-loss", "could not read the cluster's pods"),
        ({"VM_UNREACHABLE": "1"}, "power-loss", f"could not reach VM {_WORKER}"),
        ({"VM_UNREACHABLE": "1"}, "network-loss", f"could not reach VM {_WORKER}"),
    ],
)
def test_a_failed_read_is_named_and_the_worker_never_departs(
    env: _Env, stub_env: dict[str, str], mode: str, message: str
) -> None:
    result = _run(env=env, mode=mode, stub_env=stub_env)
    assert result.returncode != 0
    assert message in result.stderr
    assert "nothing was changed" in result.stderr
    assert _changes(env=env) == []


def test_power_loss_forces_the_vm_off_then_starts_it_and_writes_nothing_else(env: _Env) -> None:
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _changes(env=env) == [
        f"limactl stop --force {_WORKER}",
        f"limactl start --tty=false {_WORKER}",
    ]
    stop = _calls(env=env).index(f"limactl stop --force {_WORKER}")
    assert all(not c.startswith("sleep ") for c in _calls(env=env)[:stop])
    assert "rejoined as it was" in result.stdout.splitlines()[-2]
    assert "COLLECTOR endpoint 10.9.5.1:4319 matches cni0 (10.9.5.1) and is listening" in (
        result.stdout
    )


def test_network_loss_takes_the_lan_interface_down_then_up_and_never_stops_the_vm(
    env: _Env,
) -> None:
    result = _run(env=env, mode="network-loss")
    assert result.returncode == 0, result.stdout + result.stderr
    assert _changes(env=env) == [
        f"{_IN_VM}ip link set dev lima0 down",
        f"{_IN_VM}ip link set dev lima0 up",
    ]
    assert f"{_IN_VM}ip link show dev lima0" in _calls(env=env)


def test_the_before_record_names_the_node_its_enrollment_its_pods_and_their_jobs(
    env: _Env,
) -> None:
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    departed = result.stdout.index("departure-drill: DEPARTED at ")
    before = result.stdout[:departed].splitlines()
    assert before[:6] == [
        f"departure-drill: BEFORE Node {_WORKER}: uid=u-node Ready=True taints=[{_CLASS}]",
        "departure-drill: BEFORE enrollment: k3s-role=arc-runner-host ci-runner.io/factory=true"
        " gate-share-millicores=4000 churn-slot=6",
        "departure-drill: BEFORE collector: node.env endpoint=10.9.5.1:4319 cni0=10.9.5.1"
        " listening=true",
        "departure-drill: BEFORE pods on the node: 6",
        "departure-drill:   pod ci/gate-a-1 phase=Running owner=Job/gate-a restarts=0",
        "departure-drill:   pod arc/runner-b phase=Running owner=EphemeralRunner/runner-b"
        " restarts=3",
    ]
    assert "departure-drill:   pod ci/bare phase=Running owner=<none> restarts=0" in before
    assert not [line for line in before if "flannel-y" in line]
    assert before[-4:] == [
        "departure-drill: BEFORE Jobs that own them: 3",
        "departure-drill:   job ci/crash-d succeeded=0 failed=0 active=1 suspended=false"
        " uid=j-crash",
        "departure-drill:   job ci/done-c succeeded=1 failed=0 active=0 suspended=false uid=j-done",
        "departure-drill:   job ci/gate-a succeeded=0 failed=0 active=1 suspended=false uid=j-gate",
    ]


def test_the_hold_lasts_the_asked_time_and_names_when_ready_left_true(env: _Env) -> None:
    result = _run(env=env, hold="60")
    assert result.returncode == 0, result.stdout + result.stderr
    calls = _calls(env=env)
    held = calls[
        calls.index(f"limactl stop --force {_WORKER}") : calls.index(
            f"limactl start --tty=false {_WORKER}"
        )
    ]
    assert [c for c in held if c.startswith("sleep ")] == ["sleep 25", "sleep 25", "sleep 10"]
    assert "Ready condition left True (now 'Unknown') within 25s of the departure" in result.stdout
    assert "no cordon, no drain. Holding 60s" in result.stdout


def test_each_captured_pod_is_classified_from_the_read_back(env: _Env) -> None:
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    prefix = "departure-drill:   "
    assert [
        _report(result=result, subject=f"pod {pod} was")
        for pod in (
            "ci/gate-a-1",
            "arc/runner-b",
            "ci/done-c-1",
            "ci/bare",
            "ci/crash-d-1",
            "kube-system/flannel-x",
        )
    ] == [
        f"{prefix}replaced-elsewhere: pod ci/gate-a-1 was Running, now phase=Running"
        f" node={_WORKER}; replacement on another node: ci/gate-a-2 on {_OTHER} (Running)",
        f"{prefix}still-bound-to-the-departed-node: pod arc/runner-b was Running, now"
        f" phase=Running node={_WORKER}; replacement on another node: none",
        f"{prefix}finished-before-departure: pod ci/done-c-1 was Succeeded, now phase=Succeeded"
        f" node={_WORKER}; replacement on another node: none",
        f"{prefix}gone: pod ci/bare was Running, now pod gone; replacement on another node: none",
        f"{prefix}failed: pod ci/crash-d-1 was Running, now phase=Failed node={_WORKER};"
        " replacement on another node: none",
        f"{prefix}still-bound-to-the-departed-node: pod kube-system/flannel-x was Running, now"
        f" phase=Running node={_WORKER}; replacement on another node: none",
    ]


def test_each_owning_job_is_read_back_beside_its_before_counts(env: _Env) -> None:
    (env.state / "jobs" / "ci.gate-a.away").write_text("j-gate||1|1|true", encoding="utf-8")
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _report(result=result, subject="job ci/gate-a was") == (
        "departure-drill:   job ci/gate-a was succeeded=0 failed=0 active=1 suspended=false"
        " uid=j-gate; now succeeded=0 failed=1 active=1 suspended=true uid=j-gate"
    )
    assert _report(result=result, subject="job ci/crash-d was").endswith("; now gone")


def test_a_pod_reported_finished_or_failed_at_capture_keeps_that_class(env: _Env) -> None:
    (env.state / "pods").write_text(
        f"ci|late|u-late|Running|{_WORKER}|Job|late|0\nci|dead|u-dead|Failed|{_WORKER}|Job|dead|0\n",
        encoding="utf-8",
    )
    (env.state / "pods.away").write_text(
        f"ci|late|u-late|Succeeded|{_WORKER}|Job|late|0\n", encoding="utf-8"
    )
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _report(result=result, subject="pod ci/late was").startswith(
        "departure-drill:   finished-before-departure: pod ci/late was Running"
    )
    assert _report(result=result, subject="pod ci/dead was").startswith(
        "departure-drill:   failed: pod ci/dead was Failed, now pod gone"
    )


def test_a_node_that_does_not_return_ready_fails_after_the_return_was_attempted(
    env: _Env,
) -> None:
    (env.state / "node.back").write_text(_node(ready="Unknown"), encoding="utf-8")
    result = _run(env=env, wait="50")
    assert result.returncode != 0
    assert f"limactl start --tty=false {_WORKER}" in _calls(env=env)
    assert f"Node {_WORKER} did not return Ready within 50s of the return step" in result.stderr
    assert "the enrollment and collector read-back was not taken" in result.stdout
    calls = _calls(env=env)
    waited = calls[calls.index(f"limactl start --tty=false {_WORKER}") :]
    assert [c for c in waited if c.startswith("sleep ")] == ["sleep 25", "sleep 25"]


def test_a_hold_in_which_ready_never_left_true_measured_no_departure(env: _Env) -> None:
    (env.state / "node.away").unlink()
    result = _run(env=env, mode="network-loss")
    assert result.returncode != 0
    assert "never left True in the 60s hold" in result.stdout
    assert "no departure was measured" in result.stderr
    assert _changes(env=env)[-1] == f"{_IN_VM}ip link set dev lima0 up"


@pytest.mark.parametrize(
    ("back", "difference"),
    [
        (
            _node(uid="u-new"),
            "node uid changed: was u-node, now u-new (the Node was registered anew)",
        ),
        (_node(role=""), "label k3s-role: was 'arc-runner-host', now ''"),
        (_node(slots=""), "ci-runner.io/churn-slot allocatable: was '6', now ''"),
        (
            _node(taints=f"{_CLASS} homelab-worker.livespec.dev/admission=hold:NoSchedule "),
            f"taints: were [{_CLASS}], now [homelab-worker.livespec.dev/admission=hold:NoSchedule"
            f" {_CLASS}]",
        ),
        (_node(unschedulable="true"), "the Node is now cordoned"),
    ],
)
def test_a_node_that_returns_changed_fails_and_the_difference_is_named(
    env: _Env, back: str, difference: str
) -> None:
    (env.state / "node.back").write_text(back, encoding="utf-8")
    result = _run(env=env)
    assert result.returncode != 0
    assert f"departure-drill:   {difference}" in result.stderr.splitlines()
    assert "the worker did not come back as it left" in result.stderr


def test_a_lifecycle_taint_still_on_the_returned_node_is_not_an_enrollment_difference(
    env: _Env,
) -> None:
    (env.state / "node.back").write_text(
        _node(taints=f"node.kubernetes.io/not-ready=:NoSchedule {_CLASS} "), encoding="utf-8"
    )
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "taints=[node.kubernetes.io/not-ready=:NoSchedule " in result.stdout


def test_a_recorded_endpoint_off_the_current_cni0_address_fails_on_a_collector_line(
    env: _Env,
) -> None:
    (env.state / "cni0.back").write_text(
        "5: cni0    inet 10.9.7.1/24 brd 10.9.7.255 scope global cni0\n", encoding="utf-8"
    )
    result = _run(env=env)
    assert result.returncode != 0
    assert _report(result=result, subject="COLLECTOR") == (
        "departure-drill: COLLECTOR endpoint mismatch: node.env says 10.9.5.1:4319, cni0 is now"
        " 10.9.7.1; nothing rewrote node.env on the return (listening on the stale endpoint: true)"
    )
    assert (
        "departure-drill:   COLLECTOR: node.env endpoint 10.9.5.1:4319 is not on the current cni0"
        " address 10.9.7.1"
    ) in result.stderr.splitlines()
    assert _changes(env=env)[-1] == f"limactl start --tty=false {_WORKER}"


def test_a_collector_that_does_not_listen_on_its_endpoint_fails_on_a_collector_line(
    env: _Env,
) -> None:
    (env.state / "listeners").write_text(
        "LISTEN 0 4096 127.0.0.1:10248 0.0.0.0:*\n", encoding="utf-8"
    )
    result = _run(env=env)
    assert result.returncode != 0
    assert "COLLECTOR not listening: node.env's 10.9.5.1:4319 matches cni0" in result.stdout
    assert "COLLECTOR: nothing listens on 10.9.5.1:4319" in result.stderr


def test_a_collector_that_listens_only_after_the_first_read_is_awaited_inside_the_bound(
    env: _Env,
) -> None:
    listening = (env.state / "listeners").read_text(encoding="utf-8")
    (env.state / "listeners.back").write_text(listening, encoding="utf-8")
    (env.state / "listeners").write_text(
        "LISTEN 0 4096 127.0.0.1:10248 0.0.0.0:*\n", encoding="utf-8"
    )
    result = _run(env=env, wait="50")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "COLLECTOR endpoint 10.9.5.1:4319 matches cni0 (10.9.5.1) and is listening" in (
        result.stdout
    )
    calls = _calls(env=env)
    waited = calls[calls.index(f"limactl start --tty=false {_WORKER}") :]
    assert [c for c in waited if c.startswith("sleep ")] == ["sleep 25"]


def test_a_collector_that_never_listens_is_awaited_to_the_bound_and_the_wait_is_named(
    env: _Env,
) -> None:
    (env.state / "listeners").write_text(
        "LISTEN 0 4096 127.0.0.1:10248 0.0.0.0:*\n", encoding="utf-8"
    )
    result = _run(env=env, wait="50")
    assert result.returncode != 0
    assert "but nothing listens there 50s after the return" in result.stdout


def test_a_missing_cni0_address_is_awaited_inside_the_bound_then_fails_on_a_collector_line(
    env: _Env,
) -> None:
    (env.state / "cni0.back").write_text("", encoding="utf-8")
    result = _run(env=env, wait="50")
    assert result.returncode != 0
    assert "COLLECTOR not comparable" in result.stdout
    assert "has no cni0 address 50s after the return" in result.stdout
    calls = _calls(env=env)
    waited = calls[calls.index(f"limactl start --tty=false {_WORKER}") :]
    assert [c for c in waited if c.startswith("sleep ")] == ["sleep 25", "sleep 25"]


def test_a_worker_with_no_recorded_endpoint_or_a_stopped_container_fails(env: _Env) -> None:
    (env.root / "telemetry" / "node.env").unlink()
    (env.state / "container").write_text("false\n", encoding="utf-8")
    result = _run(env=env)
    assert result.returncode != 0
    assert "COLLECTOR not configured" in result.stdout
    assert f"worker container {_WORKER} is not running (State.Running is 'false')" in result.stderr


@pytest.mark.parametrize(
    ("start_fails", "said"),
    [
        ("", "the return step ran; the rejoin was not read back"),
        ("1", f"THE RETURN STEP FAILED: VM {_WORKER} is still away"),
    ],
)
def test_a_step_that_fails_after_the_departure_still_attempts_the_return(
    env: _Env, start_fails: str, said: str
) -> None:
    result = _run(env=env, stub_env={"KUBECTL_FAILS": "pods.away", "START_FAILS": start_fails})
    assert result.returncode != 0
    assert "could not read the cluster's pods at the end of the hold" in result.stderr
    assert "attempting the return step now" in result.stderr
    assert said in result.stderr
    assert _changes(env=env) == [
        f"limactl stop --force {_WORKER}",
        f"limactl start --tty=false {_WORKER}",
    ]


def test_a_failed_return_step_is_named_and_is_not_attempted_twice(env: _Env) -> None:
    result = _run(env=env, stub_env={"START_FAILS": "1"})
    assert result.returncode != 0
    assert f"the return step failed; VM {_WORKER} is still away" in result.stderr
    assert "attempting the return step now" not in result.stderr
    assert [c for c in _calls(env=env) if c.startswith("limactl start")] == [
        f"limactl start --tty=false {_WORKER}"
    ]


def test_an_unconfirmed_departure_reads_nothing_and_changes_nothing(env: _Env) -> None:
    result = _run(env=env, args=[_HOST, "--mode", "power-loss", "--hold-seconds", "60"])
    assert result.returncode != 0
    assert "Nothing was read and nothing was changed" in result.stderr
    assert _calls(env=env) == []


def test_the_captured_pods_are_read_a_second_time_after_the_rejoin(env: _Env) -> None:
    (env.state / "pods.back").write_text(
        "\n".join(
            (
                f"ci|gate-a-2|u-gate-2|Succeeded|{_OTHER}|Job|gate-a|0",
                f"arc|runner-b|u-runner|Failed|{_WORKER}|EphemeralRunner|runner-b|1 2",
                f"ci|done-c-1|u-done|Succeeded|{_WORKER}|Job|done-c|0",
                f"kube-system|flannel-x|u-flannel-x|Running|{_WORKER}|DaemonSet|flannel|1",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    start = lines.index("departure-drill: AFTER the rejoin, the pods captured on the node:")
    assert start > lines.index("departure-drill: AFTER 60s away, the pods captured on the node:")
    prefix = "departure-drill:   "
    assert lines[start + 1 : start + 7] == [
        f"{prefix}replaced-elsewhere: pod ci/gate-a-1 (Running at capture) is, after the rejoin,"
        f" pod gone; replacement on another node: ci/gate-a-2 on {_OTHER} (Succeeded)",
        f"{prefix}failed: pod arc/runner-b (Running at capture) is, after the rejoin, phase=Failed"
        f" node={_WORKER}; replacement on another node: none",
        f"{prefix}finished-before-departure: pod ci/done-c-1 (Succeeded at capture) is, after the"
        f" rejoin, phase=Succeeded node={_WORKER}; replacement on another node: none",
        f"{prefix}gone: pod ci/bare (Running at capture) is, after the rejoin, pod gone;"
        " replacement on another node: none",
        f"{prefix}gone: pod ci/crash-d-1 (Running at capture) is, after the rejoin, pod gone;"
        " replacement on another node: none",
        f"{prefix}still-bound-to-the-departed-node: pod kube-system/flannel-x (Running at capture)"
        f" is, after the rejoin, phase=Running node={_WORKER}; replacement on another node: none",
    ]


def test_a_job_that_does_not_retry_is_named_as_lost_after_the_rejoin(env: _Env) -> None:
    (env.state / "jobs" / "ci.gate-a.back").write_text("j-gate||1|||0", encoding="utf-8")
    (env.state / "jobs" / "ci.done-c.back").write_text("j-done|1||||6", encoding="utf-8")
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _report(result=result, subject="job ci/gate-a after the rejoin") == (
        "departure-drill:   job ci/gate-a after the rejoin: succeeded=0 failed=1 active=0"
        " suspended=false uid=j-gate; backoffLimit=0 and a failed pod: this Job does not retry,"
        " so its work is lost and its client reads the failure"
    )
    assert _report(result=result, subject="job ci/done-c after the rejoin").endswith(
        "uid=j-done; backoffLimit=6"
    )
    assert _report(result=result, subject="job ci/crash-d after the rejoin").endswith(
        "uid=j-crash; backoffLimit=unset"
    )


def test_a_job_deleted_while_away_reads_gone_after_the_rejoin(env: _Env) -> None:
    (env.state / "jobs" / "ci.crash-d.back").write_text("", encoding="utf-8")
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _report(result=result, subject="job ci/crash-d after the rejoin") == (
        "departure-drill:   job ci/crash-d after the rejoin: gone"
    )


def test_a_factory_sandbox_pod_on_the_node_is_named_before_and_after(env: _Env) -> None:
    with (env.state / "pods").open("a", encoding="utf-8") as pods:
        pods.write(f"factory|sandbox-run-9|u-sandbox|Running|{_WORKER}|||0\n")
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    before = next(i for i, line in enumerate(lines) if "FACTORY: the node carries" in line)
    after = next(i for i, line in enumerate(lines) if "FACTORY after the rejoin" in line)
    departed = next(i for i, line in enumerate(lines) if "DEPARTED at " in line)
    assert before < departed < after
    assert lines[before + 1] == "departure-drill:   factory/sandbox-run-9"
    assert lines[after + 1] == "departure-drill:   factory/sandbox-run-9"
    assert "a forced stop kills them" in lines[before]
    assert "this script cannot read a run" in lines[after]


def test_a_node_with_no_factory_pod_prints_no_factory_line(env: _Env) -> None:
    result = _run(env=env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FACTORY" not in result.stdout


def test_the_header_states_what_the_drill_does_not_prove() -> None:
    header = " ".join(
        line.lstrip("# ")
        for line in _SCRIPT.read_text(encoding="utf-8")
        .split("\nset -euo pipefail\n", 1)[0]
        .splitlines()
    )
    for stated in (
        "WHAT THIS DRILL DOES NOT PROVE.",
        "does not exercise the collector ingest key's dependence on a login Keychain unlock",
        "IN NETWORK-LOSS MODE THE RETURN RESTORES ONLY THE CONNECTED ROUTE.",
        "a converge (the start task) may have to follow",
        "`--confirm-depart` must name the worker's Node, <host>-homelab-worker, exactly",
    ):
        assert stated in header, stated
