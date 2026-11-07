"""The homelab worker start task of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

These run the real `homelab-worker/start-homelab-worker-node-container.sh` under the system
`/bin/bash` (bash 3.2 on macOS, because a worker host is not a development box) against stub
`uname`, `brew` and `limactl` executables on a minimal PATH. Each stub appends its argv to a
shared call log, so an assertion about what the task did NOT do — no Lima install or upgrade, no
VM recreation, no second worker — is an assertion about that log.
"""

from __future__ import annotations

import hashlib
import re
import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

# Integration tier: each test runs the real script under /bin/bash against stub executables
# and mocked config, so the script's whole control flow is exercised.
pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_WORKER_DIR = _REPO_ROOT / "homelab-worker"
_SCRIPT = _WORKER_DIR / "start-homelab-worker-node-container.sh"
_GIB = 1024 * 1024 * 1024
# Mocked host declarations: the tests never read the committed hosts/ values.
_HOSTS = {
    "alpha": {"cpus": 3, "memory_gib": 5, "disk_gib": 7, "data_gib": 11, "lan": "10.99.0.21/24"},
    "beta": {"cpus": 13, "memory_gib": 17, "disk_gib": 19, "data_gib": 23, "lan": "10.99.0.22/24"},
    "delta": {"cpus": 2, "memory_gib": 3, "disk_gib": 5, "data_gib": 7},
}
# A mocked collector configuration and pin: the tests never fetch the real one.
_COLLECTOR_COMMIT = "c" * 40
_COLLECTOR_FILE = "config.homelab-worker.yaml"
_COLLECTOR_BYTES = b"# mocked collector configuration\n"
_INGEST_KEY = "mocked-ingest-key-value"

# A mocked container-hook bundle: the tests never deliver the committed one.
_HOOK_VERSION = "9.9.9"
_HOOK_BYTES = b"// mocked fleet container hook\n"
# A mocked cache-span emitter: the tests never deliver the committed one.
_SPAN_BYTES = b"#!/bin/sh\n# mocked cache-span emitter\n"
_A = "alpha"
_B = "beta"
_NO_LAN = "delta"
_OPTIONAL_HOST_KEYS = {"WORKER_LAN_ADDRESS"}
_REQUIRED_HOST_KEYS = {
    "WORKER_HOST_OS",
    "WORKER_VM_CPUS",
    "WORKER_VM_MEMORY_GIB",
    "WORKER_VM_DISK_GIB",
    "WORKER_DATA_DISK_GIB",
}

