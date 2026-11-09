"""The container-worker queue quota of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

These run the real `ci-runner/k3s/phase2/kueue/converge-worker-queues.sh --dry-run` against a stub
`kubectl` answering mocked worker churn-slot capacities, so the rendered quota is asserted as the
sum rule, never as a committed number.
"""

from __future__ import annotations

import json
import re
import stat
import subprocess
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_KUEUE = Path(__file__).resolve().parents[2] / "ci-runner" / "k3s" / "phase2" / "kueue"
_SCRIPT = _KUEUE / "converge-worker-queues.sh"

_STUB = """#!/bin/bash
printf 'kubectl %s\\n' "$*" >> "$STUB_LOG"
case "$*" in
  *"kubernetes.io/arch=arm64"*) printf '%b' "$ARM64_SLOTS" ;;
  *"kubernetes.io/arch=amd64"*) printf '%b' "$AMD64_SLOTS" ;;
esac
"""

_TEMPLATE = """apiVersion: kueue.x-k8s.io/v1beta2
kind: ClusterQueue
metadata:
  name: some-arm64-cq
spec:
  resourceGroups:
    - flavors:
        - resources:
            - name: "ci-runner.io/churn-slot"
              nominalQuota: @WORKER_CHURN_SLOTS@
"""


def _render(*, tmp_path: Path, arm64: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "kubectl"
    stub.write_text(_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    queues = tmp_path / "worker"
    queues.mkdir()
    (queues / "cluster-queue-some-repo-arm64.yaml").write_text(_TEMPLATE, encoding="utf-8")
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_LOG": str(log),
            "WORKER_QUEUE_DIR": str(queues),
            "ARM64_SLOTS": arm64,
            "AMD64_SLOTS": "99\\n",
        },
        check=False,
        timeout=30,
    )
    return result, log.read_text(encoding="utf-8").splitlines()


def _quota(*, stdout: str) -> int:
    manifest = yaml.safe_load(stdout.split("\n", 1)[1])
    return int(manifest["spec"]["resourceGroups"][0]["flavors"][0]["resources"][0]["nominalQuota"])


@pytest.mark.parametrize(
    ("slots", "total"), [("3\\n", 3), ("3\\n2\\n", 5), ("", 0), ("2\\n\\n", 2)]
)
def test_the_quota_is_the_sum_of_the_enrolled_workers_of_the_templates_architecture(
    tmp_path: Path, slots: str, total: int
) -> None:
    result, calls = _render(tmp_path=tmp_path, arm64=slots)
    assert result.returncode == 0, result.stderr
    assert _quota(stdout=result.stdout) == total
    assert all("kubernetes.io/arch=arm64" in c for c in calls)
    assert all("homelab-worker.livespec.dev/class=worker" in c for c in calls)


def test_a_dry_run_applies_nothing(tmp_path: Path) -> None:
    _, calls = _render(tmp_path=tmp_path, arm64="3\\n")
    assert not [c for c in calls if " apply " in c]


def test_every_committed_worker_template_carries_the_quota_placeholder() -> None:
    templates = sorted((_KUEUE / "worker").glob("cluster-queue-*.yaml"))
    assert templates
    assert all("@WORKER_CHURN_SLOTS@" in t.read_text(encoding="utf-8") for t in templates)


def test_no_committed_worker_template_borrows_from_the_cohort() -> None:
    """A worker queue never borrows another architecture's churn slots.

    Its runners schedule only on its own architecture's workers, so a slot
    borrowed from the cohort would be held by a pod that cannot start.
    """
    templates = sorted((_KUEUE / "worker").glob("cluster-queue-*.yaml"))
    assert templates
    for template in templates:
        text = template.read_text(encoding="utf-8").replace("@WORKER_CHURN_SLOTS@", "0")
        queues = [d for d in yaml.safe_load_all(text) if d and d.get("kind") == "ClusterQueue"]
        assert queues, template.name
        for queue in queues:
            resources = [
                resource
                for group in queue["spec"]["resourceGroups"]
                for flavor in group["flavors"]
                for resource in flavor["resources"]
            ]
            assert resources, template.name
            assert all(
                resource.get("borrowingLimit") == 0 for resource in resources
            ), f"{template.name}: every resource must carry borrowingLimit 0"


_GATES_STUB = """#!/bin/bash
printf 'kubectl %s\\n' "$*" >> "$STUB_LOG"
case "$*" in
  *"gate-share-millicores"*) printf '%b' "$GATE_SHARES" ;;
  *"get clusterqueue gates-cq"*) [ -n "$NO_GATES_CQ" ] && exit 1; printf '%s' "$GATES_CQ" ;;
esac
"""

_FLEET_GATES_CQ = {
    "spec": {
        "resourceGroups": [
            {
                "coveredResources": ["cpu", "memory"],
                "flavors": [
                    {"name": "gates-hp-flavor", "resources": []},
                    {"name": "gates-worker-arm64-flavor", "resources": []},
                    {"name": "gates-flavor", "resources": []},
                ],
            }
        ]
    }
}


def _render_gates(
    *, tmp_path: Path, shares: str, no_gates_cq: bool = False
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    stub = bin_dir / "kubectl"
    stub.write_text(_GATES_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    worker = tmp_path / "worker"
    worker.mkdir()
    template = (_KUEUE / "worker" / "gates-worker-flavor.yaml").read_text(encoding="utf-8")
    (worker / "gates-worker-flavor.yaml").write_text(template, encoding="utf-8")
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), "--dry-run"],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_LOG": str(log),
            "WORKER_QUEUE_DIR": str(worker),
            "GATE_SHARES": shares,
            "GATES_CQ": json.dumps(_FLEET_GATES_CQ),
            "NO_GATES_CQ": "1" if no_gates_cq else "",
        },
        check=False,
        timeout=30,
    )
    return result, log.read_text(encoding="utf-8").splitlines()


