"""The `vxlan_tunnel_tso` role turns tso off on the VXLAN interface only where the NIC is affected.

poweredge-xubuntu's bnx2x NIC emits malformed frames when it segments
VXLAN-encapsulated TCP in hardware (plan homelab-k8s-worker-nodes, epic
livespec-dev-tooling-ko26ez). The role works around it on the flannel interface.

THE ROLE IS RUN, NOT READ. Its contract is behaviour: which hosts it acts on,
what it writes, and what a drift report shows. So each test executes the role
with the `ansible-core` pin `just ansible-drift` uses, against a one-host local
inventory, a stand-in `ethtool` and `sudo`, and paths under `tmp_path`. Every
value the role reads (driver list, interface names, rule path) is a FIXTURE
value, so no test pins a committed configuration value.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLES_PATH = _REPO_ROOT / "ansible" / "roles"
_PLAY = _REPO_ROOT / "ansible" / "ci-pool.yml"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_TIMEOUT_SECONDS = 600
_HOST = "fixture-node"

# Fixture values: none of them is a value the role or the inventory commits.
_AFFECTED_DRIVER = "fakedrv"
_OTHER_DRIVER = "otherdrv"
_UPLINK = "upl0"
_TUNNEL = "tun9"

_SUDO_STAND_IN = """#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in
    -u) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
exec "$@"
"""

# The stand-in ethtool. It logs every invocation, reports the driver named in
# its state directory, and keeps the tunnel's tso state in a file so a set is
# visible to the next read. Anything it was not written to answer exits 64.
_ETHTOOL_STAND_IN = """#!/bin/sh
state="$(dirname "$0")/../state"
printf '%s\\n' "$*" >> "$state/argv.log"
case "$1" in
  -i) printf 'driver: %s\\nversion: 1\\n' "$(cat "$state/driver")"; exit 0 ;;
  -k) printf 'Features for %s:\\ntcp-segmentation-offload: %s\\n' "$2" "$(cat "$state/tso")"; exit 0 ;;
  -K) [ "$3" = tso ] || exit 64; printf '%s' "$4" > "$state/tso"; exit 0 ;;
