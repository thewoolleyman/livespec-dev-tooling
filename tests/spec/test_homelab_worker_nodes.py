"""The homelab worker start task of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

These run the real `homelab-worker/start-homelab-worker-node-container.sh` under the system
`/bin/bash` (bash 3.2 on macOS, because a worker host is not a development box) against stub
`uname`, `brew` and `limactl` executables on a minimal PATH. Each stub appends its argv to a
shared call log, so an assertion about what the task did NOT do — no Lima install or upgrade, no
VM recreation, no second worker — is an assertion about that log.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_DIR = _REPO_ROOT / "homelab-worker"
_SCRIPT = _WORKER_DIR / "start-homelab-worker-node-container.sh"
_GIB = 1024 * 1024 * 1024

_STUB_LIMACTL = """#!/bin/bash
set -eu
printf 'limactl %s\\n' "$*" >> "$STUB_LOG"
state="$STUB_STATE"
case "${1:-}" in
  --version) cat "$state/lima-version"; exit 0 ;;
  list)
    shift
    fmt=""
    name=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --format) fmt="$2"; shift 2 ;;
        *) name="$1"; shift ;;
      esac
    done
    for f in "$state"/instances/*; do
      [ -e "$f" ] || continue
      n="${f##*/}"
      if [ -n "$name" ] && [ "$n" != "$name" ]; then continue; fi
      if [ "$fmt" = "{{.Name}}" ]; then echo "$n"; else cat "$f"; fi
    done
    exit 0 ;;
  create)
    for a in "$@"; do case "$a" in --name=*) n="${a#--name=}" ;; esac; done
    echo "Stopped 0 0 0" > "$state/instances/$n"
    exit 0 ;;
  start) exit 0 ;;
  disk)
    case "${2:-}" in
      list) for d in "$state"/disks/*; do [ -e "$d" ] && printf '{"name":"%s"}\n' "${d##*/}"; done; exit 0 ;;
      create) touch "$state/disks/$3"; exit 0 ;;
    esac ;;
  shell)
    cat > "$state/probe-stdin"
    cat "$state/probe-output"
    exit "$(cat "$state/probe-exit")" ;;
esac
exit 0
"""

_STUB_BREW = """#!/bin/bash
set -eu
printf 'brew %s\\n' "$*" >> "$STUB_LOG"
if [ "$1 $2" = "install lima" ]; then
  cp "$STUB_STATE/limactl.stub" "$STUB_BIN/limactl"
  chmod +x "$STUB_BIN/limactl"
  echo "limactl version 2.2.1" > "$STUB_STATE/lima-version"
