"""Removed worker pods must disappear before a same-name worker can rejoin."""

from __future__ import annotations

import stat
from pathlib import Path

from tests.hang_guard import run_under_hang_guard

__all__: list[str] = []


_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "homelab-worker" / "remove-worker.sh"
_HOST = "alpha"
_WORKER = f"{_HOST}-homelab-worker"


def _executable(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_remove_waits_until_daemonset_pods_of_the_deleted_node_are_gone(tmp_path: Path) -> None:
    """A rejoin must not race the API's delayed garbage collection of DaemonSet pods."""
    state = tmp_path / "state"
    state.mkdir()
    (state / "hosts").mkdir()
    (state / "hosts" / f"{_HOST}.env").write_text("WORKER_HOST_OS=Darwin\n", encoding="utf-8")
    (state / "node").write_text("true", encoding="utf-8")
    (state / "pods-before-delete").write_text(
        "kube-system/flannel-before-delete Running DaemonSet\n", encoding="utf-8"
    )
    (state / "stale-pods").write_text(
        "kube-system/flannel-from-deleted-node Running DaemonSet\n", encoding="utf-8"
    )
    (state / "calls.log").write_text("", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _executable(
        path=bin_dir / "kubectl",
        body="""#!/bin/bash
s="$STUB_STATE"
printf 'kubectl %s\\n' "$*" >> "$s/calls.log"
case "$1 $2" in
  "get node") [ ! -f "$s/node" ] || printf '%s true' "$3" ;;
  "get pods")
    if [ -f "$s/node-deleted" ]; then
      if [ -f "$s/stale-pods" ]; then
        cat "$s/stale-pods"
        rm "$s/stale-pods"
      fi
    else
      cat "$s/pods-before-delete"
    fi ;;
  "delete node") touch "$s/node-deleted"; rm -f "$s/node" ;;
esac
""",
    )
    _executable(
        path=bin_dir / "limactl",
        body="""#!/bin/bash
shift 5
case "$1 $2" in
  "docker inspect") printf 'true\\n' ;;
  "rm -rf") exec "$@" ;;
esac
""",
    )
    _executable(path=bin_dir / "worker-queues", body="#!/bin/bash\nexit 0\n")
    _executable(path=bin_dir / "sleep", body="#!/bin/bash\nexit 0\n")

    result = run_under_hang_guard(
        ["/bin/bash", str(_SCRIPT), _HOST, "--state-root", str(tmp_path / "worker-state")],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{bin_dir}:/usr/bin:/bin",
            "HOMELAB_WORKER_HOSTS_DIR": str(state / "hosts"),
            "STUB_STATE": str(state),
            "WORKER_QUEUES_CONVERGE": str(bin_dir / "worker-queues"),
        },
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    calls = (state / "calls.log").read_text(encoding="utf-8").splitlines()
    deletion = calls.index(f"kubectl delete node {_WORKER} --wait --ignore-not-found")
    pod_reads_after_deletion = [
        call for call in calls[deletion + 1 :] if call.startswith("kubectl get pods")
    ]
    assert len(pod_reads_after_deletion) >= 2
