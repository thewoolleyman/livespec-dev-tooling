"""The M4 declaration retains capacity for the arm64 factory lane."""

from __future__ import annotations

import re
import stat
from pathlib import Path

import pytest

from tests.hang_guard import run_under_hang_guard

__all__: list[str] = []

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "homelab-worker" / "enroll-workload-classes.sh"
_HOSTS = _ROOT / "homelab-worker" / "hosts"
_WORKLOAD_ARCH = _ROOT / "ci-runner" / "k3s" / "phase2" / "workload-arch.conf"
_DECLARATION = _HOSTS / "macbook-m4-max.env"
_NODE = "macbook-m4-max-homelab-worker"

_KUBECTL = """#!/bin/bash
printf 'kubectl %s\\n' "$*" >> "$STUB_LOG"
case "$*" in
  *"homelab-worker\\.livespec\\.dev/host"*) printf '%s' macbook-m4-max ;;
  *"homelab-worker\\.livespec\\.dev/class"*) printf '%s' worker ;;
  *"kubernetes\\.io/arch"*) printf '%s' arm64 ;;
  *"allocatable.cpu"*) printf '%s' 12 ;;
esac
"""


def test_the_committed_m4_split_enrolls_the_arm64_factory_lane_with_its_recorded_share(
    tmp_path: Path,
) -> None:
    """The recorded factory capacity is sufficient for one arm64 sandbox."""
    split = re.search(
        r'^WORKER_MEASURED_CLASS_SPLIT="(?P<split>[^\"]+)"$',
        _DECLARATION.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    reason = re.search(
        r'^WORKER_MEASURED_CLASS_SPLIT_REASON="(?P<reason>[^\"]+)"$',
        _DECLARATION.read_text(encoding="utf-8"),
        flags=re.MULTILINE,
    )
    assert split and reason
    shares = dict(part.split("=", 1) for part in split["split"].split(","))
    factory_capacity = 12_000 * int(shares["factory"]) // 100
    assert factory_capacity >= 4_000
    assert "homelab-worker-arm64 factory lane" in reason["reason"]

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(_KUBECTL, encoding="utf-8")
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IXUSR)
    queues = bin_dir / "worker-queues"
    queues.write_text('#!/bin/bash\nprintf "worker-queues\\n" >> "$STUB_LOG"\n', encoding="utf-8")
    queues.chmod(queues.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "calls.log"

    result = run_under_hang_guard(
        ["/bin/bash", str(_SCRIPT), _NODE],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_LOG": str(log),
            "WORKLOAD_ARCH_CONF": str(_WORKLOAD_ARCH),
            "WORKER_QUEUES_CONVERGE": str(queues),
            "HOMELAB_WORKER_HOSTS_DIR": str(_HOSTS),
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert f"kubectl label node {_NODE} ci-runner.io/factory=true --overwrite" in log.read_text(
        encoding="utf-8"
    )
    assert f"factory: enrolled (share {factory_capacity}m CPU)" in result.stdout
