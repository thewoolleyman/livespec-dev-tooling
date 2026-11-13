"""A dispatch-only host gets the registry role's client logins and nothing else from it.

Work-item livespec-dev-tooling-yyadq6. A host where a Dispatcher runs natively, but whose own
provisioning lives in another repository, needs a dev-token login for every registered
factory. The token can only be read with the factory host's administration identity, which
only this tree's control node holds. So this tree reaches such a host through the
`fabro_dispatch_clients` group and runs the `fabro_factory_registry` role with its render
switch off: the client logins run, and the registry file and fleet-limit files are not
written. The registry itself stays declared once, in `group_vars/dev_hosts.yml`.

The first two tests run the committed inventory and play under the pinned `ansible-core`, and
reach no host: an ad-hoc `debug` resolves variables on the controller, and `--list-hosts` /
`--list-tasks` only select. The third reads the committed tasks, because which tasks a switch
gates is a property of the file.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"
_PLAYBOOK = _ANSIBLE / "fabro-hosts.yml"
_DEV_HOSTS_VARS = _ANSIBLE / "inventory" / "group_vars" / "dev_hosts.yml"
_ROLE = _ANSIBLE / "roles" / "fabro_factory_registry"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_GROUP = "fabro_dispatch_clients"
_RENDER_SWITCH = "fabro_factory_registry_render | bool"
_RENDER_TASKS = (
    "Create the directory this host's Fabro factory registry lives in",
    "Install this host's Fabro factory registry",
    "Create the directory this host's Fabro fleet limits live in",
    "Install each Fabro factory's fleet limit",
)
_LOGIN_TASKS = (
    "Read each registered factory's dev token on its own host",
    "Log this host's Fabro client in to each registered factory",
)
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_TIMEOUT_SECONDS = 600
_AD_HOC_RESULT = re.compile(
    r"^(?P<host>\S+) \| SUCCESS => (?P<result>\{.*?^\})", re.MULTILINE | re.DOTALL
)


def _pin() -> str:
    [pin] = sorted(set(_ANSIBLE_CORE_PIN.findall((_REPO_ROOT / "justfile").read_text())))
    return pin


def _run(*argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uvx", "--from", _pin(), *argv],
        cwd=_REPO_ROOT,
        env={**os.environ, "ANSIBLE_NOCOLOR": "1"},
        capture_output=True,
        text=True,
        check=False,
        timeout=_TIMEOUT_SECONDS,
    )


def _resolved_per_client() -> dict[str, Any]:
    """Each dispatch client's resolved entries and switches, as the controller renders them."""
    expression = (
        "{{ {'entries': fabro_factory_registry_entries | items2dict,"
        " 'render': fabro_factory_registry_render,"
        " 'login': fabro_factory_registry_client_login} }}"
    )
    run = _run(
        "ansible",
        "-i",
        str(_INVENTORY),
        _GROUP,
        "-m",
        "ansible.builtin.debug",
        "-a",
        f"msg={expression}",
    )
    # The default ad-hoc output prints one `<host> | SUCCESS => {...}` JSON block per host.
    return {
        match["host"]: json.loads(match["result"])["msg"]
        for match in _AD_HOC_RESULT.finditer(run.stdout)
    }


def _task(name: str) -> dict[str, Any]:
    [task] = [t for t in yaml.safe_load(_TASKS.read_text()) if t.get("name") == name]
    return task


def test_every_dispatch_client_logs_in_to_the_one_declared_registry_and_renders_nothing() -> None:
    declared = yaml.safe_load(_DEV_HOSTS_VARS.read_text())["fabro_factory_registry"]
    resolved = _resolved_per_client()
    assert resolved, f"the inventory's {_GROUP} group resolves no host"
    for host, values in resolved.items():
        assert values["entries"] == declared, host
        assert values["login"] is True, host
        assert values["render"] is False, host


def test_a_committed_play_reaches_the_dispatch_clients_with_the_registry_role_alone() -> None:
    run = _run(
        "ansible-playbook",
        "-i",
        str(_INVENTORY),
        str(_PLAYBOOK),
        "--limit",
        _GROUP,
        "--list-tasks",
    )
    plays = [block for block in run.stdout.split("\n  play #") if f"({_GROUP})" in block]
    assert len(plays) == 1, run.stdout + run.stderr
    tasks = [line.strip() for line in plays[0].splitlines() if "\tTAGS:" in line][1:]
    assert tasks, plays[0]
    assert all(task.startswith("fabro_factory_registry : ") for task in tasks), tasks


def test_the_render_switch_gates_every_file_write_and_no_login() -> None:
    assert yaml.safe_load(_DEFAULTS.read_text()).get("fabro_factory_registry_render") is True
    for name in _RENDER_TASKS:
        assert _RENDER_SWITCH in str(_task(name).get("when", "")), name
    for name in _LOGIN_TASKS:
        assert "fabro_factory_registry_render" not in str(_task(name).get("when", "")), name
