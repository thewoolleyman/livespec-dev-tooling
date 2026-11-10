"""Consumer-tier: the gate placement reconciler steers gates-cq's flavor order.

Covers the three `SPECIFICATION/scenarios.md` scenarios that the "Placement by
node pressure" bullet of the delegated pre-push gate contract in
`SPECIFICATION/contracts.md` governs (work item livespec-dev-tooling-gvo7fa), and
the bullet's other MUSTs: a lane per `ci_pool` node needs no edit to the
reconciler, an architecture-ineligible lane is neither unsaturated nor a lane
with room, quota is never changed, and the committed files are never written.

NOTHING HERE REACHES A CLUSTER. `reconcile-gate-lane-order.sh` runs for real with a
fake `kubectl` first on PATH that serves canned cluster JSON and records the
patch it is handed. `_Cluster.admit` then plays Kueue's one relevant rule: a
newly submitted gate Job is admitted on the FIRST flavor of the queue's current
order whose lane has quota room. The static lane order is the committed
`cluster-queue-gates.yaml`, read through the script's own installed-path override.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_Json = dict[str, Any]

_REPO = Path(__file__).resolve().parents[2]
_PHASE2 = _REPO / "ci-runner" / "k3s" / "phase2"
_RECONCILE = _PHASE2 / "gate-placement" / "reconcile-gate-lane-order.sh"
_STATIC_QUEUE = _PHASE2 / "kueue" / "cluster-queue-gates.yaml"
_ARCH_CONF = _PHASE2 / "workload-arch.conf"
_NOW = 1_800_000_000
_BEAT = "2027-01-15T08:00:00Z"  # == _NOW
_GMK, _PE, _HP = "gmktec-xubuntu", "poweredge-xubuntu", "hp-xubuntu"
_FLAVOR = {_GMK: "gates-flavor", _PE: "gates-poweredge-flavor", _HP: "gates-hp-flavor"}
_GATE_CPU = 5

_FAKE_KUBECTL = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DIR/argv.log"
case "$1 $2 $3" in
  "get nodes -o") cat "$FAKE_DIR/nodes.json" ;;
  "get clusterqueue gates-cq") cat "$FAKE_DIR/cq.json" ;;
  "get resourceflavors -o") cat "$FAKE_DIR/flavors.json" ;;
  "patch clusterqueue gates-cq") printf '%s' "$6" >"$FAKE_DIR/patch.json" ;;
  *) echo "fake kubectl: unexpected argv: $*" >&2; exit 1 ;;
esac
"""


def _node(
    name: str,
    *,
    idle: str | float | None,
    pressure: str | float | None,
    beat: str = _BEAT,
    arch: str = "amd64",
    condition: bool = True,
) -> _Json:
    conditions: list[_Json] = [{"type": "Ready", "status": "True"}]
    if condition:
        conditions.append(
            {
                "type": "LivespecGateLaneCPU",
                "status": "True",
                "message": f"cpu.idle60={idle} ci.slice.some.avg60={pressure}",
                "lastHeartbeatTime": beat,
            }
        )
    return {
        "metadata": {
            "name": name,
            "labels": {"kubernetes.io/hostname": name, "kubernetes.io/arch": arch},
        },
        "status": {"conditions": conditions},
    }


def _saturated(name: str) -> _Json:
    return _node(name, idle=1.2, pressure=52.0)


def _free(name: str) -> _Json:
    return _node(name, idle=18.6, pressure=0.06)


def _flavor(name: str, *, cpu: int) -> _Json:
    return {
        "name": name,
        "resources": [
            {"name": "cpu", "nominalQuota": cpu},
            {"name": "memory", "nominalQuota": f"{cpu // 5 * 8}Gi"},
        ],
    }


