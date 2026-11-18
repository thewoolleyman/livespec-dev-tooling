"""The control-node role is bound to one machine in one place, and guarded.

WHY (work-item livespec-dev-tooling-voazyv slice S3, shared with ctete5's converge
trigger; legacy-coordinator-agent ruling 2026-11-18, on the maintainer's VPS
migration ruling that the VPS keeps only overseerd and caam-anthropic-loop-runner).
Roles that belong on the control node, the machine `ansible-apply` runs from and
that runs the coordinators, must not name a machine, or a move of the role would be
a hunt through plays. `ansible/inventory/legacy.yml` therefore declares ONE group,
`control_node_role`, holding exactly one alias entry whose local connection is
valid only where the controller's machine-id equals the entry's
`control_node_machine_id`.

WHAT IS HELD.
1. The group holds exactly one host, and that host declares a machine-id.
2. Every play that selects the role selects the GROUP, and no play names the alias.
3. A play selecting the group on another controller refuses before any task and
   names both machine-ids; on the control node it runs over the local connection.

HOW. By running the committed inventory with the `ansible-core` pin that `just
ansible-apply` executes. A scratch play runs a debug task only, so no host is
changed. The controller's identity is supplied through
`control_node_identity_file`, so the test is deterministic on every machine.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_INVENTORY = _REPO_ROOT / "ansible" / "inventory" / "legacy.yml"
_ANSIBLE_DIR = _REPO_ROOT / "ansible"
_GROUP = "control_node_role"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_MACHINE_ID = re.compile(r"^[0-9a-f]{32}$")
_FOREIGN_MACHINE_ID = "0123456789abcdef0123456789abcdef"
_REACHED = "CONTROL-NODE-ROLE-GUARD-REACHED"
_TIMEOUT_SECONDS = 600


def _ansible_core_pin() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, f"{_JUSTFILE} must carry an `ansible-apply *args:` recipe"
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, "the `ansible-apply` recipe must pin ansible-core exactly"
    return pin[0]


def _group_hosts() -> dict[str, dict[str, object]]:
    inventory = yaml.safe_load(_INVENTORY.read_text(encoding="utf-8"))
    group = inventory["all"]["children"][_GROUP]
    hosts = group["hosts"]
    assert isinstance(hosts, dict), f"{_GROUP} must declare hosts"
    return hosts


def _control_node_machine_id() -> str:
    ((_, entry),) = _group_hosts().items()
    machine_id = entry.get("control_node_machine_id")
    assert isinstance(machine_id, str), (
        f"the {_GROUP} entry must declare control_node_machine_id, the machine-id its "
        "local connection is valid for"
    )
    assert _MACHINE_ID.match(machine_id), machine_id
    return machine_id


def test_the_control_node_role_group_holds_exactly_one_host_with_a_machine_id() -> None:
    hosts = _group_hosts()
    assert len(hosts) == 1, f"{_GROUP} must hold exactly one host, found {sorted(hosts)}"
    assert _MACHINE_ID.match(_control_node_machine_id())


def test_every_play_that_selects_the_role_selects_the_group_and_no_play_names_the_alias() -> None:
    (alias,) = _group_hosts()
    selecting = 0
    for play_file in sorted(_ANSIBLE_DIR.glob("*.yml")):
        plays = yaml.safe_load(play_file.read_text(encoding="utf-8"))
        if not isinstance(plays, list):
            continue
        for play in plays:
            if not isinstance(play, dict) or "hosts" not in play:
                continue
            hosts = str(play["hosts"])
            assert alias not in hosts.split(":"), (
                f"{play_file.name} names the control-node alias {alias!r}; select the "
                f"{_GROUP} group instead"
            )
            if _GROUP in hosts:
                selecting += 1
                assert hosts.strip() == _GROUP, (
                    f"{play_file.name} selects {hosts!r}; a control-node-role play selects "
                    f"exactly the {_GROUP} group"
                )
    assert selecting >= 1, f"at least one play must select {_GROUP}"


def _run_play(*, tmp_path: Path, controller_machine_id: str) -> tuple[int, str]:
    identity = tmp_path / "machine-id"
    identity.write_text(f"{controller_machine_id}\n", encoding="utf-8")
    play = tmp_path / "play.yml"
    play.write_text(
        f"---\n- name: control-node role guard fixture\n  hosts: {_GROUP}\n"
        "  gather_facts: false\n"
        "  tasks:\n    - name: report the resolved connection\n"
        "      ansible.builtin.debug:\n"
        f'        msg: "{_REACHED} {{{{ ansible_connection }}}}"\n',
        encoding="utf-8",
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    } | {"ANSIBLE_NOCOWS": "1", "ANSIBLE_RETRY_FILES_ENABLED": "False"}
    result = subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(_INVENTORY),
            "--limit",
            _GROUP,
            "-e",
            f"control_node_identity_file={identity}",
            str(play),
        ],
        cwd=_REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    return result.returncode, result.stdout + result.stderr


def test_a_play_selecting_the_role_on_another_controller_refuses_before_any_task(
    *, tmp_path: Path
) -> None:
    expected = _control_node_machine_id()
    returncode, output = _run_play(tmp_path=tmp_path, controller_machine_id=_FOREIGN_MACHINE_ID)
    assert returncode != 0, output
    assert _REACHED not in output, output
    assert expected in output, output
    assert _FOREIGN_MACHINE_ID in output, output


def test_a_play_selecting_the_role_on_the_control_node_runs_over_the_local_connection(
    *, tmp_path: Path
) -> None:
    returncode, output = _run_play(
        tmp_path=tmp_path, controller_machine_id=_control_node_machine_id()
    )
    assert returncode == 0, output
    assert f"{_REACHED} local" in output, output
