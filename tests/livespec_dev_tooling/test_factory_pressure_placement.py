"""The factory pressure placement scripts, run for real against a faked kubectl.

Orchestrator work-item bd-ib-plon2p: a host-side reconciler steers NEW factory
sandbox pods off a CPU-pressured factory node with a PreferNoSchedule taint,
reserving the gates quota (the rule agreed with dev-host-test-gate-load). Each
factory node publishes its own pressure as the `LivespecCPUPressure` node
condition through the node-status credential it already holds.

WHY THE SCRIPTS ARE RUN RATHER THAN READ. Every claim here is about a DECISION:
when to taint, when to clear, what a missing reading or a failed quota read
does. Reading a shell script cannot establish that. So each script runs with a
fake `kubectl` first on PATH. The fake serves canned cluster JSON from a
scratch directory and logs every argv. No cluster is reached and nothing
leaves `tmp_path`.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

__all__: list[str] = []

_Json = dict[str, Any]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_DIR = _PHASE2 / "factory-pressure-placement"
_RECONCILE = _DIR / "reconcile-factory-pressure-taint.sh"
_PUBLISH = _DIR / "publish-node-cpu-pressure.sh"
_PLAY = _REPO_ROOT / "ansible" / "ci-pool.yml"
_TAINT_KEY = "livespec.io/factory-pressure"
_NOW = 1_800_000_000
_BEAT = "2027-01-15T08:00:00Z"  # == _NOW
_PE = "poweredge-xubuntu"
_GMK = "gmktec-xubuntu"

_FAKE_KUBECTL = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DIR/argv.log"
case "$*" in
  "get nodes -l ci-runner.io/factory=true -o json") cat "$FAKE_DIR/nodes.json" ;;
  "get pods --all-namespaces -o json") cat "$FAKE_DIR/pods.json" ;;
  "get clusterqueue gates-cq -o json")
    [ -f "$FAKE_DIR/cq.json" ] || { echo 'Error from server: connection refused' >&2; exit 1; }
    cat "$FAKE_DIR/cq.json" ;;
  "get resourceflavors -o json")
    [ -f "$FAKE_DIR/flavors.json" ] || { echo 'Error from server: connection refused' >&2; exit 1; }
    cat "$FAKE_DIR/flavors.json" ;;
  patch*)
    if [ -f "$FAKE_DIR/reject-once" ]; then
      rm -f "$FAKE_DIR/reject-once"
      echo 'error: You must be logged in to the server (Unauthorized)' >&2
      exit 1
    fi ;;
  taint*|annotate*) ;;
  *) echo "fake kubectl: unexpected argv: $*" >&2; exit 1 ;;
esac
"""


def _node(
    name: str, *, avg60: float | None, beat: str = _BEAT, tainted: bool = False, alloc: str = "32"
) -> _Json:
    conditions = [{"type": "Ready", "status": "True"}]
    if avg60 is not None:
        conditions.append(
            {
                "type": "LivespecCPUPressure",
                "status": "True",
                "reason": "PSIReading",
                "message": f"cpu.some.avg60={avg60}",
                "lastHeartbeatTime": beat,
            }
        )
    return {
        "metadata": {
            "name": name,
            "labels": {"kubernetes.io/hostname": name, "ci-runner.io/factory": "true"},
        },
        "spec": {
            "taints": [{"key": _TAINT_KEY, "value": "high", "effect": "PreferNoSchedule"}]
            if tainted
            else []
        },
        "status": {"allocatable": {"cpu": alloc}, "conditions": conditions},
    }


def _pod(
    name: str,
    *,
    node: str,
    cpu: str,
    namespace: str = "factory",
    labels: _Json | None = None,
    annotations: _Json | None = None,
    phase: str = "Running",
) -> _Json:
    return {
        "metadata": {
            "name": name,
            "namespace": namespace,
            "labels": labels or {},
            "annotations": annotations or {},
        },
        "spec": {
            "nodeName": node,
            "containers": [{"name": "c", "resources": {"requests": {"cpu": cpu}}}],
        },
        "status": {"phase": phase},
    }