def _gates_patch(*, stdout: str) -> list[dict[str, object]]:
    [line] = [ln for ln in stdout.splitlines() if ln.startswith('[{"op"')]
    [op] = json.loads(line)
    assert op["op"] == "replace"
    assert op["path"] == "/spec/resourceGroups/0/flavors"
    return list(op["value"])


@pytest.mark.parametrize(
    ("shares", "gates"),
    [("arm64 4000\\n", 1), ("arm64 10000\\n", 2), ("arm64 4000\\narm64 15000\\n", 4)],
)
def test_the_worker_gate_quota_is_whole_gates_of_the_enrolled_shares(
    tmp_path: Path, shares: str, gates: int
) -> None:
    result, _ = _render_gates(tmp_path=tmp_path, shares=shares)
    assert result.returncode == 0, result.stderr
    worker = [
        f
        for f in _gates_patch(stdout=result.stdout)
        if f["name"] == "gates-worker-taint-arm64-flavor"
    ]
    assert worker == [
        {
            "name": "gates-worker-taint-arm64-flavor",
            "resources": [
                {"name": "cpu", "nominalQuota": gates * 5},
                {"name": "memory", "nominalQuota": f"{gates * 8}Gi"},
            ],
        }
    ]


def test_the_worker_flavors_come_first_and_the_fleet_gate_flavors_keep_their_order(
    tmp_path: Path,
) -> None:
    # First, not last: an enrolled worker takes its own share of the gates its
    # architecture can run, rather than only the gates the fleet's nodes have no
    # quota left for. A gate whose required kubernetes.io/arch excludes the
    # worker's is never assigned the worker flavor, so order moves no amd64-only
    # gate onto an arm64 worker.
    result, _ = _render_gates(tmp_path=tmp_path, shares="arm64 4000\n")
    assert result.returncode == 0, result.stderr
    names = [f["name"] for f in _gates_patch(stdout=result.stdout)]
    assert names == ["gates-worker-taint-arm64-flavor", "gates-hp-flavor", "gates-flavor"]


def test_a_worker_no_longer_enrolled_drops_out_of_gates_cq(tmp_path: Path) -> None:
    result, _ = _render_gates(tmp_path=tmp_path, shares="")
    assert result.returncode == 0, result.stderr
    names = [f["name"] for f in _gates_patch(stdout=result.stdout)]
    assert names == ["gates-hp-flavor", "gates-flavor"]


def test_the_worker_gate_flavor_selects_its_architecture_and_admits_only_class_tolerating_gates(
    tmp_path: Path,
) -> None:
    result, _ = _render_gates(tmp_path=tmp_path, shares="arm64 4000\n")
    assert result.returncode == 0, result.stderr
    manifests = "\n".join(
        line
        for line in result.stdout.splitlines()
        if not line.startswith(("converge-worker-queues:", '[{"op"'))
    )
    [flavor] = [doc for doc in yaml.safe_load_all(manifests) if doc]
    assert flavor["kind"] == "ResourceFlavor"
    assert flavor["metadata"]["name"] == "gates-worker-taint-arm64-flavor"
    assert flavor["spec"]["nodeLabels"] == {
        "homelab-worker.livespec.dev/class": "worker",
        "kubernetes.io/arch": "arm64",
    }
    # A nodeTaint, never an injected toleration: Kueue assigns the flavor only to a
    # gate that already tolerates the class taint, so a gate from an older
    # vendored renderer (no arch rule) can never be placed on a worker.
    assert flavor["spec"]["nodeTaints"] == [
        {"key": "homelab-worker.livespec.dev/class", "value": "worker", "effect": "NoSchedule"}
    ]
    assert "tolerations" not in flavor["spec"]


def test_the_gate_template_tolerates_the_class_taint_and_requires_its_declared_arches() -> None:
    """Only the current template's gates tolerate the class taint the worker flavors carry."""
    template = (
        Path(__file__).resolve().parents[2]
        / "ci-runner"
        / "k3s"
        / "phase2"
        / "gates"
        / "gate-job-template.yaml"
    ).read_text(encoding="utf-8")
    toleration = re.search(
        r"- key: homelab-worker\.livespec\.dev/class\n\s+operator: Equal\n"
        r"\s+value: worker\n\s+effect: NoSchedule",
        template,
    )
    assert toleration is not None
    required = template.index("requiredDuringSchedulingIgnoredDuringExecution:")
    assert "key: kubernetes.io/arch" in template[required : required + 400]
    assert "values: [@@GATE_ARCHES@@]" in template[required : required + 400]


def test_a_dry_run_patches_and_applies_nothing(tmp_path: Path) -> None:
    _, calls = _render_gates(tmp_path=tmp_path, shares="arm64 4000\n")
    assert not [c for c in calls if " apply " in c or " patch " in c]


def test_a_cluster_without_gates_cq_is_left_alone(tmp_path: Path) -> None:
    result, calls = _render_gates(tmp_path=tmp_path, shares="arm64 4000\n", no_gates_cq=True)
    assert result.returncode == 0, result.stderr
    assert "gates-cq is not present" in result.stderr
    assert not [c for c in calls if " patch " in c]
