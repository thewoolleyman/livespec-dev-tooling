"""The root-level CPU share system.slice holds on the k3s server node.

Work-item `livespec-dev-tooling-cetudy`. Measured on poweredge-xubuntu on
2026-11-05: the k3s server runs in `/system.slice/k3s.service`, and its
root-level parent `system.slice` sits at cpu.weight 100 against
`kubepods.slice` at 2813, the weight kubelet's systemd cgroup driver derives
from 72 allocatable CPUs. At full contention all of system.slice was therefore
entitled to about 2.5 of 72 CPUs, and the API server's datastore p99 reached
7 s while the node was saturated. A unit-level `CPUWeight=` (the existing
`k3s_config_cpu_weight`) only orders units INSIDE system.slice, so it cannot
move that share. These static tests grade the committed role (neither Ansible
nor Jinja is importable here):

- the slice weight is a host variable, off by default, and declared only on
  poweredge-xubuntu, at a value that entitles system.slice to at least 8 of
  72 CPUs against kubepods.slice under full contention;
- the drop-in is a `[Slice]` `CPUWeight=` rendered from that variable into
  `system.slice.d`, and it pins no CPU (no `AllowedCPUs=`);
- the apply is a daemon-reload and NEVER a restart: no task notifies a handler
  or asks for a unit `state:`;
- every task carries its own tag, so an apply can be narrowed to it, and an
  empty value removes the drop-in, which is the revert.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_K3S = _ANSIBLE / "roles" / "k3s_config"
_HOST_VARS = _ANSIBLE / "inventory" / "host_vars"
_POWEREDGE = "poweredge-xubuntu"
_VARIABLE = "k3s_config_system_slice_cpu_weight"
_TAG = "tags: [k3s_system_slice_cpu_weight]"
# kubepods.slice's cpu.weight on a 72-CPU node, as kubelet derives it:
# 72000m -> 73728 cpu.shares -> 1 + (73728 - 2) * 9999 / 262142.
_KUBEPODS_WEIGHT = 1 + ((72 * 1024 - 2) * 9999) // 262142
# user.slice and init.scope, the other root-level peers at systemd's default.
_OTHER_ROOT_PEERS = 100 + 100
_NODE_CPUS = 72
_MIN_ENTITLED_CPUS = 8


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _tasks(text: str) -> list[str]:
    """Split a flat task file into its top-level task blocks."""
    starts = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    return [text[start:end] for start, end in zip(starts, [*starts[1:], len(text)], strict=True)]


def _slice_weight_tasks() -> list[str]:
    return [
        task
        for task in _tasks(_read(_K3S / "tasks" / "main.yml"))
        if "system.slice CPU weight" in task.split("\n", 1)[0]
    ]


def test_the_slice_weight_is_off_by_default_and_declared_only_on_poweredge() -> None:
    assert f'{_VARIABLE}: ""' in _read(_K3S / "defaults" / "main.yml")
    for host_vars in sorted(_HOST_VARS.glob("*.yml")):
        declared = re.findall(rf"^{_VARIABLE}: (.*)$", _read(host_vars), re.MULTILINE)
        if host_vars.stem == _POWEREDGE:
            assert len(declared) == 1, declared
            weight = int(declared[0])
            entitled = weight / (weight + _KUBEPODS_WEIGHT + _OTHER_ROOT_PEERS) * _NODE_CPUS
            assert entitled >= _MIN_ENTITLED_CPUS, (weight, entitled)
        else:
            assert declared == [], (host_vars.name, declared)


def test_the_drop_in_is_a_slice_cpu_weight_and_pins_no_cpu() -> None:
    template = _read(_K3S / "templates" / "system-slice-cpu-weight.conf.j2")
    assert f"[Slice]\nCPUWeight={{{{ {_VARIABLE} }}}}\n" in template
    assert "AllowedCPUs" not in template
    defaults = _read(_K3S / "defaults" / "main.yml")
    assert "k3s_config_system_slice_drop_in_dir: /etc/systemd/system/system.slice.d" in defaults


def test_the_apply_is_a_daemon_reload_and_never_a_restart() -> None:
    tasks = _slice_weight_tasks()
    assert len(tasks) == 5, tasks
    for task in tasks:
        assert "notify" not in task, task
        assert "state: restarted" not in task and "state: reloaded" not in task, task
    reloads = [task for task in tasks if "ansible.builtin.systemd_service:" in task]
    assert len(reloads) == 1, reloads
    body = reloads[0].split("ansible.builtin.systemd_service:", 1)[1]
    assert "daemon_reload: true" in body
    assert "\n    state:" not in body and "\n    name:" not in body, body


def test_every_task_carries_its_own_tag_and_an_empty_value_removes_the_drop_in() -> None:
    tasks = _slice_weight_tasks()
    for task in tasks:
        assert _TAG in task, task
    removals = [task for task in tasks if "state: absent" in task]
    assert len(removals) == 1, removals
    assert f"when: {_VARIABLE} | string | length == 0" in removals[0]