_SANDBOX = {"app.kubernetes.io/managed-by": "sandbox-driver-kubernetes"}
_GATE = {"app.kubernetes.io/part-of": "livespec-ci-gates"}


def _gates_quota(cpu: str, *, topology: bool = False) -> tuple[_Json, _Json]:
    cq = {
        "spec": {
            "resourceGroups": [
                {
                    "flavors": [
                        {
                            "name": "gates-flavor",
                            "resources": [
                                {"name": "cpu", "nominalQuota": cpu},
                                {"name": "memory", "nominalQuota": "8Gi"},
                            ],
                        },
                        {
                            "name": "gates-hp-flavor",
                            "resources": [{"name": "cpu", "nominalQuota": "5"}],
                        },
                    ]
                }
            ]
        }
    }
    flavors = {
        "items": [
            {
                "metadata": {"name": "gates-flavor"},
                "spec": {
                    "nodeLabels": {"kubernetes.io/hostname": _GMK},
                    **({"topologyName": "gates-topology"} if topology else {}),
                },
            },
            {
                "metadata": {"name": "gates-hp-flavor"},
                "spec": {"nodeLabels": {"kubernetes.io/hostname": "hp-xubuntu"}},
            },
        ]
    }
    return cq, flavors


def _scratch(tmp_path: Path) -> tuple[Path, dict[str, str]]:
    fake = tmp_path / "fake"
    bin_dir = tmp_path / "bin"
    fake.mkdir()
    bin_dir.mkdir()
    kubectl = bin_dir / "kubectl"
    _ = kubectl.write_text(_FAKE_KUBECTL, encoding="utf-8")
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IEXEC)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FAKE_DIR": str(fake),
        "KUBECONFIG": str(tmp_path / "kubeconfig"),
        "FACTORY_PRESSURE_STATE_DIR": str(tmp_path / "state"),
        "FACTORY_PRESSURE_NOW": str(_NOW),
        "HOME": str(tmp_path),
    }
    return fake, env


