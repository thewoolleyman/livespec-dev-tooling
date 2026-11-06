"""The home-LAN address step of `SPECIFICATION/non-functional-requirements.md`, "Homelab worker nodes".

`homelab-worker/vm/converge-lan-address.sh` sets a worker VM's declared static home-LAN address on
its bridged interface. These run it under the system `/bin/bash` against stub `ip` and `netplan`
executables and a temporary netplan file, and assert:

- a missing or changed netplan file is written and applied once, and the step waits for the
  address to appear, because `netplan apply` returns before networkd has set it;
- an unchanged netplan file is neither rewritten nor re-applied;
- an address that never appears within the wait is refused, naming it;
- an absent interface or an address without a prefix is refused before any change.

Every value here is the stub's own; none is a production value.
"""

from __future__ import annotations

import stat
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

_SCRIPT = Path(__file__).resolve().parents[2] / "homelab-worker" / "vm" / "converge-lan-address.sh"
_IFACE = "lan9"
_CIDR = "10.99.0.21/24"

# `ip link show dev <iface>` succeeds when the stub's link file exists. `ip -4 -o addr show dev`
# reports the address only once `netplan apply` has run and the stub's settle countdown is spent.
_STUB_IP = """#!/bin/bash
s="$STUB_STATE"
printf 'ip %s\\n' "$*" >> "$s/calls.log"
case "$*" in
  "link show dev "*) [ -f "$s/link" ] ;;
  "-4 -o addr show dev "*)
    [ -f "$s/applied" ] || exit 0
    n=$(cat "$s/settle" 2>/dev/null || echo 0)
    if [ "$n" -gt 0 ]; then echo $((n - 1)) > "$s/settle"; exit 0; fi
    printf '3: %s    inet %s brd 10.99.0.255 scope global %s\\n' "$6" "$STUB_CIDR" "$6" ;;
esac
"""

_STUB_NETPLAN = """#!/bin/bash
printf 'netplan %s\\n' "$*" >> "$STUB_STATE/calls.log"
touch "$STUB_STATE/applied"
"""


@dataclass(frozen=True, kw_only=True)
class _Vm:
    state: Path
    bin_dir: Path
    plan: Path


def _exe(*, path: Path, body: str) -> None:
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


@pytest.fixture
def vm(tmp_path: Path) -> _Vm:
    state = tmp_path / "stub"
    state.mkdir()
    (state / "link").write_text("", encoding="utf-8")
    (state / "calls.log").write_text("", encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _exe(path=bin_dir / "ip", body=_STUB_IP)
    _exe(path=bin_dir / "netplan", body=_STUB_NETPLAN)
    return _Vm(state=state, bin_dir=bin_dir, plan=tmp_path / "netplan" / "60-lan.yaml")


def _run(
    *, vm: _Vm, args: tuple[str, ...] = (_IFACE, _CIDR), wait: str = "5"
) -> subprocess.CompletedProcess[str]:
    vm.plan.parent.mkdir(exist_ok=True)
    return subprocess.run(
        ["/bin/bash", str(_SCRIPT), *args],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{vm.bin_dir}:/usr/bin:/bin",
            "STUB_STATE": str(vm.state),
            "STUB_CIDR": _CIDR,
            "NETPLAN_FILE": str(vm.plan),
            "ADDRESS_WAIT_SECONDS": wait,
            "POLL_SECONDS": "1",
        },
        check=False,
        timeout=60,
    )


def _netplan_calls(*, vm: _Vm) -> list[str]:
    lines = (vm.state / "calls.log").read_text(encoding="utf-8").splitlines()
    return [c for c in lines if c.startswith("netplan ")]


def test_a_new_address_is_written_applied_once_and_awaited(vm: _Vm) -> None:
    (vm.state / "settle").write_text("2\n", encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _netplan_calls(vm=vm) == ["netplan apply"]
    plan = vm.plan.read_text(encoding="utf-8")
    assert f"    {_IFACE}:\n" in plan
    assert "      dhcp4: false\n" in plan
    assert f"      addresses: [{_CIDR}]\n" in plan
    assert f"{_IFACE} carries {_CIDR}" in result.stdout


def test_an_unchanged_netplan_file_is_neither_rewritten_nor_reapplied(vm: _Vm) -> None:
    assert _run(vm=vm).returncode == 0
    before = vm.plan.stat().st_mtime_ns
    (vm.state / "calls.log").write_text("", encoding="utf-8")
    result = _run(vm=vm)
    assert result.returncode == 0, result.stdout + result.stderr
    assert _netplan_calls(vm=vm) == []
    assert vm.plan.stat().st_mtime_ns == before


def test_an_address_that_never_appears_is_refused_naming_it(vm: _Vm) -> None:
    (vm.state / "settle").write_text("100\n", encoding="utf-8")
    result = _run(vm=vm, wait="2")
    assert result.returncode != 0
    assert _CIDR in result.stderr
    assert _IFACE in result.stderr


@pytest.mark.parametrize(
    ("args", "message", "link"),
    [
        ((_IFACE, "10.99.0.21"), "has no /prefix", "present"),
        ((_IFACE, _CIDR), "is absent", "absent"),
    ],
)
def test_a_bad_address_or_absent_interface_is_refused_before_any_change(
    vm: _Vm, args: tuple[str, ...], message: str, link: str
) -> None:
    if link == "absent":
        (vm.state / "link").unlink()
    result = _run(vm=vm, args=args)
    assert result.returncode != 0
    assert message in result.stderr
    assert _netplan_calls(vm=vm) == []
    assert not vm.plan.exists()
