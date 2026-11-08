"""The container-worker queue quota of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

These run the real `ci-runner/k3s/phase2/kueue/converge-worker-queues.sh --dry-run` against a stub
`kubectl` answering mocked worker churn-slot capacities, so the rendered quota is asserted as the
sum rule, never as a committed number.
"""

from __future__ import annotations

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