def _reconcile(
    tmp_path: Path,
    *,
    nodes: list[_Json],
    pods: list[_Json],
    quota_cpu: str | None = "5",
    topology: bool = False,
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    fake, env = _scratch(tmp_path)
    _ = (fake / "nodes.json").write_text(json.dumps({"items": nodes}), encoding="utf-8")
    _ = (fake / "pods.json").write_text(json.dumps({"items": pods}), encoding="utf-8")
    if quota_cpu is not None:
        cq, flavors = _gates_quota(quota_cpu, topology=topology)
        _ = (fake / "cq.json").write_text(json.dumps(cq), encoding="utf-8")
        _ = (fake / "flavors.json").write_text(json.dumps(flavors), encoding="utf-8")
    run = subprocess.run(
        ["bash", str(_RECONCILE)], env=env, capture_output=True, text=True, check=False
    )
    log = (fake / "argv.log").read_text(encoding="utf-8").splitlines()
    return run, [line for line in log if not line.startswith("get ")]


def test_a_pressured_node_is_tainted_when_the_quiet_node_fits_a_sandbox(tmp_path: Path) -> None:
    run, mutations = _reconcile(
        tmp_path,
        nodes=[_node(_PE, avg60=45.0, alloc="72"), _node(_GMK, avg60=8.0)],
        pods=[_pod("sb1", node=_GMK, cpu="4", labels=_SANDBOX)],
    )
    assert run.returncode == 0, run.stderr
    assert f"taint nodes {_PE} {_TAINT_KEY}=high:PreferNoSchedule --overwrite" in mutations
    assert not any(m.startswith(f"taint nodes {_GMK}") for m in mutations), mutations


def test_the_gates_reserve_keeps_the_quiet_node_from_being_preferred(tmp_path: Path) -> None:
    # gmktec: 32 allocatable, 6 sandboxes x 4 = 24 requested, 5-CPU gates quota with
    # nothing running there -> fit = 32 - 24 - 5 = 3 CPU < 4. No steer, and the
    # existing taint on poweredge is cleared.
    sandboxes = [
        _pod(
            f"sb{i}",
            node=_GMK,
            cpu="4",
            labels=_SANDBOX,
            annotations={"livespec.io/placement-pressure": "x"},
        )
        for i in range(6)
    ]
    run, mutations = _reconcile(
        tmp_path,
        nodes=[_node(_PE, avg60=45.0, alloc="72", tainted=True), _node(_GMK, avg60=8.0)],
        pods=sandboxes,
    )
    assert run.returncode == 0, run.stderr
    assert mutations == [f"taint nodes {_PE} {_TAINT_KEY}:PreferNoSchedule-"], mutations
    assert "lowest-does-not-fit" in run.stdout


def test_a_running_gate_already_counts_inside_requested_so_only_unused_quota_is_reserved(
    tmp_path: Path,
) -> None:
    # 5 sandboxes (20) + one running 5-CPU gate: requested 25; the gate uses the whole
    # 5-CPU quota, so the reserve is 0 and fit = 32 - 25 - 0 = 7 >= 4.
    pods = [_pod(f"sb{i}", node=_GMK, cpu="4", labels=_SANDBOX) for i in range(5)]
    pods.append(_pod("gate", node=_GMK, cpu="5", namespace="gates", labels=_GATE))
    pods.append(
        _pod("done-gate", node=_GMK, cpu="5", namespace="gates", labels=_GATE, phase="Succeeded")
    )
    run, mutations = _reconcile(
        tmp_path,
        nodes=[_node(_PE, avg60=40.0, alloc="72"), _node(_GMK, avg60=10.0)],
        pods=pods,
    )
    assert run.returncode == 0, run.stderr
    assert f"taint nodes {_PE} {_TAINT_KEY}=high:PreferNoSchedule --overwrite" in mutations


def test_a_stale_or_missing_reading_clears_the_taint_everywhere(tmp_path: Path) -> None:
    run, mutations = _reconcile(
        tmp_path,
        nodes=[
            _node(_PE, avg60=45.0, alloc="72", tainted=True),
            _node(_GMK, avg60=8.0, beat="2027-01-15T07:50:00Z"),
        ],
        pods=[],
    )
    assert run.returncode == 0, run.stderr
    assert mutations == [f"taint nodes {_PE} {_TAINT_KEY}:PreferNoSchedule-"], mutations
    assert f"reading-unknown:{_GMK}" in run.stdout


def test_a_node_that_publishes_no_pressure_condition_is_unknown(tmp_path: Path) -> None:
    run, mutations = _reconcile(
        tmp_path,
        nodes=[_node(_PE, avg60=45.0, alloc="72"), _node(_GMK, avg60=None)],
        pods=[],
    )
    assert run.returncode == 0, run.stderr
    assert mutations == [], mutations
    assert f"reading-unknown:{_GMK}" in run.stdout


def test_a_gap_under_twenty_points_does_not_steer(tmp_path: Path) -> None:
    run, mutations = _reconcile(
        tmp_path,
        nodes=[_node(_PE, avg60=27.0, alloc="72"), _node(_GMK, avg60=8.0)],
        pods=[],
    )
    assert run.returncode == 0, run.stderr
    assert mutations == [], mutations
    assert "no-gap" in run.stdout


def test_no_gates_quota_read_ever_means_no_taint(tmp_path: Path) -> None:
    run, mutations = _reconcile(
        tmp_path,
        nodes=[_node(_PE, avg60=45.0, alloc="72"), _node(_GMK, avg60=8.0)],
        pods=[],
        quota_cpu=None,
    )
    assert run.returncode == 0, run.stderr
    assert mutations == [], mutations
    assert "no-gates-quota-read-ever" in run.stdout


def test_a_failed_quota_read_reserves_the_cached_full_quota(tmp_path: Path) -> None:
    # First cycle reads a 5-CPU quota live and caches it. Second cycle cannot read it:
    # the cached FULL 5 CPU is reserved even though a running gate uses it all.
    nodes = [_node(_PE, avg60=45.0, alloc="72"), _node(_GMK, avg60=8.0)]
    pods = [_pod(f"sb{i}", node=_GMK, cpu="4", labels=_SANDBOX) for i in range(5)]
    pods.append(_pod("gate", node=_GMK, cpu="5", namespace="gates", labels=_GATE))
    first, _ = _reconcile(tmp_path, nodes=nodes, pods=pods, quota_cpu="5")
    assert "quota=live" in first.stdout, first.stdout
    fake = tmp_path / "fake"
    (fake / "cq.json").unlink()
    (fake / "argv.log").unlink()
    nodes[0]["spec"]["taints"] = []
    env = {
        "PATH": f"{tmp_path / 'bin'}:{os.environ['PATH']}",
        "FAKE_DIR": str(fake),
        "KUBECONFIG": str(tmp_path / "kubeconfig"),
        "FACTORY_PRESSURE_STATE_DIR": str(tmp_path / "state"),
        "FACTORY_PRESSURE_NOW": str(_NOW),
        "HOME": str(tmp_path),
    }
    second = subprocess.run(
        ["bash", str(_RECONCILE)], env=env, capture_output=True, text=True, check=False
    )
    assert second.returncode == 0, second.stderr
    assert "quota=cached" in second.stdout, second.stdout
    # 32 - 25 - 5 (cached, full) = 2 < 4: no steer.
    assert "lowest-does-not-fit" in second.stdout, second.stdout


def test_new_sandbox_pods_are_annotated_once_with_the_cycle_readings(tmp_path: Path) -> None:
    run, mutations = _reconcile(
        tmp_path,
        nodes=[_node(_PE, avg60=45.0, alloc="72"), _node(_GMK, avg60=8.0)],
        pods=[
            _pod("fresh", node=_GMK, cpu="4", labels=_SANDBOX),
            _pod(
                "seen",
                node=_GMK,
                cpu="4",
                labels=_SANDBOX,
                annotations={"livespec.io/placement-pressure": "x"},
            ),
            _pod("runner", node=_GMK, cpu="1", namespace="arc-runners"),
        ],
    )
    assert run.returncode == 0, run.stderr
    annotated = [m for m in mutations if m.startswith("annotate")]
    assert len(annotated) == 1, annotated
    assert annotated[0].startswith("annotate pod -n factory fresh livespec.io/placement-pressure=")
    assert f"{_PE}=45.0" in annotated[0] and f"{_GMK}=8.0" in annotated[0]
    assert f"taint={_PE}" in annotated[0]


def test_a_topology_flavor_caps_the_gates_reserve_at_five_cpu(tmp_path: Path) -> None:
    # gmktec: 32 allocatable, 5 sandboxes = 20 requested, a 10-CPU gates quota with
    # nothing running. The flavor sets topologyName, so the reserve is
    # min(10, cap 5) = 5 and fit = 32 - 20 - 5 = 7 >= 4: steer.
    run, mutations = _reconcile(
        tmp_path,
        nodes=[_node(_PE, avg60=45.0, alloc="72"), _node(_GMK, avg60=8.0)],
        pods=[_pod(f"sb{i}", node=_GMK, cpu="4", labels=_SANDBOX) for i in range(5)],
        quota_cpu="10",
        topology=True,
    )
    assert run.returncode == 0, run.stderr
    assert f"RESERVE {_GMK} branch=capped-topology" in run.stdout, run.stdout
    assert "reserve=5000m" in run.stdout, run.stdout
    assert f"taint nodes {_PE} {_TAINT_KEY}=high:PreferNoSchedule --overwrite" in mutations


def test_a_flavor_without_topology_keeps_the_full_unused_quota(tmp_path: Path) -> None:
    # Same numbers without topologyName: the reserve is the full unused 10 CPU and
    # fit = 32 - 20 - 10 = 2 < 4: no steer.
    run, mutations = _reconcile(
        tmp_path,
        nodes=[_node(_PE, avg60=45.0, alloc="72"), _node(_GMK, avg60=8.0)],
        pods=[_pod(f"sb{i}", node=_GMK, cpu="4", labels=_SANDBOX) for i in range(5)],
        quota_cpu="10",
    )
    assert run.returncode == 0, run.stderr
    assert f"RESERVE {_GMK} branch=uncapped" in run.stdout, run.stdout
    assert "reserve=10000m" in run.stdout, run.stdout
    assert not any(m.startswith("taint") for m in mutations), mutations


def _publish(
    tmp_path: Path, *, psi: str, role: str = "agent", reject_once: bool = False
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    fake, env = _scratch(tmp_path)
    kubeconfig = tmp_path / "node-status-kubeconfig"
    _ = kubeconfig.write_text("x", encoding="utf-8")
    del env["KUBECONFIG"]
    profile = tmp_path / "node.env"
    _ = profile.write_text(
        f"NODE_NAME={_GMK}\nCLUSTER_ROLE={role}\nCHURN_KUBECONFIG_FILE={kubeconfig}\n",
        encoding="utf-8",
    )
    psi_file = tmp_path / "psi"
    _ = psi_file.write_text(psi, encoding="utf-8")
    refresh = tmp_path / "refresh"
    _ = refresh.write_text(
        f"#!/usr/bin/env bash\necho refreshed >>{fake}/argv.log\n", encoding="utf-8"
    )
    refresh.chmod(0o755)
    if reject_once:
        _ = (fake / "reject-once").write_text("", encoding="utf-8")
    env |= {"FACTORY_PRESSURE_PSI_FILE": str(psi_file), "NODE_STATUS_REFRESH_BIN": str(refresh)}
    run = subprocess.run(
        ["bash", str(_PUBLISH), str(profile)], env=env, capture_output=True, text=True, check=False
    )
    log_file = fake / "argv.log"
    log = log_file.read_text(encoding="utf-8").splitlines() if log_file.exists() else []
    return run, log


_PSI = "some avg10=1.00 avg60=37.25 avg300=20.00 total=1\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"


def test_the_publisher_patches_its_own_node_status_condition(tmp_path: Path) -> None:
    run, log = _publish(tmp_path, psi=_PSI)
    assert run.returncode == 0, run.stderr
    assert len(log) == 1, log
    argv = log[0]
    assert argv.startswith(f"patch node {_GMK} --subresource=status --type=strategic -p ")
    patch = json.loads(argv.split(" -p ", 1)[1])
    (condition,) = patch["status"]["conditions"]
    assert condition["type"] == "LivespecCPUPressure"
    assert condition["message"] == "cpu.some.avg60=37.25"
    assert condition["lastHeartbeatTime"].endswith("Z")


def test_the_publisher_refuses_a_false_zero(tmp_path: Path) -> None:
    run, log = _publish(tmp_path, psi="some avg10=1.00 avg300=2.00 total=1\n")
    assert run.returncode != 0
    assert log == [], log
    assert "false zero" in run.stderr


def test_the_publisher_refreshes_a_rejected_agent_credential_once(tmp_path: Path) -> None:
    run, log = _publish(tmp_path, psi=_PSI, reject_once=True)
    assert run.returncode == 0, run.stderr
    assert [line.split(" ", 1)[0] for line in log] == ["patch", "refreshed", "patch"], log


def test_ci_pool_wires_both_roles_under_one_tag() -> None:
    play = _PLAY.read_text(encoding="utf-8")
    assert (
        "    - role: factory_pressure_publisher\n"
        "      tags: [factory_pressure_placement]\n"
        "      when: ci_pool_factory_node == 'true'\n"
    ) in play
    assert (
        "    - role: factory_pressure_reconciler\n"
        "      tags: [factory_pressure_placement]\n"
        "      when: cluster_role == 'server'\n"
    ) in play


def test_every_ci_pod_template_tolerates_the_factory_pressure_taint() -> None:
    templates = [
        *sorted((_PHASE2 / "arc").glob("values-*.yaml")),
        _PHASE2 / "arc" / "hook-pod-template.yaml",
        _PHASE2 / "gates" / "gate-job-template.yaml",
    ]
    missing = [
        str(t.relative_to(_REPO_ROOT))
        for t in templates
        if f"key: {_TAINT_KEY}\n" not in t.read_text(encoding="utf-8")
        or "effect: PreferNoSchedule" not in t.read_text(encoding="utf-8")
    ]
    assert not missing, (
        f"the factory pressure taint must steer FACTORY pods only, so every CI pod "
        f"template tolerates it; missing in {missing}"
    )
