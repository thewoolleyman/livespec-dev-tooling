"""A dispatch-only host gets the registry role's client logins and nothing else from it.

Work-item livespec-dev-tooling-yyadq6. A host where a Dispatcher runs natively, but whose own
provisioning lives in another repository, needs a dev-token login for every registered
factory. The token can only be read with the factory host's administration identity, which
only this tree's control node holds. So this tree reaches such a host through the
`fabro_dispatch_clients` group and runs the `fabro_factory_registry` role with its render
switch off: the client logins run, and the registry file and fleet-limit files are not
written. The registry itself stays declared once, in `group_vars/dev_hosts.yml`.

No test here pins a committed configuration VALUE (maintainer ruling: no test is tied to a
config value's actual value). Each asserts structure or behaviour instead: that a dispatch
client resolves the SAME registry the dev hosts declare, that the play guards the one-writer
rule before the role runs, that the guard refuses a render switched on by any means, and that
the switch gates exactly the file writes. The ansible runs use the pinned `ansible-core` and
reach no host: an ad-hoc `debug` and an `assert` run on the controller, and `--list-tasks` only
selects.
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
_GROUP = "fabro_dispatch_clients"
_GUARD_TASK = "Refuse to render the factory registry on a dispatch-only host"
_GUARD_TAG = "fabro_dispatch_client_guard"
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


def _resolved_entries_per_client() -> dict[str, Any]:
    """Each dispatch client's resolved registry entries, as the controller renders them."""
    run = _run(
        "ansible",
        "-i",
        str(_INVENTORY),
        _GROUP,
        "-m",
        "ansible.builtin.debug",
        "-a",
        "msg={{ fabro_factory_registry_entries | items2dict }}",
    )
    # The default ad-hoc output prints one `<host> | SUCCESS => {...}` JSON block per host.
    return {
        match["host"]: json.loads(match["result"])["msg"]
        for match in _AD_HOC_RESULT.finditer(run.stdout)
    }


def _guard_run(*, render: bool) -> subprocess.CompletedProcess[str]:
    """Run only the dispatch-client play's guard, with the render switch forced from outside."""
    return _run(
        "ansible-playbook",
        "-i",
        str(_INVENTORY),
        str(_PLAYBOOK),
        "--limit",
        _GROUP,
        "--tags",
        _GUARD_TAG,
        "-e",
        json.dumps({"fabro_factory_registry_render": render}),
    )


def _task(name: str) -> dict[str, Any]:
    [task] = [t for t in yaml.safe_load(_TASKS.read_text()) if t.get("name") == name]
    return task


def test_every_dispatch_client_resolves_the_registry_the_dev_hosts_declare() -> None:
    declared = yaml.safe_load(_DEV_HOSTS_VARS.read_text())["fabro_factory_registry"]
    resolved = _resolved_entries_per_client()
    assert resolved, f"the inventory's {_GROUP} group resolves no host"
    for host, entries in resolved.items():
        assert entries == declared, host


def test_the_dispatch_client_play_guards_the_one_writer_rule_before_the_role_runs() -> None:
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
    assert tasks[0].startswith(_GUARD_TASK), tasks
    assert all(task.startswith("fabro_factory_registry : ") for task in tasks[1:]), tasks


def test_the_guard_refuses_a_render_switched_on_for_a_dispatch_client() -> None:
    refused = _guard_run(render=True)
    allowed = _guard_run(render=False)
    assert refused.returncode != 0, refused.stdout + refused.stderr
    assert "two writers" in refused.stdout, refused.stdout
    assert allowed.returncode == 0, allowed.stdout + allowed.stderr
    assert "failed=0" in allowed.stdout, allowed.stdout


def test_the_render_switch_gates_every_file_write_and_no_login() -> None:
    for name in _RENDER_TASKS:
        assert _RENDER_SWITCH in str(_task(name).get("when", "")), name
    for name in _LOGIN_TASKS:
        assert "fabro_factory_registry_render" not in str(_task(name).get("when", "")), name
