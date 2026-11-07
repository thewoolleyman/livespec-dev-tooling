"""Automatic enrollment by workload class, `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

These run the real `homelab-worker/enroll-workload-classes.sh` under `/bin/bash` against a stub
`kubectl` that answers the Node's labels and allocatable CPU from mocked values and logs every
call, and against a mocked architecture list, so no assertion restates a committed value.
"""

from __future__ import annotations

import stat
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "enroll-workload-classes.sh"
_NODE = "alpha-homelab-worker"

_STUB = """#!/bin/bash
printf 'kubectl %s\\n' "$*" >> "$STUB_LOG"
case "$*" in
  *"homelab-worker\\.livespec\\.dev/class"*) printf '%s' "$NODE_CLASS" ;;
  *"kubernetes\\.io/arch"*) printf '%s' "$NODE_ARCH" ;;
  *"allocatable.cpu"*) printf '%s' "$NODE_CPU" ;;
esac
exit 0
"""


def _run(
    *, tmp_path: Path, conf: str, arch: str = "arm64", cpu: str = "30", node_class: str = "worker"
) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    stub = bin_dir / "kubectl"
    stub.write_text(_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    (tmp_path / "list.conf").write_text(conf, encoding="utf-8")
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    result = subprocess.run(
        ["/bin/bash", str(_SCRIPT), _NODE],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_LOG": str(log),
            "WORKLOAD_ARCH_CONF": str(tmp_path / "list.conf"),
            "NODE_ARCH": arch,
            "NODE_CPU": cpu,
            "NODE_CLASS": node_class,
        },
        check=False,
        timeout=30,
    )
    return result, log.read_text(encoding="utf-8").splitlines()


_AMD64_ONLY = (
    "release some-k3s amd64 arm64: no arm64 job image\n"
    "gate gate amd64 arm64: gate image amd64-only\n"
    "factory python-agent amd64 arm64: agent layer amd64-only\n"
)
_ARM64_TOO = (
    "release some-k3s amd64 x\nrelease some-arm64-k3s arm64 x\n"
    "gate gate amd64,arm64 none\nfactory python-agent amd64,arm64 none\n"
)


def test_a_class_without_the_nodes_architecture_is_not_enrolled_and_is_named(
    tmp_path: Path,
) -> None:
    result, calls = _run(tmp_path=tmp_path, conf=_AMD64_ONLY)
    assert result.returncode == 0, result.stderr
    assert not [c for c in calls if "k3s-role=arc-runner-host" in c or "factory=true" in c]
    assert not [c for c in calls if "churn-slot" in c]
    assert "CI: NOT enrolled" in result.stdout
    assert "factory: NOT enrolled: arm64: agent layer amd64-only" in result.stdout
    assert "gate: NOT enrolled: arm64: gate image amd64-only" in result.stdout


def test_every_class_declaring_the_nodes_architecture_is_enrolled(tmp_path: Path) -> None:
    result, calls = _run(tmp_path=tmp_path, conf=_ARM64_TOO, cpu="30")
    assert result.returncode == 0, result.stderr
    assert f"kubectl label node {_NODE} k3s-role=arc-runner-host --overwrite" in calls
    assert f"kubectl label node {_NODE} ci-runner.io/factory=true --overwrite" in calls
    [patch] = [c for c in calls if "churn-slot" in c]
    assert "--subresource=status" in patch
    assert "gate: eligible" in result.stdout


@pytest.mark.parametrize(("cpu", "slots"), [("30", 3), ("12", 1), ("11500m", 1), ("2", 1)])
def test_the_churn_slot_capacity_is_one_third_of_allocatable_cpu_at_the_fleet_slot_size(
    tmp_path: Path, cpu: str, slots: int
) -> None:
    millicores = int(cpu[:-1]) if cpu.endswith("m") else int(cpu) * 1000
    assert slots == max(1, (millicores // 3) // 2730)
    result, calls = _run(tmp_path=tmp_path, conf=_ARM64_TOO, cpu=cpu)
    assert result.returncode == 0, result.stderr
    [patch] = [c for c in calls if "churn-slot" in c]
    assert f'"ci-runner.io/churn-slot":"{slots}"' in patch


def test_a_node_that_is_not_a_container_worker_is_refused_untouched(tmp_path: Path) -> None:
    result, calls = _run(tmp_path=tmp_path, conf=_ARM64_TOO, node_class="")
    assert result.returncode != 0
    assert "not a container worker" in result.stderr
    assert not [c for c in calls if " label " in c or " patch " in c]


def test_a_non_cpu_allocatable_value_is_refused_untouched(tmp_path: Path) -> None:
    result, calls = _run(tmp_path=tmp_path, conf=_ARM64_TOO, cpu="lots")
    assert result.returncode != 0
    assert not [c for c in calls if " label " in c or " patch " in c]
