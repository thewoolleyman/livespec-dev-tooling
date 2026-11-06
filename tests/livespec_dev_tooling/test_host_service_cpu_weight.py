"""The CPU weight the Fabro server instances and the k3s unit run with.

Orchestrator work-item `bd-ib-s6a2ex`: under a CI burst on gmktec-xubuntu the
Fabro server instances and the k3s agent sat in `system.slice` at systemd's
default weight of 100. These static tests grade the committed roles (neither
Ansible nor Jinja is importable here):

- each weight is a host variable, off by default, and declared 2000 only on
  gmktec-xubuntu;
- each drop-in is a `[Service]` `CPUWeight=` rendered from that variable;
- the apply is a daemon-reload and NEVER a restart: no task of the new role or
  of the new k3s_config tasks notifies a handler or asks for a unit `state:`,
  so neither can reach the fabro_server restart chain;
- every new task carries its own tag, so an apply can be narrowed to it.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "fabro_server_cpu_weight"
_K3S = _ANSIBLE / "roles" / "k3s_config"
_HOST_VARS = _ANSIBLE / "inventory" / "host_vars"
_GMKTEC = "gmktec-xubuntu"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tasks(text: str) -> list[str]:
    """Split a flat task file into its top-level task blocks."""
    starts = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    return [text[start:end] for start, end in zip(starts, [*starts[1:], len(text)], strict=True)]


def _k3s_cpu_weight_tasks() -> list[str]:
    # The k3s UNIT's weight tasks only. The system.slice weight tasks
    # (livespec-dev-tooling-cetudy) are graded by test_k3s_system_slice_cpu_weight.py.
    return [
        task
        for task in _tasks(_read(_K3S / "tasks" / "main.yml"))
        if "CPU weight" in (name := task.split("\n", 1)[0]) and "system.slice" not in name
    ]


def test_each_weight_is_off_by_default_and_2000_only_on_gmktec() -> None:
    assert 'fabro_server_cpu_weight_value: ""' in _read(_ROLE / "defaults" / "main.yml")
    assert 'k3s_config_cpu_weight: ""' in _read(_K3S / "defaults" / "main.yml")
    for host_vars in sorted(_HOST_VARS.glob("*.yml")):
        text = _read(host_vars)
        declared = re.findall(
            r"^(fabro_server_cpu_weight_value|k3s_config_cpu_weight): (.*)$", text, re.MULTILINE
        )
        if host_vars.stem == _GMKTEC:
            assert sorted(declared) == [
                ("fabro_server_cpu_weight_value", "2000"),
                ("k3s_config_cpu_weight", "2000"),
            ], declared
        else:
            assert declared == [], (host_vars.name, declared)


def test_each_drop_in_is_a_service_cpu_weight_from_its_variable() -> None:
    fabro = _read(_ROLE / "templates" / "cpu-weight.conf.j2")
    k3s = _read(_K3S / "templates" / "cpu-weight.conf.j2")
    assert "[Service]\nCPUWeight={{ fabro_server_cpu_weight_value }}\n" in fabro
    assert "[Service]\nCPUWeight={{ k3s_config_cpu_weight }}\n" in k3s
    tasks = _read(_ROLE / "tasks" / "main.yml")
    assert "fabro_server_instances | default([]) | map(attribute='unit_name') | list" in tasks
    assert '{{ item }}.service.d/{{ fabro_server_cpu_weight_drop_in }}"' in tasks
    assert (
        "/etc/systemd/system/{{ 'k3s-agent' if k3s_config_cluster_role == 'agent' else 'k3s' }}.service.d"
        in _read(_K3S / "defaults" / "main.yml")
    )


def test_the_apply_is_a_daemon_reload_and_never_a_restart() -> None:
    role_tasks = _tasks(_read(_ROLE / "tasks" / "main.yml"))
    k3s_tasks = _k3s_cpu_weight_tasks()
    assert len(k3s_tasks) == 5, k3s_tasks
    assert not (_ROLE / "handlers").exists()
    for task in [*role_tasks, *k3s_tasks]:
        assert "notify" not in task, task
        assert "state: restarted" not in task and "state: reloaded" not in task, task
    for tasks in (role_tasks, k3s_tasks):
        reloads = [task for task in tasks if "ansible.builtin.systemd_service:" in task]
        assert len(reloads) == 1, reloads
        body = reloads[0].split("ansible.builtin.systemd_service:", 1)[1]
        assert "daemon_reload: true" in body
        assert "\n    state:" not in body and "\n    name:" not in body, body


def test_every_new_task_carries_its_own_tag_and_the_playbook_reaches_the_role() -> None:
    for task in _tasks(_read(_ROLE / "tasks" / "main.yml")):
        assert "tags: [fabro_server_cpu_weight]" in task, task
    for task in _k3s_cpu_weight_tasks():
        assert "tags: [k3s_cpu_weight]" in task, task
    playbook = _read(_ANSIBLE / "fabro-hosts.yml")
    sandbox_play = playbook.split("- name: Fabro services on the dev host", 1)[0]
    assert (
        "    - role: fabro_server_cpu_weight\n      tags: [fabro_server_cpu_weight]\n"
        in sandbox_play
    )
