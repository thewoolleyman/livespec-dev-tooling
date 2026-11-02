"""`ansible/restart-k3s-server.yml` — the one committed way to restart the pool server's k3s unit.

Orchestrator work-item `bd-ib-v7h3az`. The node_sysctl receive-buffer fix reaches
flannel only at the next k3s start, and the committed paths could not get the
SERVER there without a whole-host reboot: `restart-k3s-agent.yml` refuses the
server, and a hand `systemctl restart k3s` is what the fleet host guard refuses.

WHAT THIS FILE GRADES, statically (neither Ansible nor Jinja is importable here):
the play is fenced by a confirmation that must name this host AND a server
cluster_role; the restart sits behind the same two-read arc-runners idle gate as
`reboot-ci-server.yml`, whose rescue FAILS rather than letting the restart run;
check mode withholds the restart; and the restart is followed by reads of
/readyz, every node's Ready condition, and the new k3s-server process's rtnl
socket receive buffers. The behaviour on the host is host-captured by the
work-item's proof, not here.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAYBOOK = _REPO_ROOT / "ansible" / "restart-k3s-server.yml"
_RESTART_TASK = "- name: Restart the k3s server unit"
_GATE_TASK = "- name: Wait for two consecutive idle reads of the runner pool"


def _text() -> str:
    return _PLAYBOOK.read_text(encoding="utf-8")


def _requested_expression() -> str:
    match = re.search(
        r"^    k3s_server_restart_requested: >-\n(?P<body>(?:      [^\n]*\n)+)",
        _text(),
        re.MULTILINE,
    )
    assert match, "the play must define k3s_server_restart_requested"
    return " ".join(match["body"].split())


def _requested(*, confirm: str, inventory_hostname: str, cluster_role: str) -> bool:
    expression = _requested_expression()
    assert expression == (
        "{{ k3s_server_restart_confirm | default('') == inventory_hostname "
        "and cluster_role | default('') == 'server' }}"
    ), expression
    return confirm == inventory_hostname and cluster_role == "server"


def test_the_fence_admits_only_a_confirmation_naming_the_server_itself() -> None:
    assert _requested(
        confirm="poweredge-xubuntu", inventory_hostname="poweredge-xubuntu", cluster_role="server"
    )
    assert not _requested(confirm="", inventory_hostname="poweredge-xubuntu", cluster_role="server")
    assert not _requested(
        confirm="gmktec-xubuntu", inventory_hostname="poweredge-xubuntu", cluster_role="server"
    )
    assert not _requested(
        confirm="gmktec-xubuntu", inventory_hostname="gmktec-xubuntu", cluster_role="agent"
    )


def test_the_restart_runs_only_after_the_idle_gate_whose_rescue_fails() -> None:
    text = _text()
    assert text.index(_GATE_TASK) < text.index(_RESTART_TASK)
    rescue = text[text.index("      rescue:") : text.index("- name: Note that a check run")]
    assert "ansible.builtin.fail:" in rescue
    assert "--namespace '{{ k3s_server_restart_runner_namespace }}'" in text
    assert "k3s_server_restart_runner_namespace: arc-runners" in text
    gate = text[text.index(_GATE_TASK) : text.index("      rescue:")]
    assert "check_mode: false" in gate
    assert "k3s_server_restart_pool_reads.stdout != ''" in gate


def test_check_mode_withholds_the_restart() -> None:
    text = _text()
    block = text[text.index("- name: Restart the server and verify the cluster came back") :]
    assert "- not ansible_check_mode" in block.split("block:")[0]
    assert "- k3s_server_restart_requested | bool" in block.split("block:")[0]


def test_the_restart_restarts_the_server_unit_and_nothing_else() -> None:
    text = _text()
    assert "k3s_server_restart_unit: k3s\n" in text
    restart = text[
        text.index(_RESTART_TASK) : text.index("- name: Wait until the API reports ready")
    ]
    assert "ansible.builtin.systemd_service:" in restart
    assert 'name: "{{ k3s_server_restart_unit }}"' in restart
    assert "state: restarted" in restart
    assert text.count("state: restarted") == 1
    assert "ansible.builtin.reboot" not in text


def test_the_restart_is_verified_by_readyz_ready_nodes_and_rtnl_buffers() -> None:
    text = _text()
    assert "kubectl get --raw /readyz" in text
    assert "'readyz=ok' not in k3s_server_restart_api_reads.stdout" in text
    assert "'=False' in k3s_server_restart_api_reads.stdout" in text
    assert "ss -f netlink -a -p -m" in text
    assert "rtnl:k3s-server/${pid}" in text
    assert "sysctl -n net.core.rmem_default" in text
