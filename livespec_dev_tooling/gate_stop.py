"""Stop a detached gate by its durable run record."""

from __future__ import annotations

import argparse
import getpass
import os
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from livespec_dev_tooling.gate_credential import with_gates_kubeconfig
from livespec_dev_tooling.gate_remote_invocation import default_gate_command_runner

__all__: list[str] = []


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="gate-stop")
    _ = parser.add_argument("--run-dir", required=True, type=Path)
    return parser.parse_args()


def _read(*, path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _alive(*, pid: int) -> bool:
    try:
        state = (Path("/proc") / str(pid) / "status").read_text(encoding="utf-8")
    except OSError:
        return False
    return "State:\tZ" not in state


def _tree(*, root: int) -> set[int]:
    parents: dict[int, int] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "status").read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        parent = next((line[5:] for line in fields if line.startswith("PPid:")), "").strip()
        if parent.isdigit():
            parents[int(entry.name)] = int(parent)
    found = {root}
    while True:
        added = {pid for pid, parent in parents.items() if parent in found} - found
        if not added:
            return found
        found.update(added)


def _stop(*, root: int) -> set[int]:
    pids = _tree(root=root)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            continue
    deadline = time.monotonic() + 3
    alive = {pid for pid in pids if _alive(pid=pid)}
    while alive and time.monotonic() < deadline:
        time.sleep(0.05)
        alive = {pid for pid in pids if _alive(pid=pid)}
    for pid in alive:
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            continue
    return {pid for pid in pids if _alive(pid=pid)}


def _job_gone(*, run_dir: Path) -> bool:
    name = _read(path=run_dir / "job_name")
    if not name:
        return True
    namespace = _read(path=run_dir / "namespace") or "gates"
    get = ["kubectl", "--namespace", namespace, "get", "job", name]
    result = default_gate_command_runner(
        argv=with_gates_kubeconfig(argv=get), cwd=run_dir
    ).value_or(None)
    if result is None:
        return False
    if result.returncode != 0:
        return "notfound" in result.stderr.lower() or "not found" in result.stderr.lower()
    delete = ["kubectl", "--namespace", namespace, "delete", "job", name]
    deleted = default_gate_command_runner(
        argv=with_gates_kubeconfig(argv=delete), cwd=run_dir
    ).value_or(None)
    if deleted is None or deleted.returncode != 0:
        return False
    checked = default_gate_command_runner(
        argv=with_gates_kubeconfig(argv=get), cwd=run_dir
    ).value_or(None)
    return checked is not None and checked.returncode != 0 and "notfound" in checked.stderr.lower()


def main() -> int:
    """Record the stop before signalling every known run process and its Job."""
    run_dir = _args().run_dir
    if (run_dir / "exit_code").is_file():
        _ = sys.stdout.write(f"gate-stop: run {run_dir.name} is already terminal\n")
        return 1
    pid = _read(path=run_dir / "pid")
    if not pid.isdigit():
        _ = sys.stdout.write(f"gate-stop: run {run_dir.name} has no live pid\n")
        return 1
    when = datetime.now(tz=timezone.utc).isoformat().replace("+00:00", "Z")
    _ = (run_dir / "stopped").write_text(
        f"stopped_at={when}\nrequested_by={getpass.getuser() or 'unknown'}\n", encoding="utf-8"
    )
    survivors = _stop(root=int(pid))
    job_gone = _job_gone(run_dir=run_dir)
    if not survivors and job_gone:
        _ = sys.stdout.write(f"gate-stop: stopped {run_dir.name}\n")
        return 0
    if survivors:
        _ = sys.stdout.write(f"gate-stop: surviving processes: {sorted(survivors)}\n")
    if not job_gone:
        _ = sys.stdout.write(f"gate-stop: surviving Job {_read(path=run_dir / 'job_name')}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