class _Cluster:
    """The canned cluster: nodes, the gates-cq flavor order, and each lane's room."""

    def __init__(
        self,
        tmp_path: Path,
        *,
        nodes: list[_Json],
        order: list[str],
        lane_node: dict[str, str],
        quota_cpu: int = 10,
    ) -> None:
        self.tmp_path = tmp_path
        self.fake = tmp_path / "fake"
        self.fake.mkdir()
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        kubectl = bin_dir / "kubectl"
        _ = kubectl.write_text(_FAKE_KUBECTL, encoding="utf-8")
        kubectl.chmod(kubectl.stat().st_mode | stat.S_IEXEC)
        self.lane_node = lane_node
        self.order = order
        self.quota_cpu = quota_cpu
        self.used_cpu = dict.fromkeys(order, 0)
        flavors = [
            {
                "metadata": {"name": flavor},
                "spec": {"nodeLabels": {"kubernetes.io/hostname": node}},
            }
            for flavor, node in lane_node.items()
        ]
        self.write("nodes.json", {"items": nodes})
        self.write("flavors.json", {"items": flavors})
        self.write_queue(order)
        self.env = {
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_DIR": str(self.fake),
            "KUBECONFIG": str(tmp_path / "kubeconfig"),
            "GATE_LANE_NOW": str(_NOW),
            "GATE_LANE_STATIC_QUEUE_FILE": str(_STATIC_QUEUE),
            "GATE_LANE_ARCH_CONF": str(_ARCH_CONF),
            "HOME": str(tmp_path),
        }

    def write(self, name: str, document: _Json) -> None:
        _ = (self.fake / name).write_text(json.dumps(document), encoding="utf-8")

    def write_queue(self, order: list[str]) -> None:
        self.order = order
        self.write(
            "cq.json",
            {
                "metadata": {"name": "gates-cq", "resourceVersion": "4711"},
                "spec": {
                    "resourceGroups": [
                        {
                            "coveredResources": ["cpu", "memory"],
                            "flavors": [_flavor(n, cpu=self.quota_cpu) for n in order],
                        }
                    ]
                },
            },
        )

    def reconcile(self, *args: str) -> subprocess.CompletedProcess[str]:
        run = subprocess.run(
            ["bash", str(_RECONCILE), *args],
            env=self.env,
            capture_output=True,
            text=True,
            check=False,
        )
        patch = self.fake / "patch.json"
        if run.returncode == 0 and patch.exists() and "--dry-run" not in args:
            ops: list[_Json] = json.loads(patch.read_text(encoding="utf-8"))
            assert ops[0] == {
                "op": "test",
                "path": "/metadata/resourceVersion",
                "value": "4711",
            }
            self.order = [flavor["name"] for flavor in ops[1]["value"]]
            self.write_queue(self.order)
            patch.unlink()
        return run

    def patched(self) -> bool:
        return (self.fake / "patch.json").exists()

    def admit(self) -> str | None:
        """Admit one gate Job on the first flavor, in queue order, with quota room."""
        for flavor in self.order:
            if self.used_cpu[flavor] + _GATE_CPU <= self.quota_cpu:
                self.used_cpu[flavor] += _GATE_CPU
                return self.lane_node[flavor]
        return None


def _pool(
    tmp_path: Path, nodes: list[_Json], *, lanes: list[str] | None = None, quota_cpu: int = 10
) -> _Cluster:
    lanes = lanes or [_GMK, _PE, _HP]
    return _Cluster(
        tmp_path,
        nodes=nodes,
        order=[_FLAVOR[n] for n in lanes],
        lane_node={_FLAVOR[n]: n for n in lanes},
        quota_cpu=quota_cpu,
    )


def test_a_gate_job_submitted_while_one_lane_is_saturated_is_admitted_on_an_unsaturated_lane(
    tmp_path: Path,
) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE)], lanes=[_GMK, _PE])
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert cluster.admit() == _PE
    change = next(line for line in run.stdout.splitlines() if ": CHANGE " in line)
    assert f"{_GMK}(idle60=1.2,ci.slice.some.avg60=52.0,saturated)" in change
    assert f"{_PE}(idle60=18.6,ci.slice.some.avg60=0.06,not-saturated)" in change
    assert "gates-flavor,gates-poweredge-flavor -> gates-poweredge-flavor,gates-flavor" in change


def test_five_gate_jobs_while_gmktec_is_saturated_land_on_poweredge_or_hp(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE), _free(_HP)], quota_cpu=25)
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    landed = [cluster.admit() for _ in range(5)]
    assert _GMK not in landed and None not in landed, landed


