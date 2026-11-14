"""The `vps` inventory entry's local connection is valid only on the control node.

WHY (work-item livespec-dev-tooling-fy6ip4, finding N1 of plan
bootstrap-credentials-and-onboarding, routed by legacy-coordinator-agent on
2026-11-14 as a safety fix). `ansible/inventory/legacy.yml` declares the control
node `vps` with `ansible_connection: local`, so that the VPS manages itself with
no ssh credential toward itself. A local connection runs on WHATEVER machine
launched ansible. Without a guard, a play that selects `vps`, run from another
controller such as a hetzner-xubuntu seat, converges THAT controller as if it
were the VPS. `fabro-hosts.yml --limit vps` is one such run.

WHAT IS HELD. The entry's own `ansible_connection` resolves to `local` only when
the controller's machine-id equals the control node's machine-id, which the
entry declares. Otherwise the host fails before any task, with a message naming
the expected and the found machine-id. Because the guard lives on the inventory
entry, it covers every play that selects `vps`, including plays added later.

HOW. By running the committed inventory with the same `ansible-core` pin that
`just ansible-apply` executes, read out of the justfile. A scratch play that
selects `vps` runs a debug task only, so no host is changed. The controller's
identity is supplied through `control_node_identity_file`, the variable the
guard reads its machine-id from (default `/etc/machine-id`), so the test is
deterministic on every machine, the control node included.

Governing clause: `SPECIFICATION/non-functional-requirements.md`
§"Host provisioning tree" (a host is applied from the control node).
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
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_MACHINE_ID = re.compile(r"^[0-9a-f]{32}$")
_FOREIGN_MACHINE_ID = "0123456789abcdef0123456789abcdef"
_REACHED = "VPS-IDENTITY-GUARD-REACHED"
# A cold `uvx` resolves and caches ansible-core before the first play runs.
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


def _vps_entry() -> dict[str, object]:
    inventory = yaml.safe_load(_INVENTORY.read_text(encoding="utf-8"))
    entry = inventory["all"]["children"]["legacy"]["children"]["dev_hosts"]["hosts"]["vps"]
    assert isinstance(entry, dict), "the vps inventory entry must carry host variables"
    return entry


def _control_node_machine_id() -> str:
    machine_id = _vps_entry().get("control_node_machine_id")
    assert isinstance(machine_id, str), (
        "the vps entry must declare control_node_machine_id, the machine-id its "
        "local connection is valid for"
    )
    assert _MACHINE_ID.match(machine_id), machine_id
    return machine_id


def _run_play(*, tmp_path: Path, controller_machine_id: str) -> tuple[int, str]:
    identity = tmp_path / "machine-id"
    identity.write_text(f"{controller_machine_id}\n", encoding="utf-8")
    play = tmp_path / "play.yml"
    play.write_text(
        "---\n- name: vps identity guard fixture\n  hosts: vps\n  gather_facts: false\n"
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
            "vps",
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


def test_a_play_selecting_vps_on_another_controller_refuses_before_any_task(
    *, tmp_path: Path
) -> None:
    expected = _control_node_machine_id()
    returncode, output = _run_play(tmp_path=tmp_path, controller_machine_id=_FOREIGN_MACHINE_ID)
    assert returncode != 0, output
    assert _REACHED not in output, output
    assert expected in output, output
    assert _FOREIGN_MACHINE_ID in output, output


def test_a_play_selecting_vps_on_the_control_node_runs_over_the_local_connection(
    *, tmp_path: Path
) -> None:
    returncode, output = _run_play(
        tmp_path=tmp_path, controller_machine_id=_control_node_machine_id()
    )
    assert returncode == 0, output
    assert f"{_REACHED} local" in output, output
