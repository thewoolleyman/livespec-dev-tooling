"""Factory admission is cleared with factory enrollment, per “Leaving a workload class”.

The real enrollment script runs against a stub ``kubectl`` and a mocked workload
architecture list.  The stub records each label operation, so this test proves
the command the production cluster receives without contacting a cluster.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from tests.hang_guard import run_under_hang_guard

__all__: list[str] = []

pytestmark = pytest.mark.integration

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "enroll-workload-classes.sh"
_NODE = "alpha-homelab-worker"

_KUBECTL = """#!/bin/bash
printf 'kubectl %s\\n' "$*" >> "$STUB_LOG"
case "$*" in
  *"homelab-worker\\.livespec\\.dev/host"*) printf '%s' "$NODE_HOST" ;;
  *"homelab-worker\\.livespec\\.dev/class"*) printf '%s' worker ;;
  *"kubernetes\\.io/arch"*) printf '%s' arm64 ;;
  *"allocatable.cpu"*) printf '%s' 30 ;;
esac
"""


def test_unenrolling_factory_also_closes_factory_admission(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    kubectl = bin_dir / "kubectl"
    kubectl.write_text(_KUBECTL, encoding="utf-8")
    kubectl.chmod(kubectl.stat().st_mode | stat.S_IXUSR)
    queues = bin_dir / "worker-queues"
    queues.write_text("#!/bin/bash\n", encoding="utf-8")
    queues.chmod(queues.stat().st_mode | stat.S_IXUSR)
    arch_conf = tmp_path / "workload-arch.conf"
    arch_conf.write_text(
        "release arm64-runner arm64 supported\n"
        "gate arm64-gate arm64 supported\n"
        "factory python-agent amd64 unsupported\n",
        encoding="utf-8",
    )
    calls = tmp_path / "calls.log"
    calls.touch()

    result = run_under_hang_guard(
        ["/bin/bash", str(_SCRIPT), _NODE],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "STUB_LOG": str(calls),
            "WORKLOAD_ARCH_CONF": str(arch_conf),
            "WORKER_QUEUES_CONVERGE": str(queues),
            "NODE_HOST": "",
            "HOMELAB_WORKER_HOSTS_DIR": str(tmp_path / "hosts"),
        },
        check=False,
    )

    assert result.returncode == 0, result.stderr
    recorded = calls.read_text(encoding="utf-8").splitlines()
    assert f"kubectl label node {_NODE} ci-runner.io/factory-" in recorded
    assert f"kubectl label node {_NODE} ci-runner.io/factory-admit=false --overwrite" in recorded