def test_a_gate_job_submitted_while_every_lane_is_saturated_is_still_admitted(
    tmp_path: Path,
) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _saturated(_PE), _saturated(_HP)])
    cluster.used_cpu[_FLAVOR[_GMK]] = 10  # the first lane is full; the others have room
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert not cluster.patched()
    assert cluster.order == [_FLAVOR[_GMK], _FLAVOR[_PE], _FLAVOR[_HP]]
    assert cluster.admit() == _PE
    assert "all-lanes-saturated:static-order" in run.stdout


def test_a_queue_with_no_quota_room_on_any_lane_admits_nowhere_whatever_the_readings(
    tmp_path: Path,
) -> None:
    cluster = _pool(tmp_path, [_free(_GMK), _free(_PE)], lanes=[_GMK, _PE])
    cluster.used_cpu = {_FLAVOR[_GMK]: 10, _FLAVOR[_PE]: 10}
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert cluster.admit() is None


def test_a_pass_after_a_saturation_lifts_restores_the_static_order(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE), _free(_HP)])
    assert cluster.reconcile().returncode == 0
    assert cluster.order[-1] == _FLAVOR[_GMK]
    cluster.write("nodes.json", {"items": [_free(_GMK), _free(_PE), _free(_HP)]})
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert cluster.order == [_FLAVOR[_GMK], _FLAVOR[_PE], _FLAVOR[_HP]]
    assert "CHANGE" in run.stdout


def test_a_lane_whose_idle_share_cannot_be_read_falls_back_to_the_static_order(
    tmp_path: Path,
) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _node(_PE, idle="unreadable", pressure=0.1)])
    cluster.write_queue([_FLAVOR[_PE], _FLAVOR[_GMK]])  # a previously steered order
    cluster.lane_node = {_FLAVOR[_GMK]: _GMK, _FLAVOR[_PE]: _PE}
    cluster.used_cpu = {_FLAVOR[_GMK]: 0, _FLAVOR[_PE]: 0}
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert cluster.order == [_FLAVOR[_GMK], _FLAVOR[_PE]]
    assert cluster.admit() == _GMK
    assert f"UNREAD node={_PE} reading=cpu.idle60 why=reading is unreadable" in run.stdout
    assert "reading-unread:static-order" in run.stdout


@pytest.mark.parametrize(
    ("broken", "reading"),
    [
        (_node(_PE, idle=None, pressure=None, condition=False), "cpu.idle60"),
        (_node(_PE, idle=9.0, pressure=0.1, beat="2027-01-15T07:50:00Z"), "ci.slice.some.avg60"),
        (_node(_PE, idle=9.0, pressure="unreadable"), "ci.slice.some.avg60"),
        (_node(_PE, idle="garbage", pressure=1.0), "cpu.idle60"),
    ],
    ids=["absent-condition", "stale-heartbeat", "unreadable-pressure", "malformed-idle"],
)
def test_every_unread_reading_is_logged_by_node_and_never_taken_as_saturated_or_free(
    tmp_path: Path, broken: _Json, reading: str
) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), broken], lanes=[_PE, _GMK])
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert cluster.order == [_FLAVOR[_GMK], _FLAVOR[_PE]]  # the static order, not "PE is free"
    assert f"UNREAD node={_PE} reading={reading} why=" in run.stdout


def test_a_lane_node_the_cluster_does_not_know_is_an_unread_reading(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_free(_GMK)], lanes=[_GMK, _PE])
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert f"UNREAD node={_PE} reading=cpu.idle60 why=node not found" in run.stdout


def test_a_node_that_joins_the_pool_is_covered_without_editing_the_reconciler(
    tmp_path: Path,
) -> None:
    new_node = "newbox-xubuntu"
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE), _free(_HP), _free(new_node)])
    cluster.lane_node["gates-newbox-flavor"] = new_node
    cluster.write_queue([_FLAVOR[_GMK], _FLAVOR[_PE], _FLAVOR[_HP], "gates-newbox-flavor"])
    cluster.write(
        "flavors.json",
        {
            "items": [
                {"metadata": {"name": f}, "spec": {"nodeLabels": {"kubernetes.io/hostname": n}}}
                for f, n in cluster.lane_node.items()
            ]
        },
    )
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert cluster.order[-1] == _FLAVOR[_GMK]
    assert set(cluster.order) == set(cluster.lane_node)
    assert "gates-newbox-flavor" in cluster.order[:3]