fi
"""


@dataclass(frozen=True, kw_only=True)
class _Host:
    bin_dir: Path
    state: Path
    log: Path


def _write_exec(*, path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def host(tmp_path: Path) -> _Host:
    bin_dir = tmp_path / "bin"
    state = tmp_path / "state"
    bin_dir.mkdir()
    (state / "instances").mkdir(parents=True)
    (state / "disks").mkdir()
    (state / "probe-output").write_text("PRESENT apparmor\n", encoding="utf-8")
    (state / "probe-exit").write_text("0\n", encoding="utf-8")
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    _write_exec(path=bin_dir / "uname", text='#!/bin/bash\necho "${STUB_UNAME:-Darwin}"\n')
    _write_exec(path=bin_dir / "brew", text=_STUB_BREW)
    (state / "limactl.stub").write_text(_STUB_LIMACTL, encoding="utf-8")
    return _Host(bin_dir=bin_dir, state=state, log=log)


def _install_lima(*, host: _Host, version: str) -> None:
    _write_exec(path=host.bin_dir / "limactl", text=_STUB_LIMACTL)
    (host.state / "lima-version").write_text(f"limactl version {version}\n", encoding="utf-8")


def _add_instance(
    *, host: _Host, name: str, status: str, cpus: int, memory_gib: int, disk_gib: int
) -> None:
    (host.state / "instances" / name).write_text(
        f"{status} {cpus} {memory_gib * _GIB} {disk_gib * _GIB}\n", encoding="utf-8"
    )


def _run(*, host: _Host, args: list[str]) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{host.bin_dir}:/usr/bin:/bin",
        "HOME": str(host.state),
        "STUB_LOG": str(host.log),
        "STUB_STATE": str(host.state),
        "STUB_BIN": str(host.bin_dir),
    }
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=60,
    )


def _calls(*, host: _Host) -> list[str]:
    return host.log.read_text(encoding="utf-8").splitlines()


def test_undeclared_host_is_refused_naming_the_declared_hosts_before_any_host_change(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=["spare-pc"])
    assert result.returncode != 0
    assert "spare-pc" in result.stderr
    assert "macbook-m4-max" in result.stderr
    assert "macbook-air" in result.stderr
    assert _calls(host=host) == []


def test_absent_lima_is_installed_through_homebrew_and_the_named_vz_vm_is_created(
    host: _Host,
) -> None:
    result = _run(host=host, args=["macbook-m4-max"])
    assert result.returncode == 0, result.stderr
    calls = _calls(host=host)
    assert "brew install lima" in calls
    creates = [c for c in calls if c.startswith("limactl create ")]
    assert len(creates) == 1
    assert "--name=macbook-m4-max-homelab-worker" in creates[0]
    assert "--vm-type=vz" in creates[0]
    assert "--cpus=12" in creates[0]
    assert "limactl start --tty=false macbook-m4-max-homelab-worker" in calls


def test_installed_lima_at_or_above_the_minimum_is_reused_without_install_or_upgrade(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=["macbook-air"])
    assert result.returncode == 0, result.stderr
    assert [c for c in _calls(host=host) if c.startswith("brew ")] == []
    assert "reusing Lima 2.2.1" in result.stdout


def test_installed_lima_older_than_the_minimum_is_refused_by_version(host: _Host) -> None:
    _install_lima(host=host, version="1.2.0")
    result = _run(host=host, args=["macbook-air"])
    assert result.returncode != 0
    assert "1.2.0" in result.stderr
    assert "2.0.0" in result.stderr
    calls = _calls(host=host)
    assert [c for c in calls if c.startswith("brew ")] == []
    assert [c for c in calls if c.startswith("limactl create")] == []


def test_rerun_starts_the_existing_vm_in_place_and_never_recreates_it(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    _add_instance(
        host=host,
        name="macbook-air-homelab-worker",
        status="Stopped",
        cpus=6,
        memory_gib=16,
        disk_gib=60,
    )
    result = _run(host=host, args=["macbook-air"])
    assert result.returncode == 0, result.stderr
    calls = _calls(host=host)
    assert "limactl start --tty=false macbook-air-homelab-worker" in calls
    assert [c for c in calls if c.split()[1] in {"create", "delete", "stop", "factory-reset"}] == []


def test_rerun_keeps_a_running_vm_without_starting_or_recreating_it(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    _add_instance(
        host=host,
        name="macbook-air-homelab-worker",
        status="Running",
        cpus=6,
        memory_gib=16,
        disk_gib=60,
    )
    result = _run(host=host, args=["macbook-air"])
    assert result.returncode == 0, result.stderr
    assert [
        c for c in _calls(host=host) if c.split()[1] in {"create", "delete", "stop", "start"}
    ] == []


def test_a_second_worker_on_the_same_host_is_refused_naming_the_existing_worker(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    _add_instance(
        host=host,
        name="macbook-m4-max-homelab-worker",
        status="Running",
        cpus=12,
        memory_gib=64,
        disk_gib=100,
    )
    result = _run(host=host, args=["macbook-air"])
    assert result.returncode != 0
    assert "macbook-m4-max-homelab-worker" in result.stderr
    assert [c for c in _calls(host=host) if c.startswith("limactl create")] == []


def test_a_vm_whose_declared_setting_changed_is_refused_naming_the_setting(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    _add_instance(
        host=host,
        name="macbook-air-homelab-worker",
        status="Stopped",
        cpus=4,
        memory_gib=16,
        disk_gib=60,
    )
    result = _run(host=host, args=["macbook-air"])
    assert result.returncode != 0
    assert "WORKER_VM_CPUS" in result.stderr
    assert [c for c in _calls(host=host) if c.split()[1] in {"create", "delete", "start"}] == []


def test_a_host_declared_for_another_platform_is_refused(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.bin_dir / "uname").write_text("#!/bin/bash\necho Linux\n", encoding="utf-8")
    result = _run(host=host, args=["macbook-air"])
    assert result.returncode != 0
    assert "Darwin" in result.stderr
    assert _calls(host=host) == []


def test_every_declared_host_is_data_for_the_same_code_path() -> None:
    hosts = sorted(p.stem for p in (_WORKER_DIR / "hosts").glob("*.env"))
    assert hosts == ["macbook-air", "macbook-m4-max"]
    script = _SCRIPT.read_text(encoding="utf-8")
    for name in hosts:
        assert name not in script
        keys = {
            line.split("=", 1)[0]
            for line in (_WORKER_DIR / "hosts" / f"{name}.env")
            .read_text(encoding="utf-8")
            .splitlines()
            if line and not line.startswith("#")
        }
        assert keys == {
            "WORKER_HOST_OS",
            "WORKER_VM_CPUS",
            "WORKER_VM_MEMORY_GIB",
            "WORKER_VM_DISK_GIB",
            "WORKER_DATA_DISK_GIB",
        }


def test_a_new_vm_gets_an_xfs_data_disk_created_once(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=["macbook-air"])
    assert result.returncode == 0, result.stderr
    calls = _calls(host=host)
    assert [c for c in calls if c.startswith("limactl disk create ")] == [
        "limactl disk create hwdata --size=90GiB --format=raw"
    ]
    create = next(c for c in calls if c.startswith("limactl create "))
    assert '"name":"hwdata"' in create
    assert '"fsType":"xfs"' in create
    assert (
        "limactl shell --workdir / macbook-air-homelab-worker sudo bash -s -- /mnt/lima-hwdata"
        in calls
    )


def test_the_data_disk_filesystem_label_fits_the_xfs_limit() -> None:
    # Lima formats an additional disk with `mkfs.<fs> -L lima-<disk name>` (v2.2.1
    # boot.Linux/05-lima-disks.sh), and an XFS label holds at most 12 characters. A longer
    # name leaves the disk unformatted and unmounted, measured on macbook-m4-max 2026-11-04.
    script = _SCRIPT.read_text(encoding="utf-8")
    declared = [line for line in script.splitlines() if line.startswith("data_disk=")]
    assert declared == ['data_disk="hwdata"']
    assert len("lima-hwdata") <= 12


def test_a_missing_vm_capability_stops_the_task_naming_it_with_its_remedy(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / "probe-output").write_text(
        "PRESENT tun\nMISSING apparmor: boot the VM kernel with apparmor=1\n", encoding="utf-8"
    )
    (host.state / "probe-exit").write_text("1\n", encoding="utf-8")
    result = _run(host=host, args=["macbook-air"])
    assert result.returncode != 0
    assert "MISSING apparmor: boot the VM kernel with apparmor=1" in result.stderr
    assert "worker container was not started" in result.stderr
    assert (host.state / "probe-stdin").read_text(encoding="utf-8") == (
        _WORKER_DIR / "probe-vm-capabilities.sh"
    ).read_text(encoding="utf-8")


def test_a_passing_probe_is_recorded_beside_the_worker_state(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=["macbook-air"])
    assert result.returncode == 0, result.stderr
    report = (
        host.state / ".local" / "state" / "livespec-homelab-worker" / "macbook-air-homelab-worker"
    )
    assert (report / "vm-capabilities.txt").read_text(encoding="utf-8") == "PRESENT apparmor\n"