_STUB_LIMACTL = """#!/bin/bash
set -eu
printf 'limactl %s\\n' "$*" >> "$STUB_LOG"
state="$STUB_STATE"
case "${1:-}" in
  --version) cat "$state/lima-version"; exit 0 ;;
  sudoers) exit "$(cat "$state/sudoers-exit" 2>/dev/null || echo 0)" ;;
  list)
    shift
    fmt=""
    name=""
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --format) fmt="$2"; shift 2 ;;
        --json) fmt=json; shift ;;
        *) name="$1"; shift ;;
      esac
    done
    for f in "$state"/instances/*; do
      [ -e "$f" ] || continue
      n="${f##*/}"
      if [ -n "$name" ] && [ "$n" != "$name" ]; then continue; fi
      case "$n" in *.json) continue ;; esac
      if [ "$fmt" = "{{.Name}}" ]; then echo "$n"
      elif [ "$fmt" = json ]; then cat "$f.json"
      else cat "$f"; fi
    done
    exit 0 ;;
  create)
    for a in "$@"; do case "$a" in --name=*) n="${a#--name=}" ;; esac; done
    echo "Stopped 0 0 0" > "$state/instances/$n"
    echo '{"config":{"networks":[{"lima":"bridged"}]}}' > "$state/instances/$n.json"
    exit 0 ;;
  start) exit 0 ;;
  disk)
    case "${2:-}" in
      list) for d in "$state"/disks/*; do [ -e "$d" ] && printf '{"name":"%s"}\n' "${d##*/}"; done; exit 0 ;;
      create) touch "$state/disks/$3"; exit 0 ;;
    esac ;;
  shell)
    # The VM's filesystem is modelled under $state/vm.
    case "$*" in
      *" sha256sum "*)
        for p in "$@"; do :; done
        [ -f "$state/vm$p" ] || exit 1
        { sha256sum "$state/vm$p" 2>/dev/null || shasum -a 256 "$state/vm$p"; }
        exit 0 ;;
      *" install -D -m "*" /dev/stdin "*)
        for dest in "$@"; do :; done
        mkdir -p "$(dirname "$state/vm$dest")"
        cat > "$state/vm$dest"
        [ -f "$state/corrupt-delivery" ] && echo corrupted >> "$state/vm$dest"
        exit 0 ;;
      *" mv "*)
        src=""; dst=""
        for a in "$@"; do src="$dst"; dst="$a"; done
        mv "$state/vm$src" "$state/vm$dst"
        exit 0 ;;
      *" apparmor_parser "*) exit "$(cat "$state/apparmor-exit" 2>/dev/null || echo 0)" ;;
      *" mkdir "*) exit 0 ;;
      *" install -m 0600 /dev/stdin "*)
        for dest in "$@"; do :; done
        cat > "$state/delivered-${dest##*/}"
        exit 0 ;;
    esac
    cat > "$state/shell-stdin"
    if grep -q '^# converge-lan-address' "$state/shell-stdin"; then
      mv "$state/shell-stdin" "$state/lan-stdin"
      exit "$(cat "$state/lan-exit" 2>/dev/null || echo 0)"
    fi
    if grep -q '^# converge-worker-container' "$state/shell-stdin"; then
      mv "$state/shell-stdin" "$state/converge-stdin"
      echo "converge-worker-container: worker converged"
      exit 0
    fi
    mv "$state/shell-stdin" "$state/probe-stdin"
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
    hosts = state / "hosts"
    hosts.mkdir()
    for name, v in _HOSTS.items():
        (hosts / f"{name}.env").write_text(
            "WORKER_HOST_OS=Darwin\n"
            f"WORKER_VM_CPUS={v['cpus']}\n"
            f"WORKER_VM_MEMORY_GIB={v['memory_gib']}\n"
            f"WORKER_VM_DISK_GIB={v['disk_gib']}\n"
            f"WORKER_DATA_DISK_GIB={v['data_gib']}\n"
            + (f"WORKER_LAN_ADDRESS={v['lan']}\n" if "lan" in v else ""),
            encoding="utf-8",
        )
    _write_exec(path=bin_dir / "socket_vmnet", text="#!/bin/bash\nexit 0\n")
    bundle = state / "hook-bundle" / _HOOK_VERSION
    bundle.mkdir(parents=True)
    (bundle / "index.js").write_bytes(_HOOK_BYTES)
    (bundle / "index.js.sha256").write_text(
        f"{hashlib.sha256(_HOOK_BYTES).hexdigest()}  index.js\n", encoding="utf-8"
    )
    (state / "workflow-profile").write_text("# mocked workflow profile\n", encoding="utf-8")
    (state / "cache-span").write_bytes(_SPAN_BYTES)
    repo = state / "collector-repo" / _COLLECTOR_COMMIT
    repo.mkdir(parents=True)
    (repo / _COLLECTOR_FILE).write_bytes(_COLLECTOR_BYTES)
    (state / "collector.ref").write_text(
        "# mocked pin\n"
        f"commit={_COLLECTOR_COMMIT}\n"
        f"file={_COLLECTOR_FILE}\n"
        f"sha256={hashlib.sha256(_COLLECTOR_BYTES).hexdigest()}\n",
        encoding="utf-8",
    )
    return _Host(bin_dir=bin_dir, state=state, log=log)


def _install_lima(*, host: _Host, version: str) -> None:
    _write_exec(path=host.bin_dir / "limactl", text=_STUB_LIMACTL)
    (host.state / "lima-version").write_text(f"limactl version {version}\n", encoding="utf-8")


def _add_instance(
    *,
    host: _Host,
    name: str,
    status: str,
    cpus: int,
    memory_gib: int,
    disk_gib: int,
    bridged: bool = True,
) -> None:
    (host.state / "instances" / name).write_text(
        f"{status} {cpus} {memory_gib * _GIB} {disk_gib * _GIB}\n", encoding="utf-8"
    )
    networks = '[{"lima":"bridged"}]' if bridged else "[]"
    (host.state / "instances" / f"{name}.json").write_text(
        f'{{"config":{{"networks":{networks}}}}}\n', encoding="utf-8"
    )


def _run(
    *, host: _Host, args: list[str], extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    env = {
        "PATH": f"{host.bin_dir}:/usr/bin:/bin",
        "HOME": str(host.state),
        "STUB_LOG": str(host.log),
        "STUB_STATE": str(host.state),
        "STUB_BIN": str(host.bin_dir),
        "HOMELAB_WORKER_HOSTS_DIR": str(host.state / "hosts"),
        "HOMELAB_WORKER_SOCKET_VMNET": str(host.bin_dir / "socket_vmnet"),
        "HOMELAB_WORKER_HOOK_BUNDLE_DIR": str(host.state / "hook-bundle"),
        "HOMELAB_WORKER_APPARMOR_PROFILE": str(host.state / "workflow-profile"),
        "HOMELAB_WORKER_CACHE_SPAN": str(host.state / "cache-span"),
        "HOMELAB_WORKER_COLLECTOR_REF": str(host.state / "collector.ref"),
        "HOMELAB_WORKER_COLLECTOR_BASE_URL": f"file://{host.state / 'collector-repo'}",
        **(extra_env or {}),
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
    assert _B in result.stderr
    assert _A in result.stderr
    assert _calls(host=host) == []


def test_absent_lima_is_installed_through_homebrew_and_the_named_vz_vm_is_created(
    host: _Host,
) -> None:
    result = _run(host=host, args=[_B])
    assert result.returncode == 0, result.stderr
    calls = _calls(host=host)
    assert "brew install lima" in calls
    creates = [c for c in calls if c.startswith("limactl create ")]
    assert len(creates) == 1
    assert f"--name={_B}-homelab-worker" in creates[0]
    assert "--vm-type=vz" in creates[0]
    assert f"--cpus={_HOSTS[_B]['cpus']}" in creates[0]
    assert f"limactl start --tty=false {_B}-homelab-worker" in calls


def test_installed_lima_at_or_above_the_minimum_is_reused_without_install_or_upgrade(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    assert [c for c in _calls(host=host) if c.startswith("brew ")] == []
    assert "reusing Lima 2.2.1" in result.stdout


def test_installed_lima_older_than_the_minimum_is_refused_by_version(host: _Host) -> None:
    _install_lima(host=host, version="1.2.0")
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "1.2.0" in result.stderr
    # The refusal names whatever minimum the task declares, not a restated value.
    minimum = (_WORKER_DIR / "lima" / "min-version").read_text(encoding="utf-8").strip()
    assert minimum in result.stderr
    calls = _calls(host=host)
    assert [c for c in calls if c.startswith("brew ")] == []
    assert [c for c in calls if c.startswith("limactl create")] == []


def test_rerun_starts_the_existing_vm_in_place_and_never_recreates_it(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    _add_instance(
        host=host,
        name=f"{_A}-homelab-worker",
        status="Stopped",
        cpus=_HOSTS[_A]["cpus"],
        memory_gib=_HOSTS[_A]["memory_gib"],
        disk_gib=_HOSTS[_A]["disk_gib"],
    )
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    calls = _calls(host=host)
    assert f"limactl start --tty=false {_A}-homelab-worker" in calls
    assert [c for c in calls if c.split()[1] in {"create", "delete", "stop", "factory-reset"}] == []


def test_rerun_keeps_a_running_vm_without_starting_or_recreating_it(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    _add_instance(
        host=host,
        name=f"{_A}-homelab-worker",
        status="Running",
        cpus=_HOSTS[_A]["cpus"],
        memory_gib=_HOSTS[_A]["memory_gib"],
        disk_gib=_HOSTS[_A]["disk_gib"],
    )
    result = _run(host=host, args=[_A])
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
        name=f"{_B}-homelab-worker",
        status="Running",
        cpus=_HOSTS[_B]["cpus"],
        memory_gib=_HOSTS[_B]["memory_gib"],
        disk_gib=_HOSTS[_B]["disk_gib"],
    )
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert f"{_B}-homelab-worker" in result.stderr
    assert [c for c in _calls(host=host) if c.startswith("limactl create")] == []


def test_a_vm_whose_declared_setting_changed_is_refused_naming_the_setting(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    _add_instance(
        host=host,
        name=f"{_A}-homelab-worker",
        status="Stopped",
        cpus=_HOSTS[_A]["cpus"] + 1,
        memory_gib=_HOSTS[_A]["memory_gib"],
        disk_gib=_HOSTS[_A]["disk_gib"],
    )
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "WORKER_VM_CPUS" in result.stderr
    assert [c for c in _calls(host=host) if c.split()[1] in {"create", "delete", "start"}] == []


def test_a_host_declared_for_another_platform_is_refused(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.bin_dir / "uname").write_text("#!/bin/bash\necho Linux\n", encoding="utf-8")
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "Darwin" in result.stderr
    assert _calls(host=host) == []


def test_every_committed_host_declaration_is_data_for_the_same_code_path() -> None:
    hosts = sorted(p.stem for p in (_WORKER_DIR / "hosts").glob("*.env"))
    assert hosts
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
        assert _REQUIRED_HOST_KEYS <= keys <= _REQUIRED_HOST_KEYS | _OPTIONAL_HOST_KEYS


def test_the_vm_is_registered_to_start_at_login_so_the_worker_rejoins_after_a_reboot(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    calls = _calls(host=host)
    registered = calls.index(f"limactl autostart enable --tty=false {_A}-homelab-worker")
    started = max(i for i, c in enumerate(calls) if c.startswith("limactl start "))
    assert registered > started


def test_a_rerun_on_a_running_vm_still_registers_it_to_start_at_login(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    v = _HOSTS[_A]
    _add_instance(
        host=host,
        name=f"{_A}-homelab-worker",
        status="Running",
        cpus=int(v["cpus"]),
        memory_gib=int(v["memory_gib"]),
        disk_gib=int(v["disk_gib"]),
    )
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    assert f"limactl autostart enable --tty=false {_A}-homelab-worker" in _calls(host=host)


def test_a_new_vm_gets_an_xfs_data_disk_created_once(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    calls = _calls(host=host)
    assert [c for c in calls if c.startswith("limactl disk create ")] == [
        f"limactl disk create hwdata --size={_HOSTS[_A]['data_gib']}GiB --format=raw"
    ]
    create = next(c for c in calls if c.startswith("limactl create "))
    assert '"name":"hwdata"' in create
    assert '"fsType":"xfs"' in create
    assert (
        f"limactl shell --workdir / {_A}-homelab-worker sudo bash -s -- /mnt/lima-hwdata" in calls
    )


def test_the_data_disk_filesystem_label_fits_the_xfs_limit() -> None:
    # Lima formats an additional disk with `mkfs.<fs> -L lima-<disk name>` (v2.2.1
    # boot.Linux/05-lima-disks.sh), and an XFS label holds at most 12 characters. A longer
    # name leaves the disk unformatted and unmounted, measured on a real host 2026-11-04.
    script = _SCRIPT.read_text(encoding="utf-8")
    [declared] = [line for line in script.splitlines() if line.startswith("data_disk=")]
    match = re.fullmatch(r'data_disk="([a-z0-9-]+)"', declared)
    assert match, declared
    assert len(f"lima-{match.group(1)}") <= 12


def test_a_missing_vm_capability_stops_the_task_naming_it_with_its_remedy(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / "probe-output").write_text(
        "PRESENT tun\nMISSING apparmor: boot the VM kernel with apparmor=1\n", encoding="utf-8"
    )
    (host.state / "probe-exit").write_text("1\n", encoding="utf-8")
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "MISSING apparmor: boot the VM kernel with apparmor=1" in result.stderr
    assert "worker container was not started" in result.stderr
    assert (host.state / "probe-stdin").read_text(encoding="utf-8") == (
        _WORKER_DIR / "probe-vm-capabilities.sh"
    ).read_text(encoding="utf-8")


def test_a_passing_probe_is_recorded_beside_the_worker_state(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    report = host.state / ".local" / "state" / "livespec-homelab-worker" / f"{_A}-homelab-worker"
    assert (report / "vm-capabilities.txt").read_text(encoding="utf-8") == "PRESENT apparmor\n"


def test_after_a_passing_probe_the_worker_container_converges_from_the_pinned_image(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    [image] = [
        line
        for line in (_WORKER_DIR / "image" / "ref").read_text(encoding="utf-8").splitlines()
        if not line.startswith("#")
    ]
    assert re.fullmatch(r"\S+@sha256:[0-9a-f]{64}", image)
    shells = [c for c in _calls(host=host) if c.startswith("limactl shell ")]
    assert shells[-1] == (
        f"limactl shell --workdir / {_A}-homelab-worker sudo bash -s -- "
        f"{_A}-homelab-worker {_A} {image} /mnt/lima-hwdata/worker "
        f"host:{_HOSTS[_A]['lan'].split('/')[0]}"
    )
    assert (host.state / "converge-stdin").read_text(encoding="utf-8") == (
        _WORKER_DIR / "vm" / "converge-worker-container.sh"
    ).read_text(encoding="utf-8")
    assert "worker converged" in result.stdout


def test_a_failed_probe_never_converges_the_worker_container(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / "probe-output").write_text("MISSING tun: load the tun module\n", encoding="utf-8")
    (host.state / "probe-exit").write_text("1\n", encoding="utf-8")
    assert _run(host=host, args=[_A]).returncode != 0
    assert not (host.state / "converge-stdin").exists()


def _enrollment(*, host: _Host, files: tuple[str, ...]) -> Path:
    enrollment = host.state / "minted"
    enrollment.mkdir()
    for name in files:
        (enrollment / name).write_text(f"secret-{name}\n", encoding="utf-8")
    return enrollment


def test_a_minted_enrollment_reaches_the_vm_only_on_stdin_before_the_container_step(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    enrollment = _enrollment(host=host, files=("bootstrap-kubeconfig", "client-ca.crt"))
    result = _run(host=host, args=[_A], extra_env={"HOMELAB_WORKER_ENROLLMENT": str(enrollment)})
    assert result.returncode == 0, result.stderr
    for name in ("bootstrap-kubeconfig", "client-ca.crt"):
        assert (host.state / f"delivered-{name}").read_text(encoding="utf-8") == (
            f"secret-{name}\n"
        )
    shells = [c for c in _calls(host=host) if c.startswith("limactl shell ")]
    installs = [i for i, c in enumerate(shells) if " install -m 0600 /dev/stdin " in c]
    converge = next(
        i
        for i, c in enumerate(shells)
        if "/mnt/lima-hwdata/worker" in c and f" -- {_A}-homelab-worker " in c
    )
    assert installs
    assert max(installs) < converge
    assert all(
        c.endswith(f"/mnt/lima-hwdata/worker/enrollment/{n}")
        for c, n in zip(
            (shells[i] for i in installs), ("bootstrap-kubeconfig", "client-ca.crt"), strict=True
        )
    )
    log = host.log.read_text(encoding="utf-8")
    assert "secret-" not in log
    assert "secret-" not in result.stdout + result.stderr


def test_an_incomplete_enrollment_is_refused_before_any_host_change(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    enrollment = _enrollment(host=host, files=("bootstrap-kubeconfig",))
    result = _run(host=host, args=[_A], extra_env={"HOMELAB_WORKER_ENROLLMENT": str(enrollment)})
    assert result.returncode != 0
    assert "client-ca.crt" in result.stderr
    assert _calls(host=host) == []


def test_a_host_declaring_no_lan_address_is_refused_before_any_vm_call(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_NO_LAN])
    assert result.returncode != 0
    assert "WORKER_LAN_ADDRESS" in result.stderr
    assert [c for c in _calls(host=host) if c.split()[1] in {"create", "start", "shell"}] == []


def test_a_missing_socket_vmnet_stops_the_task_before_the_vm_starts(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(
        host=host,
        args=[_A],
        extra_env={"HOMELAB_WORKER_SOCKET_VMNET": str(host.state / "absent")},
    )
    assert result.returncode != 0
    assert "socket_vmnet" in result.stderr
    calls = _calls(host=host)
    assert [c for c in calls if c.split()[1] in {"create", "start", "shell"}] == []
    assert [c for c in calls if c.startswith("brew ")] == []


def test_a_failing_sudoers_check_stops_the_task_before_the_vm_starts(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / "sudoers-exit").write_text("1\n", encoding="utf-8")
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "limactl sudoers" in result.stderr
    assert [c for c in _calls(host=host) if c.split()[1] in {"create", "start", "shell"}] == []


def test_the_vm_template_declares_a_bridged_network() -> None:
    template = yaml.safe_load((_WORKER_DIR / "lima" / "worker.yaml").read_text(encoding="utf-8"))
    assert {"lima": "bridged"} in template["networks"]


def test_an_existing_vm_without_the_bridged_network_is_refused_naming_it(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    _add_instance(
        host=host,
        name=f"{_A}-homelab-worker",
        status="Stopped",
        cpus=_HOSTS[_A]["cpus"],
        memory_gib=_HOSTS[_A]["memory_gib"],
        disk_gib=_HOSTS[_A]["disk_gib"],
        bridged=False,
    )
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "bridged" in result.stderr
    assert [c for c in _calls(host=host) if c.split()[1] in {"create", "delete", "start"}] == []


def test_the_declared_lan_address_is_set_on_the_bridged_interface_before_converging(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    shells = [c for c in _calls(host=host) if c.startswith("limactl shell ")]
    lan = f"limactl shell --workdir / {_A}-homelab-worker sudo bash -s -- lima0 {_HOSTS[_A]['lan']}"
    assert lan in shells
    assert shells.index(lan) < len(shells) - 1
    assert (host.state / "lan-stdin").read_text(encoding="utf-8") == (
        _WORKER_DIR / "vm" / "converge-lan-address.sh"
    ).read_text(encoding="utf-8")


def test_a_failed_lan_address_step_never_converges_the_worker_container(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / "lan-exit").write_text("1\n", encoding="utf-8")
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert not (host.state / "converge-stdin").exists()


_HOOK_DEST = f"/mnt/lima-hwdata/worker/ci/hooks/{_HOOK_VERSION}/index.js"


def _shells(*, host: _Host) -> list[str]:
    return [c for c in _calls(host=host) if c.startswith("limactl shell ")]


def _converge_index(shells: list[str]) -> int:
    return next(
        i
        for i, c in enumerate(shells)
        if "/mnt/lima-hwdata/worker" in c and f" -- {_A}-homelab-worker " in c
    )


def test_the_container_hook_reaches_the_data_disk_verified_before_the_container_step(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    assert (host.state / f"vm{_HOOK_DEST}").read_bytes() == _HOOK_BYTES
    assert not (host.state / f"vm{_HOOK_DEST}.new").exists()
    shells = _shells(host=host)
    moved = next(
        i for i, c in enumerate(shells) if c.endswith(f" mv {_HOOK_DEST}.new {_HOOK_DEST}")
    )
    assert moved < _converge_index(shells)


def test_a_current_container_hook_is_not_delivered_again(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / f"vm{_HOOK_DEST}").parent.mkdir(parents=True)
    (host.state / f"vm{_HOOK_DEST}").write_bytes(_HOOK_BYTES)
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    assert [c for c in _shells(host=host) if " install -D " in c and "/ci/hooks/" in c] == []


def test_a_container_hook_not_matching_its_checksum_never_converges_the_worker(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / "corrupt-delivery").write_text("", encoding="utf-8")
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "index.js.sha256" in result.stderr
    assert not (host.state / f"vm{_HOOK_DEST}").exists()
    assert not (host.state / "converge-stdin").exists()


def test_a_hook_bundle_without_its_checksum_is_refused_before_any_host_change(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / "hook-bundle" / _HOOK_VERSION / "index.js.sha256").unlink()
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "index.js.sha256" in result.stderr
    assert [c for c in _calls(host=host) if c.startswith(("limactl create", "limactl start"))] == []


_SPAN_DEST = "/mnt/lima-hwdata/worker/ci/bin/ci-cache-span"


def test_the_cache_span_emitter_reaches_the_pool_bin_verified_before_the_container_step(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    assert (host.state / f"vm{_SPAN_DEST}").read_bytes() == _SPAN_BYTES
    shells = _shells(host=host)
    assert any(f" install -D -m 0755 /dev/stdin {_SPAN_DEST}.new" in c for c in shells)
    moved = next(
        i for i, c in enumerate(shells) if c.endswith(f" mv {_SPAN_DEST}.new {_SPAN_DEST}")
    )
    assert moved < _converge_index(shells)


def test_a_current_cache_span_emitter_is_not_delivered_again(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / f"vm{_SPAN_DEST}").parent.mkdir(parents=True)
    (host.state / f"vm{_SPAN_DEST}").write_bytes(_SPAN_BYTES)
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    assert [c for c in _shells(host=host) if f"{_SPAN_DEST}.new" in c] == []


def test_a_missing_cache_span_emitter_is_refused_before_any_host_change(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / "cache-span").unlink()
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "cache-span emitter" in result.stderr
    assert [c for c in _calls(host=host) if c.startswith(("limactl create", "limactl start"))] == []


def test_the_workflow_apparmor_profile_is_loaded_in_the_vm_before_the_container_step(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    # The stub models the VM's filesystem under state/vm.
    installed = host.state / "vm" / "etc" / "apparmor.d" / "workflow-profile"
    assert installed.read_text(encoding="utf-8") == "# mocked workflow profile\n"
    shells = _shells(host=host)
    loaded = next(
        i
        for i, c in enumerate(shells)
        if c.endswith(" apparmor_parser -r " + "/etc/apparmor.d/workflow-profile")
    )
    assert loaded < _converge_index(shells)


def test_a_profile_apparmor_refuses_never_converges_the_worker(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    (host.state / "apparmor-exit").write_text("1\n", encoding="utf-8")
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "AppArmor refused" in result.stderr
    assert not (host.state / "converge-stdin").exists()


def test_the_start_task_never_touches_the_hosts_own_tailnet(host: _Host) -> None:
    # The worker joins the tailnet from inside its own network namespace (converge); the host's
    # own Tailscale identity, login and settings are never touched by the start task.
    _install_lima(host=host, version="2.2.1")
    _write_exec(
        path=host.bin_dir / "tailscale",
        text='#!/bin/bash\nprintf "tailscale %s\\n" "$*" >> "$STUB_LOG"\n',
    )
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    assert [c for c in _calls(host=host) if c.startswith("tailscale ")] == []


def _vm_telemetry(*, host: _Host, name: str) -> Path:
    # The stub models the VM's filesystem under state/vm.
    return host.state / "vm" / "mnt" / "lima-hwdata" / "worker" / "telemetry" / name


def test_the_pinned_collector_configuration_reaches_the_vm_verified_before_the_container_step(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    assert _vm_telemetry(host=host, name="config.yaml").read_bytes() == _COLLECTOR_BYTES
    shells = _shells(host=host)
    moved = next(i for i, c in enumerate(shells) if c.endswith("/telemetry/config.yaml"))
    assert moved < _converge_index(shells)


def test_a_collector_configuration_not_matching_its_pin_never_converges_the_worker(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    repo = host.state / "collector-repo" / _COLLECTOR_COMMIT
    (repo / _COLLECTOR_FILE).write_bytes(b"# tampered\n")
    result = _run(host=host, args=[_A])
    assert result.returncode != 0
    assert "collector" in result.stderr
    assert not _vm_telemetry(host=host, name="config.yaml").exists()
    assert not (host.state / "converge-stdin").exists()


def test_the_ingest_key_reaches_the_vm_only_on_stdin(host: _Host) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A], extra_env={"HONEYCOMB_INGEST_KEY_LIVESPEC": _INGEST_KEY})
    assert result.returncode == 0, result.stderr
    env = _vm_telemetry(host=host, name=".env").read_text(encoding="utf-8")
    assert env == f"HONEYCOMB_INGEST_KEY_LIVESPEC={_INGEST_KEY}\n"
    assert _INGEST_KEY not in host.log.read_text(encoding="utf-8")
    assert _INGEST_KEY not in result.stdout + result.stderr


def test_without_an_ingest_key_the_worker_still_converges_with_its_collector_off(
    host: _Host,
) -> None:
    _install_lima(host=host, version="2.2.1")
    result = _run(host=host, args=[_A])
    assert result.returncode == 0, result.stderr
    assert not _vm_telemetry(host=host, name=".env").exists()
    assert "HONEYCOMB_INGEST_KEY_LIVESPEC" in result.stdout
    assert (host.state / "converge-stdin").exists()