def test_a_saturated_new_node_sorts_behind_the_unsaturated_lanes(tmp_path: Path) -> None:
    new_node = "newbox-xubuntu"
    cluster = _pool(tmp_path, [_free(_GMK), _free(_PE), _free(_HP), _saturated(new_node)])
    cluster.lane_node["gates-newbox-flavor"] = new_node
    cluster.write_queue([_FLAVOR[_GMK], "gates-newbox-flavor", _FLAVOR[_PE], _FLAVOR[_HP]])
    cluster.write(
        "flavors.json",
        {
            "items": [
                {"metadata": {"name": f}, "spec": {"nodeLabels": {"kubernetes.io/hostname": n}}}
                for f, n in cluster.lane_node.items()
            ]
        },
    )
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    # newbox is not in the committed order, so the static order puts it last.
    assert cluster.order == [_FLAVOR[_GMK], _FLAVOR[_PE], _FLAVOR[_HP], "gates-newbox-flavor"]


def test_a_lane_whose_node_cannot_run_the_gate_architecture_is_neither_free_nor_read(
    tmp_path: Path,
) -> None:
    arm = _node(_GMK, idle=40.0, pressure=0.0, arch="arm64")
    cluster = _pool(tmp_path, [arm, _free(_PE), _free(_HP)])
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert cluster.order == [_FLAVOR[_PE], _FLAVOR[_HP], _FLAVOR[_GMK]]
    assert f"{_GMK}(ineligible-architecture)" in run.stdout
    assert "UNREAD" not in run.stdout


def test_a_lane_with_no_architecture_label_is_ineligible_not_free(tmp_path: Path) -> None:
    unlabelled = _free(_GMK)
    del unlabelled["metadata"]["labels"]["kubernetes.io/arch"]
    cluster = _pool(tmp_path, [unlabelled, _free(_PE)], lanes=[_GMK, _PE])
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert cluster.order == [_FLAVOR[_PE], _FLAVOR[_GMK]]


def test_container_worker_flavors_stay_in_front_and_quota_is_never_changed(
    tmp_path: Path,
) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE), _free(_HP)])
    worker = "gates-worker-taint-arm64-flavor"
    cluster.write_queue([worker, _FLAVOR[_GMK], _FLAVOR[_PE], _FLAVOR[_HP]])
    cluster.write(
        "flavors.json",
        {
            "items": [
                {"metadata": {"name": worker}, "spec": {"nodeLabels": {"arch": "arm64"}}},
                *[
                    {
                        "metadata": {"name": _FLAVOR[n]},
                        "spec": {"nodeLabels": {"kubernetes.io/hostname": n}},
                    }
                    for n in (_GMK, _PE, _HP)
                ],
            ]
        },
    )
    before = json.loads((cluster.fake / "cq.json").read_text(encoding="utf-8"))
    quota = {f["name"]: f["resources"] for f in before["spec"]["resourceGroups"][0]["flavors"]}
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert cluster.order == [worker, _FLAVOR[_PE], _FLAVOR[_HP], _FLAVOR[_GMK]]
    after = json.loads((cluster.fake / "cq.json").read_text(encoding="utf-8"))
    assert {
        f["name"]: f["resources"] for f in after["spec"]["resourceGroups"][0]["flavors"]
    } == quota


def test_the_patch_writes_only_the_flavor_list_with_every_flavor_object_unchanged(
    tmp_path: Path,
) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE), _free(_HP)])
    live = json.loads((cluster.fake / "cq.json").read_text(encoding="utf-8"))
    original = {f["name"]: f for f in live["spec"]["resourceGroups"][0]["flavors"]}
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    sent = (cluster.fake / "argv.log").read_text(encoding="utf-8")
    assert "patch clusterqueue gates-cq --type=json -p" in sent
    after = json.loads((cluster.fake / "cq.json").read_text(encoding="utf-8"))
    for flavor in after["spec"]["resourceGroups"][0]["flavors"]:
        assert flavor == original[flavor["name"]]