esac
exit 64
"""


@dataclass(frozen=True, kw_only=True)
class _Scratch:
    root: Path
    bin_dir: Path
    state: Path
    rule: Path

    def argv_log(self) -> list[str]:
        log = self.state / "argv.log"
        return log.read_text(encoding="utf-8").splitlines() if log.exists() else []

    def sets(self) -> list[str]:
        return [line for line in self.argv_log() if line.startswith("-K ")]


@pytest.fixture
def scratch(*, tmp_path: Path) -> _Scratch:
    bin_dir = tmp_path / "bin"
    state = tmp_path / "state"
    bin_dir.mkdir()
    state.mkdir()
    for name, body in (("sudo", _SUDO_STAND_IN), ("ethtool", _ETHTOOL_STAND_IN)):
        stand_in = bin_dir / name
        stand_in.write_text(body, encoding="utf-8")
        stand_in.chmod(0o755)
    (state / "tso").write_text("on", encoding="utf-8")
    return _Scratch(root=tmp_path, bin_dir=bin_dir, state=state, rule=tmp_path / "70-fixture.rules")


def _ansible_core_pin() -> str:
    recipe = re.search(
        r"^ansible-drift \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None
    return pin[0]


def _run(
    *,
    scratch: _Scratch,
    driver: str,
    uplink: str = _UPLINK,
    ethtool: Path | None = None,
    check: bool = False,
) -> int:
    """Run the role once; return the host's `changed=` count from the PLAY RECAP."""
    (scratch.state / "driver").write_text(driver, encoding="utf-8")
    host_vars = {
        "vxlan_tunnel_tso_interface": _TUNNEL,
        "vxlan_tunnel_tso_affected_drivers": f"[{_AFFECTED_DRIVER}]",
        "vxlan_tunnel_tso_udev_rule": str(scratch.rule),
        "vxlan_tunnel_tso_ethtool": str(ethtool or scratch.bin_dir / "ethtool"),
        "vxlan_tunnel_tso_uplink": f'"{uplink}"',
    }
    declared = "".join(f"      {key}: {value}\n" for key, value in host_vars.items())
    inventory = scratch.root / "inventory.yml"
    inventory.write_text(
        f"all:\n  hosts:\n    {_HOST}:\n      ansible_connection: local\n{declared}",
        encoding="utf-8",
    )
    play = scratch.root / "play.yml"
    play.write_text(
        "- name: fixture\n  hosts: all\n  gather_facts: false\n"
        "  roles:\n    - role: vxlan_tunnel_tso\n",
        encoding="utf-8",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update(
        {
            "PATH": f"{scratch.bin_dir}{os.pathsep}{env['PATH']}",
            "ANSIBLE_ROLES_PATH": str(_ROLES_PATH),
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_INTERPRETER_PYTHON": "auto_silent",
        }
    )
    command = ["uvx", "--from", _ansible_core_pin(), "ansible-playbook"]
    if check:
        command += ["--check", "--diff"]
    completed = subprocess.run(
        [*command, "-i", str(inventory), str(play)],
        cwd=scratch.root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, f"the role must complete on every host:\n{output}"
    recap = re.search(rf"^{_HOST}\s+: .*?\bchanged=(?P<changed>\d+)\b", output, re.MULTILINE)
    assert recap is not None, output
    return int(recap["changed"])


def test_an_affected_node_gets_tso_off_and_a_rule_that_reapplies_it(*, scratch: _Scratch) -> None:
    changed = _run(scratch=scratch, driver=_AFFECTED_DRIVER)
    assert changed == 2
    assert (scratch.state / "tso").read_text(encoding="utf-8") == "off"
    # The only write names the tunnel interface, never the uplink.
    assert scratch.sets() == [f"-K {_TUNNEL} tso off"]
    rule = scratch.rule.read_text(encoding="utf-8")
    assert f'ACTION=="add", SUBSYSTEM=="net", KERNEL=="{_TUNNEL}"' in rule
    assert f'RUN+="{scratch.bin_dir / "ethtool"} -K {_TUNNEL} tso off"' in rule


def test_a_second_apply_on_an_affected_node_changes_nothing(*, scratch: _Scratch) -> None:
    _run(scratch=scratch, driver=_AFFECTED_DRIVER)
    assert _run(scratch=scratch, driver=_AFFECTED_DRIVER) == 0
    assert len(scratch.sets()) == 1


def test_an_unaffected_node_is_left_alone_and_loses_a_stale_rule(*, scratch: _Scratch) -> None:
    scratch.rule.write_text("stale\n", encoding="utf-8")
    assert _run(scratch=scratch, driver=_OTHER_DRIVER) == 1
    assert not scratch.rule.exists()
    assert scratch.sets() == []
    assert (scratch.state / "tso").read_text(encoding="utf-8") == "on"


def test_a_node_with_no_default_route_completes_and_only_removes_the_rule(
    *, scratch: _Scratch
) -> None:
    scratch.rule.write_text("stale\n", encoding="utf-8")
    assert _run(scratch=scratch, driver=_AFFECTED_DRIVER, uplink="") == 1
    assert not scratch.rule.exists()
    assert scratch.argv_log() == []


def test_a_node_with_no_ethtool_completes_and_only_removes_the_rule(*, scratch: _Scratch) -> None:
    scratch.rule.write_text("stale\n", encoding="utf-8")
    missing = scratch.root / "absent" / "ethtool"
    assert _run(scratch=scratch, driver=_AFFECTED_DRIVER, ethtool=missing) == 1
    assert not scratch.rule.exists()
    assert scratch.argv_log() == []


def test_a_drift_report_shows_the_pending_change_and_writes_nothing(*, scratch: _Scratch) -> None:
    changed = _run(scratch=scratch, driver=_AFFECTED_DRIVER, check=True)
    assert changed == 2
    assert scratch.sets() == []
    assert not scratch.rule.exists()
    assert (scratch.state / "tso").read_text(encoding="utf-8") == "on"


def test_ci_pool_reaches_the_role_ungated() -> None:
    entry = re.search(
        r"^    - role: vxlan_tunnel_tso\n      tags: \[vxlan_tunnel_tso\]\n(?P<next>.*)$",
        _PLAY.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert entry is not None
    assert not entry.group("next").startswith("      when:")
