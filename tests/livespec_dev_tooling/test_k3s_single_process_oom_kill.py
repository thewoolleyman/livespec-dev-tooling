"""Every k3s node's kubelet kills only the process that exceeds a container's memory limit.

Orchestrator work-item `bd-ib-3kdjct` (plan epic `bd-ib-nmuyjc`). On cgroup v2
the kubelet sets `memory.oom.group=1` on every container cgroup by default, so a
single runaway command inside a factory sandbox pod takes the whole container,
agent included, down with it. Measured 2026-11-02 in pod
`petri-01m6dp57ek5q0p8arn07bgwad8-l0`: the agent's pytest reached about 7.5 GB
against a 7630 MB limit, the group kill took the codex agent with it, and every
uncommitted change was lost.

WHAT THIS FILE GRADES. The `k3s_config` role installs a KubeletConfiguration
drop-in carrying `singleProcessOOMKill: true` into the directory k3s's kubelet
reads with `--config-dir`, on the server and on every agent. The directory is
derived from the node's committed profile, so a node on a non-default data
directory (hp-xubuntu, `/srv/sandbox-storage/k3s`) gets it where its kubelet
looks. These tests are STATIC reads of the committed role, like the sibling
`test_hp_coexistence_budget`: neither Ansible nor Jinja is importable in this
suite.

WHAT IS NOT PROVEN HERE. The behaviour itself is host-captured: a new pod's
container cgroup reading `memory.oom.group` 0, and a command that exceeds the
limit dying alone while the agent keeps running. No sandbox reaches a node's
cgroup tree.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "k3s_config"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_DOC = _ROLE / "HOST_VARS.md"
_PROFILES = _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles"
_INSTALL_TASK = "- name: Kill only the process that exceeds a container's memory limit"


def _task_block(*, body: str, name: str) -> str:
    """The text of ONE task, from its `- name:` line to the next task."""
    start = body.index(name)
    following = body.find("\n- name:", start + len(name))
    return body[start : following if following != -1 else len(body)]


def test_the_role_installs_the_single_process_oom_kill_drop_in_on_every_node() -> None:
    body = _TASKS.read_text(encoding="utf-8")
    assert _INSTALL_TASK in body, "k3s_config must install the single-process OOM kill drop-in"
    task = _task_block(body=body, name=_INSTALL_TASK)
    assert "singleProcessOOMKill: true" in task, task
    assert "kind: KubeletConfiguration" in task, task
    assert "apiVersion: kubelet.config.k8s.io/v1beta1" in task, task
    assert "cluster_role" not in task, (
        "the drop-in must not be gated on the cluster role: the server node runs "
        f"factory pods too:\n{task}"
    )
    assert "k3s_config_kubelet_conf_dir" in task, task


def test_the_drop_in_lands_where_each_nodes_kubelet_reads_its_config_dir() -> None:
    """`--config-dir=<data-dir>/agent/etc/kubelet.conf.d`, data-dir from the profile."""
    body = _TASKS.read_text(encoding="utf-8")
    resolve = _task_block(body=body, name="- name: Resolve this node's kubelet configuration")
    assert "NODE_DATA_DIR" in resolve, resolve
    assert "'/agent/etc/kubelet.conf.d'" in resolve, resolve
    assert "k3s_config_default_data_dir" in resolve, resolve
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    assert re.search(r"^k3s_config_default_data_dir: /var/lib/rancher/k3s$", defaults, re.MULTILINE)
    assert re.search(r"^k3s_config_single_process_oom_kill: true$", defaults, re.MULTILINE)
    hp = (_PROFILES / "hp-xubuntu.env").read_text(encoding="utf-8")
    assert "NODE_DATA_DIR=/srv/sandbox-storage/k3s" in hp, (
        "hp's kubelet reads /srv/sandbox-storage/k3s/agent/etc/kubelet.conf.d; the "
        "derivation must find that data directory in hp's profile"
    )


def test_turning_it_off_removes_the_drop_in() -> None:
    body = _TASKS.read_text(encoding="utf-8")
    remove = _task_block(body=body, name="- name: Remove the single-process OOM kill drop-in")
    assert "state: absent" in remove, remove
    assert "not (k3s_config_single_process_oom_kill | bool)" in remove, remove


def test_host_vars_documents_the_variables_and_the_rollout() -> None:
    doc = _DOC.read_text(encoding="utf-8")
    assert "## Single-process OOM kill" in doc
    for variable in (
        "k3s_config_single_process_oom_kill",
        "k3s_config_single_process_oom_kill_drop_in",
        "k3s_config_default_data_dir",
    ):
        assert f"`{variable}`" in doc, f"HOST_VARS.md must document {variable}"
    assert "restart-k3s-agent.yml" in doc, "the doc must say how the change takes effect"
    assert "Rollback" in doc
