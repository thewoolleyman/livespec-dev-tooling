"""The VM capability probe of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

`homelab-worker/probe-vm-capabilities.sh` runs inside a worker's Linux VM before the worker
container starts. These run it under the system `/bin/bash` against a fixture kernel-interface
tree (`PROBE_ROOT`) and stub `uname`, `findmnt`, `docker`, `mount`, `umount` and `cp`
executables, so each capability can be made present or absent on its own. The probe must name
every missing capability with a remedy, exit non-zero when any is missing, and never change the
VM to make itself pass.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROBE = _REPO_ROOT / "homelab-worker" / "probe-vm-capabilities.sh"
_CAPABILITIES = (
    "apparmor",
    "userns-idmap",
    "tun",
    "br-netfilter",
    "cgroup-v2",
    "mount-propagation",
    "nested-containerd",
    "reflink-storage",
)
_DATA_MOUNT = "/mnt/lima-test-homelab-worker-data"


@dataclass(frozen=True, kw_only=True)
class _Vm:
    root: Path
    bin_dir: Path
    log: Path


def _write(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_exec(*, path: Path, text: str) -> None:
    _write(path=path, text=text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _stub(*, vm: _Vm, name: str, body: str) -> None:
    _write_exec(
        path=vm.bin_dir / name,
        text=f'#!/bin/bash\nprintf "{name} %s\\n" "$*" >> "{vm.log}"\n{body}\n',
    )


@pytest.fixture
def vm(tmp_path: Path) -> _Vm:
    root = tmp_path / "root"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    log.write_text("", encoding="utf-8")
    made = _Vm(root=root, bin_dir=bin_dir, log=log)
    _write(path=root / "sys/module/apparmor/parameters/enabled", text="Y\n")
    _write(path=root / "sys/kernel/security/apparmor/profiles", text="")
    _write(path=root / "proc/sys/user/max_user_namespaces", text="63413\n")
    _write(path=root / "dev/net/tun", text="")
    _write(
        path=root / "sys/fs/cgroup/cgroup.controllers",
        text="cpuset cpu io memory hugetlb pids rdma misc\n",
    )
    _write(path=root / "sys/fs/cgroup/cgroup.subtree_control", text="cpuset cpu io memory pids\n")
    (root / _DATA_MOUNT.lstrip("/")).mkdir(parents=True)
    _stub(vm=made, name="uname", body='echo "6.8.0-88-generic"')
    _stub(vm=made, name="modinfo", body='[ "$1" = br_netfilter ] && echo "filename: stub"')
    _stub(vm=made, name="findmnt", body="echo shared")
    _stub(vm=made, name="docker", body="exit 0")
    _stub(vm=made, name="mount", body="exit 0")
    _stub(vm=made, name="umount", body="exit 0")
    _stub(vm=made, name="cp", body='[ "$1" = "--reflink=always" ] && /bin/cp "$2" "$3"')
    return made


def _run(*, vm: _Vm, tun_is_char_device: bool = True) -> subprocess.CompletedProcess[str]:
    # A regular file stands in for /dev/net/tun; the probe tests `-c`, so the fixture redirects that
    # one test by pointing the probe at the real /dev/null character device when TUN is present.
    if tun_is_char_device:
        (vm.root / "dev/net/tun").unlink()
        (vm.root / "dev/net/tun").symlink_to("/dev/null")
    return subprocess.run(
        ["/bin/bash", str(_PROBE), _DATA_MOUNT],
        capture_output=True,
        text=True,
        env={"PATH": f"{vm.bin_dir}:/usr/bin:/bin", "PROBE_ROOT": str(vm.root)},
        check=False,
        timeout=60,
    )


def _lines(*, result: subprocess.CompletedProcess[str]) -> list[str]:
    return result.stdout.splitlines()


def test_a_vm_with_every_capability_reports_each_present_and_exits_zero(vm: _Vm) -> None:
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _lines(result=result) == [f"PRESENT {c}" for c in _CAPABILITIES]


def test_apparmor_not_enforcing_is_named_missing_with_a_remedy(vm: _Vm) -> None:
    _write(path=vm.root / "sys/module/apparmor/parameters/enabled", text="N\n")
    result = _run(vm=vm)
    assert result.returncode != 0
    missing = [line for line in _lines(result=result) if line.startswith("MISSING ")]
    assert len(missing) == 1
    assert missing[0].startswith("MISSING apparmor: ")
    assert "apparmor=1" in missing[0]


def test_a_kernel_older_than_6_3_is_named_missing_for_user_namespaces(vm: _Vm) -> None:
    _stub(vm=vm, name="uname", body='echo "6.1.0-25-generic"')
    result = _run(vm=vm)
    assert result.returncode != 0
    assert any(
        line.startswith("MISSING userns-idmap: ") and "6.1.0-25-generic" in line
        for line in _lines(result=result)
    )


def test_an_absent_tun_device_is_named_missing(vm: _Vm) -> None:
    (vm.root / "dev/net/tun").unlink()
    result = _run(vm=vm, tun_is_char_device=False)
    assert result.returncode != 0
    assert any(line.startswith("MISSING tun: ") for line in _lines(result=result))


def test_an_undelegated_cgroup_controller_is_named_missing(vm: _Vm) -> None:
    _write(path=vm.root / "sys/fs/cgroup/cgroup.subtree_control", text="cpuset cpu io pids\n")
    result = _run(vm=vm)
    assert result.returncode != 0
    assert any(
        line.startswith("MISSING cgroup-v2: ") and "memory(not-delegated)" in line
        for line in _lines(result=result)
    )


def test_a_private_root_mount_is_named_missing_for_propagation(vm: _Vm) -> None:
    _stub(vm=vm, name="findmnt", body="echo private")
    result = _run(vm=vm)
    assert result.returncode != 0
    assert any(line.startswith("MISSING mount-propagation: ") for line in _lines(result=result))


def test_a_runtime_that_cannot_start_a_container_is_named_missing(vm: _Vm) -> None:
    _stub(vm=vm, name="docker", body="exit 125")
    result = _run(vm=vm)
    assert result.returncode != 0
    assert any(line.startswith("MISSING nested-containerd: ") for line in _lines(result=result))


def test_storage_without_reflink_is_named_missing(vm: _Vm) -> None:
    _stub(vm=vm, name="cp", body="exit 1")
    result = _run(vm=vm)
    assert result.returncode != 0
    assert any(
        line.startswith("MISSING reflink-storage: ") and _DATA_MOUNT in line
        for line in _lines(result=result)
    )


def test_the_probe_changes_nothing_to_make_itself_pass(vm: _Vm) -> None:
    _write(path=vm.root / "sys/module/apparmor/parameters/enabled", text="N\n")
    _run(vm=vm)
    calls = vm.log.read_text(encoding="utf-8").splitlines()
    commands = {line.split()[0] for line in calls}
    assert commands <= {"uname", "findmnt", "docker", "mount", "umount", "cp", "modinfo"}
    assert [c for c in calls if c.startswith("docker ") and " run " not in f" {c} "] == []
    assert (vm.root / "sys/module/apparmor/parameters/enabled").read_text(encoding="utf-8") == "N\n"


def test_a_kernel_that_cannot_load_br_netfilter_is_named_missing(vm: _Vm) -> None:
    _stub(vm=vm, name="modinfo", body="exit 1")
    result = _run(vm=vm)
    assert result.returncode != 0
    assert any(
        line.startswith("MISSING br-netfilter: ") and "br_netfilter" in line
        for line in _lines(result=result)
    )


def test_a_loaded_br_netfilter_is_present_even_without_modinfo(vm: _Vm) -> None:
    _stub(vm=vm, name="modinfo", body="exit 1")
    _write(path=vm.root / "proc/sys/net/bridge/bridge-nf-call-iptables", text="1\n")
    result = _run(vm=vm)
    assert "PRESENT br-netfilter" in _lines(result=result)
