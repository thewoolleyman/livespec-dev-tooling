"""The vps-remote alias reaches the VPS dev host from the control node, and only then.

WHY (work-item livespec-dev-tooling-voazyv slice S3). The control node
(hetzner-xubuntu) drift-checks and applies ansible/dev-host.yml against the VPS over
ssh while the dev-host roles move off it. The alias `vps-remote` sits in its own
group, in no `dev_hosts` group, so the default play still reaches exactly `vps`.

WHAT IS HELD.
1. `vps-remote` is in no `dev_hosts` group, and `dev-host.yml` defaults to `dev_hosts`.
2. The default play selects exactly `vps`; with `dev_host_group=dev_hosts_remote` it
   selects exactly `vps-remote`, so one of the two is selected per controller.
3. The alias resolves the vps's host_vars and the dev_hosts group_vars unchanged.

HOW. By running the committed inventory with the `ansible-core` pin that `just
ansible-apply` executes, listing hosts only, so nothing is changed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE_DIR = _REPO_ROOT / "ansible"
_INVENTORY = _ANSIBLE_DIR / "inventory" / "legacy.yml"
_PLAY = _ANSIBLE_DIR / "dev-host.yml"
_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_TIMEOUT_SECONDS = 600


def _pin() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        (_REPO_ROOT / "justfile").read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None
    found = _PIN.search(recipe["body"])
    assert found is not None
    return found[0]


def _ansible(*, tool: str, args: list[str]) -> str:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    } | {"ANSIBLE_NOCOWS": "1"}
    result = subprocess.run(
        ["uvx", "--from", _pin(), tool, "-i", str(_INVENTORY), *args],
        cwd=_REPO_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=_TIMEOUT_SECONDS,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def _selected(*, extra: list[str]) -> list[str]:
    output = _ansible(tool="ansible-playbook", args=["--list-hosts", *extra, str(_PLAY)])
    return [line.strip() for line in output.splitlines() if re.fullmatch(r"\s{6}\S+", line)]


def test_the_alias_is_in_no_dev_hosts_group_and_the_play_defaults_to_dev_hosts() -> None:
    inventory = yaml.safe_load(_INVENTORY.read_text(encoding="utf-8"))
    children = inventory["all"]["children"]
    assert "vps-remote" in children["dev_hosts_remote"]["hosts"]
    assert "vps-remote" not in children["legacy"]["children"]["dev_hosts"]["hosts"]
    assert "default('dev_hosts')" in _PLAY.read_text(encoding="utf-8")


def test_exactly_one_of_vps_and_vps_remote_is_selected_per_controller() -> None:
    assert _selected(extra=[]) == ["vps"]
    assert _selected(extra=["-e", "dev_host_group=dev_hosts_remote"]) == ["vps-remote"]


def test_the_alias_resolves_the_vps_host_vars_and_dev_hosts_group_vars() -> None:
    def resolved(host: str) -> dict[str, object]:
        out = json.loads(_ansible(tool="ansible-inventory", args=["--host", host]))
        for connection_key in (
            "ansible_host",
            "ansible_user",
            "ansible_connection",
            "control_node_machine_id",
            "control_node_identity_found",
            "inventory_hostname",
            # Group var of caam_role_holder, which only caam-role-holder.yml reads.
            "caam_delivery_push_ref",
        ):
            out.pop(connection_key, None)
        return out

    assert resolved("vps-remote") == resolved("vps")