def test_no_change_means_no_patch(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_free(_GMK), _free(_PE), _free(_HP)])
    run = cluster.reconcile()
    assert run.returncode == 0, run.stderr
    assert not cluster.patched()
    assert "patch" not in (cluster.fake / "argv.log").read_text(encoding="utf-8")
    assert "none-saturated:static-order" in run.stdout


def test_dry_run_decides_and_logs_but_patches_nothing(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE), _free(_HP)])
    run = cluster.reconcile("--dry-run")
    assert run.returncode == 0, run.stderr
    assert "CHANGE" in run.stdout
    assert "patch" not in (cluster.fake / "argv.log").read_text(encoding="utf-8")


def test_an_unreadable_static_order_changes_nothing_and_says_so(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE), _free(_HP)])
    cluster.env["GATE_LANE_STATIC_QUEUE_FILE"] = str(tmp_path / "absent.yaml")
    run = cluster.reconcile()
    assert run.returncode == 1
    assert "cannot read the static lane order" in run.stdout
    assert not cluster.patched()


def test_an_arch_conf_without_a_gate_line_changes_nothing(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE), _free(_HP)])
    conf = tmp_path / "workload-arch.conf"
    _ = conf.write_text("release x amd64 arm64: y\n", encoding="utf-8")
    cluster.env["GATE_LANE_ARCH_CONF"] = str(conf)
    run = cluster.reconcile()
    assert run.returncode == 1
    assert "cannot read the static lane order or the gate architectures" in run.stdout


def test_a_static_file_without_a_gates_queue_changes_nothing(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE), _free(_HP)])
    other = tmp_path / "other.yaml"
    _ = other.write_text("kind: Namespace\nmetadata:\n  name: gates\n", encoding="utf-8")
    cluster.env["GATE_LANE_STATIC_QUEUE_FILE"] = str(other)
    run = cluster.reconcile()
    assert run.returncode == 1
    assert "no gates-cq flavor list found" in run.stdout


def test_a_queue_with_no_cpu_resource_group_changes_nothing(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_free(_GMK)], lanes=[_GMK])
    cluster.write(
        "cq.json",
        {
            "metadata": {"resourceVersion": "1"},
            "spec": {"resourceGroups": [{"coveredResources": ["memory"], "flavors": []}]},
        },
    )
    run = cluster.reconcile()
    assert run.returncode == 1
    assert "no resource group covering cpu" in run.stdout


@pytest.mark.parametrize("which", ["nodes.json", "cq.json", "flavors.json"])
def test_a_failed_cluster_read_changes_nothing(tmp_path: Path, which: str) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE)], lanes=[_GMK, _PE])
    (cluster.fake / which).unlink()
    broken = tmp_path / "bin" / "kubectl"
    _ = broken.write_text(
        _FAKE_KUBECTL.replace(f'cat "$FAKE_DIR/{which}"', "echo refused >&2; exit 1"),
        encoding="utf-8",
    )
    run = cluster.reconcile()
    assert run.returncode == 1
    assert not cluster.patched()


def test_a_rejected_patch_fails_the_pass_so_the_next_pass_reapplies(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_saturated(_GMK), _free(_PE)], lanes=[_GMK, _PE])
    kubectl = tmp_path / "bin" / "kubectl"
    _ = kubectl.write_text(
        _FAKE_KUBECTL.replace(
            'printf \'%s\' "$6" >"$FAKE_DIR/patch.json"', "echo conflict >&2; exit 1"
        ),
        encoding="utf-8",
    )
    run = cluster.reconcile()
    assert run.returncode == 1
    assert "the next pass re-applies" in run.stderr


def test_a_usage_error_is_refused(tmp_path: Path) -> None:
    cluster = _pool(tmp_path, [_free(_GMK)], lanes=[_GMK])
    run = cluster.reconcile("--bogus")
    assert run.returncode == 1
    assert "usage:" in run.stderr
