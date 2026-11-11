"""`ansible/k3s-window-drain.yml` — pause runner intake and cordon nodes for a k3s window.

Orchestrator work-items `bd-ib-v7h3az` and `bd-ib-3kdjct`: the maintainer-approved
combined k3s restart window could not run because the runner pool never went idle,
and the only ways to drain load were hand `kubectl` mutations the fleet host guard
refuses. These static tests grade the committed playbook (neither Ansible nor
Jinja is importable here):

- the fence: a run acts only when the confirmation names the same action as
  `k3s_window_action`, and only on the pool's server;
- pause-arc records each runner set's limit BEFORE zeroing it, and never
  overwrites an existing record (a re-run must not record the paused 0);
- restore-arc restores the recorded value exactly, drops the record, and refuses
  when nothing was recorded;
- the node actions are exactly cordon and uncordon of a named node: a pool host,
  or any Node registered in the cluster, read on the server, with an
  unregistered name refused (the generic hold/lift for any k3s node);
- nothing evicts, drains or deletes a pod.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAYBOOK = _REPO_ROOT / "ansible" / "k3s-window-drain.yml"
_RECORD = "livespec.dev/window-paused-max-runners"


def _text() -> str:
    return _PLAYBOOK.read_text(encoding="utf-8")


def _task(*, name: str) -> str:
    text = _text()
    start = text.index(f"- name: {name}")
    following = text.find("\n    - name: ", start + 1)
    return text[start : following if following != -1 else len(text)]


def _requested(*, action: str, confirm: str, cluster_role: str) -> bool:
    """The fence, evaluated as the playbook's own expression states it."""
    match = re.search(
        r"^    k3s_window_requested: >-\n(?P<body>(?:      [^\n]*\n)+)", _text(), re.MULTILINE
    )
    assert match
    expression = " ".join(match["body"].split())
    assert expression == (
        "{{ k3s_window_action | default('') in k3s_window_actions "
        "and k3s_window_confirm | default('') == k3s_window_action | default('') "
        "and cluster_role | default('') == 'server' }}"
    ), expression
    actions = ["pause-arc", "restore-arc", "cordon", "uncordon"]
    assert "k3s_window_actions: [pause-arc, restore-arc, cordon, uncordon]" in _text()
    return action in actions and confirm == action and cluster_role == "server"


def test_the_fence_needs_a_matching_confirmation_on_the_server() -> None:
    assert _requested(action="pause-arc", confirm="pause-arc", cluster_role="server")
    assert not _requested(action="pause-arc", confirm="", cluster_role="server")
    assert not _requested(action="pause-arc", confirm="restore-arc", cluster_role="server")
    assert not _requested(action="pause-arc", confirm="pause-arc", cluster_role="agent")
    assert not _requested(action="drain", confirm="drain", cluster_role="server")


def test_pause_records_the_limit_before_zeroing_and_keeps_an_existing_record() -> None:
    task = _task(name="Pause every runner set's intake, recording its limit first")
    assert task.index("kubectl annotate autoscalingrunnerset") < task.index(
        '--patch \'{"spec":{"maxRunners":0}}\''
    )
    assert 'if test -z "${recorded}"; then' in task
    assert '"${max}"' in task.split("kubectl annotate", 1)[1].split("fi", 1)[0]
    assert "k3s_window_action == 'pause-arc'" in task


def test_restore_writes_the_recorded_value_drops_the_record_and_refuses_when_none() -> None:
    task = _task(name="Restore every recorded runner set's limit exactly")
    assert '{\\"spec\\":{\\"maxRunners\\":${recorded}}}' in task
    assert "'{{ k3s_window_record_annotation }}-'" in task
    assert "refusing restore-arc: no runner set carries a recorded limit" in task
    assert "*[!0-9]*)" in task
    assert f"k3s_window_record_annotation: {_RECORD}" in _text()


def test_the_node_actions_are_cordon_and_uncordon_of_a_named_pool_node() -> None:
    assert "k3s_window_node_actions: [cordon, uncordon]" in _text()
    assert "k3s_window_node | default('') in groups['ci_pool']" in _text()
    refuse = _task(
        name="Refuse a node action that does not name a pool node or a registered cluster node"
    )
    assert "ansible.builtin.fail:" in refuse
    node = _task(name="Cordon or uncordon the confirmed node")
    assert '- "{{ k3s_window_action }}"' in node
    assert "k3s_window_action in k3s_window_node_actions" in node


def test_a_node_outside_the_pool_inventory_is_held_when_the_cluster_registers_it() -> None:
    assert "{{ (k3s_window_node_read.rc | default(1)) == 0 }}" in _text()
    read = _task(name="Read whether the named node is registered in the cluster")
    for word in ("- kubectl", "- get", "- node", '- "{{ k3s_window_node }}"'):
        assert word in read, word
    assert "register: k3s_window_node_read" in read
    assert "changed_when: false" in read
    assert "failed_when: false" in read
    assert "check_mode: false" in read
    assert "not (k3s_window_node_known | bool)" in read
    refuse = _task(
        name="Refuse a node action that does not name a pool node or a registered cluster node"
    )
    assert "not (k3s_window_node_known | bool)" in refuse
    assert "not (k3s_window_node_registered | bool)" in refuse
    assert _text().index("- name: Read whether the named node") < _text().index(
        "- name: Refuse a node action"
    )


def test_holding_an_already_held_node_changes_nothing() -> None:
    node = _task(name="Cordon or uncordon the confirmed node")
    assert "changed_when: \"'already' not in k3s_window_node_change.stdout\"" in node


def test_nothing_evicts_drains_or_deletes_a_pod() -> None:
    executable = "\n".join(
        line for line in _text().splitlines() if not line.lstrip().startswith("#")
    )
    for forbidden in ("kubectl drain", "kubectl delete", "evict", "--force"):
        assert forbidden not in executable, forbidden
