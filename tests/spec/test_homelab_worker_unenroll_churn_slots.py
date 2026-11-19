"""CI churn-slot removal for unenrolled homelab workers.

This exercises the shared workload-class enrollment script with an arm64 worker
whose architecture appears in no CI scale-set declaration.  The Node must keep
advertising the extended resource at zero, so the queue reconciler can render a
zero worker-lane quota rather than continue scheduling on stale capacity.
"""

from __future__ import annotations

import stat
from pathlib import Path

from tests.hang_guard import run_under_hang_guard

__all__: list[str] = []

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "enroll-workload-classes.sh"
_NODE = "arm64-worker"
_NO_ARM64_CI = "release ci-amd64 amd64 unavailable\n"

_KUBECTL = """#!/bin/bash
printf 'kubectl %s\\n' "$*" >> "$STUB_LOG"
case "$*" in
  *"homelab-worker\\.livespec\\.dev/class"*) printf '%s' worker ;;
  *"kubernetes\\.io/arch"*) printf '%s' arm64 ;;
  *"allocatable.cpu"*) printf '%s' 12 ;;
  *"homelab-worker\\.livespec\\.dev/host"*) printf '%s' '' ;;
esac
"""


def test_an_architecture_without_a_ci_scale_set_advertises_zero_churn_slots(
    tmp_path: Path,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(_KUBECTL, encoding="utf-8")
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IXUSR)
    queues = bin_dir / "worker-queues"
    queues.write_text('#!/bin/bash\nprintf "worker-queues\\n" >> "$STUB_LOG"\n', encoding="utf-8")
    queues.chmod(queues.stat().st_mode | stat.S_IXUSR)
    conf = tmp_path / "workload-arch.conf"
    conf.write_text(_NO_ARM64_CI, encoding="utf-8")
    calls = tmp_path / "kubectl.log"

    result = run_under_hang_guard(
        ["/bin/bash", str(_SCRIPT), _NODE],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_LOG": str(calls),
            "WORKLOAD_ARCH_CONF": str(conf),
            "WORKER_QUEUES_CONVERGE": str(queues),
            "HOMELAB_WORKER_HOSTS_DIR": str(tmp_path / "hosts"),
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr
    patches = [
        call for call in calls.read_text(encoding="utf-8").splitlines() if "churn-slot" in call
    ]
    assert len(patches) == 1
    [patch] = patches
    assert '"ci-runner.io/churn-slot":"0"' in patch
