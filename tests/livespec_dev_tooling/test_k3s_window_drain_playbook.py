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
- the hold actions are exactly cordon and uncordon of a named node: a pool host,
  or any Node registered in the cluster, read on the server, with an
  unregistered name refused (the generic hold/lift for any k3s node);
- only the `evacuate` and `clear-lost` task deletes a pod, and nothing drains or
  evicts one.

`evacuate` and `clear-lost` (the 2026-11-12 listener outage after a pool node was
powered off) are one shell task that takes every input from its environment and
carries no Jinja, so the behaviour tests below run the committed script itself
under bash against a stand-in `kubectl`. The stand-in serves a pod table keyed by
node, honours the `spec.nodeName` field selector, logs every invocation and drops
a deleted pod from the table. No test contacts a cluster.
"""

from __future__ import annotations

import os
import re
import subprocess
import textwrap
from dataclasses import dataclass
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
    actions = ["pause-arc", "restore-arc", "cordon", "uncordon", "evacuate", "clear-lost"]
    listed = "k3s_window_actions: [pause-arc, restore-arc, cordon, uncordon, evacuate, clear-lost]"
    assert listed in _text()
    return action in actions and confirm == action and cluster_role == "server"


def test_the_fence_needs_a_matching_confirmation_on_the_server() -> None:
    assert _requested(action="pause-arc", confirm="pause-arc", cluster_role="server")
    assert not _requested(action="pause-arc", confirm="", cluster_role="server")
    assert not _requested(action="pause-arc", confirm="restore-arc", cluster_role="server")
    assert not _requested(action="pause-arc", confirm="pause-arc", cluster_role="agent")
    assert not _requested(action="drain", confirm="drain", cluster_role="server")
    for action in ("evacuate", "clear-lost"):
        assert _requested(action=action, confirm=action, cluster_role="server")
        assert not _requested(action=action, confirm="", cluster_role="server")
        assert not _requested(action=action, confirm="cordon", cluster_role="server")
        assert not _requested(action=action, confirm=action, cluster_role="agent")
    assert not _requested(action="evacuate", confirm="clear-lost", cluster_role="server")
    assert not _requested(action="clear-lost", confirm="evacuate", cluster_role="server")


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
    assert "k3s_window_node_actions: [cordon, uncordon, evacuate, clear-lost]" in _text()
    assert "k3s_window_hold_actions: [cordon, uncordon]" in _text()
    assert "k3s_window_node | default('') in groups['ci_pool']" in _text()
    refuse = _task(
        name="Refuse a node action that does not name a pool node or a registered cluster node"
    )
    assert "ansible.builtin.fail:" in refuse
    node = _task(name="Cordon or uncordon the confirmed node")
    assert '- "{{ k3s_window_action }}"' in node
    assert "k3s_window_action in k3s_window_hold_actions" in node
    assert "k3s_window_action in k3s_window_node_actions" in refuse


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


_FACTORY_REASON = "a factory namespace pod follows the dispatcher's cancel-and-re-dispatch route"
_POD_TASK = "Evacuate a cordoned node's recreated pods, or clear a lost node's pods"


def test_only_the_pod_task_deletes_and_nothing_drains_or_evicts() -> None:
    pod_task = _task(name=_POD_TASK)
    elsewhere = "\n".join(
        line
        for line in _text().replace(pod_task, "").splitlines()
        if not line.lstrip().startswith("#")
    )
    for forbidden in ("kubectl drain", "kubectl delete", "evict", "--force"):
        assert forbidden not in elsewhere, forbidden
    for forbidden in ("kubectl drain", "evict"):
        assert forbidden not in pod_task, forbidden
    assert pod_task.count("kubectl delete pod") == 2
    assert pod_task.count("--force") == 1


def test_the_header_states_the_two_deleting_actions_and_no_longer_denies_them() -> None:
    header = _text().split("\n- name: ", 1)[0]
    assert "NOTHING HERE EVICTS, DRAINS OR DELETES A POD" not in header
    assert "FOUR ACTIONS" not in header
    assert "SIX ACTIONS, ONE CONFIRMATION EACH" in header
    for stated in (
        "#   evacuate     — BEFORE a planned power-off",
        "#   clear-lost   — AFTER a node is already gone",
        "2026-11-12",
        "AutoscalingListener",
        "THE OWNER RULE",
        "livespec-dev-tooling-acgcwp",
        "k3s_window_node_confirm",
        "k3s-window-drain-committed-evacuate",
        "a DaemonSet's pod",
    ):
        assert stated in header, stated


def test_the_pod_task_is_fenced_node_scoped_and_takes_its_inputs_from_the_environment() -> None:
    task = _task(name=_POD_TASK)
    assert "k3s_window_requested | bool" in task
    assert "k3s_window_action in k3s_window_pod_actions" in task
    assert "k3s_window_pod_actions: [evacuate, clear-lost]" in _text()
    assert (
        "k3s_window_recreating_owner_kinds: [AutoscalingListener, ReplicaSet, StatefulSet]"
        in _text()
    )
    assert "k3s_window_kept_namespaces: [factory, factory-mi-homelab]" in _text()
    assert "k3s_window_evacuate_wait_seconds: 120" in _text()
    assert 'K3S_WINDOW_NODE: "{{ k3s_window_node }}"' in task
    assert "K3S_WINDOW_DRY_RUN: \"{{ ansible_check_mode | ternary('true', 'false') }}\"" in task
    assert "changed_when: k3s_window_pods.stdout is search('(?m)^(deleted|cleared) ')" in task
    assert _text().index("- name: Refuse a node action") < _text().index(f"- name: {_POD_TASK}")
    assert "{{" not in _pod_script()
    assert "(k3s_window_pods.stdout_lines | default([]))" in _task(
        name="Report what the action did"
    )


def _node_confirmed(*, action: str, node: str, node_confirm: str) -> bool:
    """The second fence, evaluated as the playbook's own expression states it."""
    match = re.search(
        r"^    k3s_window_node_confirmed: >-\n(?P<body>(?:      [^\n]*\n)+)", _text(), re.MULTILINE
    )
    assert match
    expression = " ".join(match["body"].split())
    assert expression == (
        "{{ k3s_window_action | default('') not in k3s_window_node_confirm_actions "
        "or (k3s_window_node | default('') | length > 0 "
        "and k3s_window_node_confirm | default('') == k3s_window_node | default('')) }}"
    ), expression
    assert "k3s_window_node_confirm_actions: [uncordon, evacuate, clear-lost]" in _text()
    return action not in ("uncordon", "evacuate", "clear-lost") or (
        len(node) > 0 and node_confirm == node
    )


def test_uncordon_evacuate_and_clear_lost_need_the_node_confirmed_by_name() -> None:
    for action in ("uncordon", "evacuate", "clear-lost"):
        assert _node_confirmed(action=action, node="node-a", node_confirm="node-a")
        assert not _node_confirmed(action=action, node="node-a", node_confirm="")
        assert not _node_confirmed(action=action, node="node-a", node_confirm="node-b")
        assert not _node_confirmed(action=action, node="", node_confirm="")
    for action in ("pause-arc", "restore-arc", "cordon"):
        assert _node_confirmed(action=action, node="node-a", node_confirm="")
        assert _node_confirmed(action=action, node="", node_confirm="")


def test_an_unconfirmed_node_is_reported_and_nothing_is_read_or_changed() -> None:
    report = _task(
        name=(
            "Report an uncordon, evacuate or clear-lost whose node confirmation "
            "is absent or names another node"
        )
    )
    assert "ansible.builtin.debug:" in report
    assert "not (k3s_window_node_confirmed | bool)" in report
    assert "Nothing was read and nothing was changed." in " ".join(report.split())
    gated = (
        "Read whether the named node is registered in the cluster",
        "Refuse a node action that does not name a pool node or a registered cluster node",
        _POD_TASK,
        "Cordon or uncordon the confirmed node",
        "Report what the action did",
    )
    for name in gated:
        assert "        - k3s_window_node_confirmed | bool\n" in _task(name=name), name
    executing = [
        block
        for block in _text().split("\n    - name: ")[1:]
        if "kubectl" in block and "k3s_window_pod_actions" in block
    ]
    assert len(executing) == 1
    # Cordon is the safe direction: the shared hold task carries the fence, and
    # the fence's own expression lets a cordon through on its action
    # confirmation alone.
    assert _node_confirmed(action="cordon", node="node-a", node_confirm="")
    assert not _node_confirmed(action="uncordon", node="node-a", node_confirm="")
    header = _text().split("\n- name: ", 1)[0]
    assert "-e k3s_window_node_confirm=<node>" in header
    assert "THREE ACTIONS CARRY A SECOND FENCE" in header
    for name in (
        "Pause every runner set's intake, recording its limit first",
        "Restore every recorded runner set's limit exactly",
    ):
        assert "k3s_window_node_confirmed" not in _task(name=name), name


def test_the_pod_read_asks_for_the_fields_the_selection_rests_on() -> None:
    script = _pod_script()
    assert (
        'node_template=\'{.spec.unschedulable}{"|"}'
        '{.status.conditions[?(@.type=="Ready")].status}\''
    ) in script
    assert "'{\" marked:\"}{.metadata.deletionTimestamp}'" in script
    assert '\'{" owners:"}{.metadata.ownerReferences[*].kind}{"\\n"}{end}\'' in script
    assert "--all-namespaces" in script


def _pod_script() -> str:
    task = _task(name=_POD_TASK)
    body = task.split("        cmd: |\n", 1)[1].split("\n      become: true", 1)[0]
    return textwrap.dedent(body)


_KUBECTL_STAND_IN = r"""#!/usr/bin/env bash
# Stand-in kubectl: a node file, a pod table keyed by node, an invocation log.
set -euo pipefail
printf '%s\n' "$*" >> "${STAND_IN_DIR}/log"
case "$1 $2" in
  'get node')
    test -f "${STAND_IN_DIR}/node-$3" || { echo "node $3 not found" >&2; exit 1; }
    cat "${STAND_IN_DIR}/node-$3"
    ;;
  'get nodes')
    if test -e "${STAND_IN_DIR}/nodes-read-fails"; then
      echo 'stand-in kubectl: the nodes read failed' >&2
      exit 1
    fi
    if test -e "${STAND_IN_DIR}/nodes-read-fails-after-a-delete" \
      && test -e "${STAND_IN_DIR}/deleted-once"; then
      echo 'stand-in kubectl: the nodes read failed' >&2
      exit 1
    fi
    cat "${STAND_IN_DIR}/nodes"
    ;;
  'get pods')
    selector=''
    for argument in "$@"; do
      case "${argument}" in spec.nodeName=*) selector="${argument#spec.nodeName=}" ;; esac
    done
    while read -r bound namespace name marked owners phase local; do
      if test -z "${selector}"; then
        # The every-pod read: owner `<Kind>/<pod name minus its last segment>`.
        kind="${owners#owners:}"
        printf '%s %s node:%s phase:%s %s owners:%s local:%s\n' "${namespace}" "${name}" \
          "${bound}" "${phase:-Running}" "${marked}" "${kind:+${kind}/${name%-*},}" "${local}"
      elif test "${bound}" = "${selector}"; then
        printf '%s %s %s %s\n' "${namespace}" "${name}" "${marked}" "${owners}"
      fi
    done < "${STAND_IN_DIR}/pods"
    ;;
  'delete pod')
    : > "${STAND_IN_DIR}/deleted-once"
    if test ! -e "${STAND_IN_DIR}/kubelet-never-confirms"; then
      row="$(grep -E "^[^ ]+ $4 $5 " "${STAND_IN_DIR}/pods" || true)"
      { grep -v -E "^[^ ]+ $4 $5 " "${STAND_IN_DIR}/pods" || true; } > "${STAND_IN_DIR}/pods.next"
      mv "${STAND_IN_DIR}/pods.next" "${STAND_IN_DIR}/pods"
      # A recreating owner brings its pod back on node-b: a listener under the
      # same name, a ReplicaSet's pod under a new one.
      read -r _ _ name _ owners _ <<< "${row}"
      replacement="${name}"
      case "${owners}" in
        owners:ReplicaSet) replacement="${name%-*}-new" ;;
        owners:AutoscalingListener | owners:StatefulSet) ;;
        *) replacement='' ;;
      esac
      if test -n "${replacement}" && test ! -e "${STAND_IN_DIR}/owner-never-recreates"; then
        printf 'node-b %s %s marked: %s %s\n' "$4" "${replacement}" "${owners}" \
          "$(cat "${STAND_IN_DIR}/replacement-phase")" >> "${STAND_IN_DIR}/pods"
      fi
    fi
    ;;
  *)
    printf 'stand-in kubectl: unexpected invocation: %s\n' "$*" >&2
    exit 2
    ;;
esac
"""

# One row per pod: `<node> <namespace> <name> marked:<deletionTimestamp> owners:<kinds>`,
# the node first and then exactly what the play's node-scoped jsonpath renders.
# Two optional columns follow for the every-pod read: the phase (Running when
# absent) and the rendered emptyDir volumes (none when absent).
_PODS = """\
node-a arc-systems overseer-listener marked: owners:AutoscalingListener
node-a kube-system coredns-5d78c marked: owners:ReplicaSet
node-a kube-system svclb-traefik-x marked: owners:DaemonSet
node-a gates gate-job-abcde marked: owners:Job
node-a arc-runners runner-xyz marked: owners:
node-a arc-runners runner-owned marked: owners:EphemeralRunner
node-a factory sandbox-run-1 marked: owners:
node-a factory factory-web-1 marked: owners:ReplicaSet
node-b arc-systems tooling-listener marked: owners:AutoscalingListener
node-b kube-system metrics-server-9 marked: owners:ReplicaSet
"""

_LOST_PODS = """\
node-a arc-systems overseer-listener marked:2026-11-12T21:28:26Z owners:AutoscalingListener
node-a kube-system coredns-5d78c marked: owners:ReplicaSet
node-a kube-system svclb-traefik-x marked:2026-11-12T21:28:26Z owners:DaemonSet
node-a gates gate-job-abcde marked:2026-11-12T21:28:27Z owners:Job
node-a gates gate-job-fresh marked: owners:Job
node-a arc-runners runner-xyz marked:2026-11-12T21:28:28Z owners:
node-a arc-runners runner-new marked: owners:
node-a factory sandbox-run-1 marked:2026-11-12T21:28:29Z owners:
node-b arc-systems tooling-listener marked:2026-11-12T21:28:26Z owners:AutoscalingListener
node-b kube-system metrics-server-9 marked: owners:ReplicaSet
"""


@dataclass(frozen=True, kw_only=True)
class _Outcome:
    returncode: int
    stdout: str
    stderr: str
    log: list[str]
    pods: str

    def deletes(self) -> list[str]:
        return [line for line in self.log if line.startswith("delete ")]


def _run(
    *,
    tmp_path: Path,
    action: str,
    node_state: str | None,
    pods: str,
    dry_run: str = "false",
    wait_seconds: str = "5",
    kubelet_confirms: bool = True,
    owner_recreates: bool = True,
    replacement_phase: str = "Running",
    nodes: str = "node-a|True\nnode-b|True\n",
    nodes_read_fails: str = "",
) -> _Outcome:
    stand_in = tmp_path / "stand-in"
    (stand_in / "bin").mkdir(parents=True)
    kubectl = stand_in / "bin" / "kubectl"
    _ = kubectl.write_text(_KUBECTL_STAND_IN, encoding="utf-8")
    kubectl.chmod(0o755)
    _ = (stand_in / "pods").write_text(pods, encoding="utf-8")
    _ = (stand_in / "log").write_text("", encoding="utf-8")
    if node_state is not None:
        _ = (stand_in / "node-node-a").write_text(node_state, encoding="utf-8")
    if not kubelet_confirms:
        _ = (stand_in / "kubelet-never-confirms").write_text("", encoding="utf-8")
    if not owner_recreates:
        _ = (stand_in / "owner-never-recreates").write_text("", encoding="utf-8")
    _ = (stand_in / "replacement-phase").write_text(replacement_phase, encoding="utf-8")
    _ = (stand_in / "nodes").write_text(nodes, encoding="utf-8")
    if nodes_read_fails:
        _ = (stand_in / nodes_read_fails).write_text("", encoding="utf-8")
    completed = subprocess.run(
        ["/bin/bash", "-c", _pod_script()],
        env={
            "PATH": f"{stand_in / 'bin'}{os.pathsep}/usr/bin{os.pathsep}/bin",
            "STAND_IN_DIR": str(stand_in),
            "K3S_WINDOW_ACTION": action,
            "K3S_WINDOW_NODE": "node-a",
            "K3S_WINDOW_RECREATING_OWNER_KINDS": "AutoscalingListener ReplicaSet StatefulSet",
            "K3S_WINDOW_KEPT_NAMESPACES": "factory factory-mi-homelab",
            "K3S_WINDOW_EVACUATE_WAIT_SECONDS": wait_seconds,
            "K3S_WINDOW_EVACUATE_POLL_SECONDS": "0",
            "K3S_WINDOW_DRY_RUN": dry_run,
        },
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    return _Outcome(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
        log=(stand_in / "log").read_text(encoding="utf-8").splitlines(),
        pods=(stand_in / "pods").read_text(encoding="utf-8"),
    )


def _refused_reading_only_the_node(*, outcome: _Outcome, pods: str) -> bool:
    return (
        outcome.returncode == 1
        and "Nothing was changed." in outcome.stderr
        and outcome.pods == pods
        and outcome.deletes() == []
        and all(line.startswith("get node node-a ") for line in outcome.log)
        and len(outcome.log) == 1
    )


def test_evacuate_refuses_a_node_that_is_not_cordoned(*, tmp_path: Path) -> None:
    for index, state in enumerate(("|True", "false|True")):
        outcome = _run(
            tmp_path=tmp_path / str(index), action="evacuate", node_state=state, pods=_PODS
        )
        assert _refused_reading_only_the_node(outcome=outcome, pods=_PODS), outcome
        assert "it is not cordoned" in outcome.stderr
        assert "Run `cordon` first." in outcome.stderr


def test_evacuate_refuses_a_node_that_is_not_ready(*, tmp_path: Path) -> None:
    for index, state in enumerate(("true|False", "true|Unknown", "true|")):
        outcome = _run(
            tmp_path=tmp_path / str(index), action="evacuate", node_state=state, pods=_PODS
        )
        assert _refused_reading_only_the_node(outcome=outcome, pods=_PODS), outcome
        assert "no kubelet can complete a graceful delete" in outcome.stderr


def test_both_actions_refuse_a_node_that_cannot_be_read(*, tmp_path: Path) -> None:
    for action in ("evacuate", "clear-lost"):
        outcome = _run(tmp_path=tmp_path / action, action=action, node_state=None, pods=_PODS)
        assert _refused_reading_only_the_node(outcome=outcome, pods=_PODS), outcome
        assert "the node could not be read." in outcome.stderr


def test_the_pod_task_refuses_an_action_it_does_not_know(*, tmp_path: Path) -> None:
    outcome = _run(tmp_path=tmp_path, action="cordon", node_state="true|True", pods=_PODS)
    assert _refused_reading_only_the_node(outcome=outcome, pods=_PODS), outcome


def test_evacuate_deletes_only_recreated_pods_on_the_named_node(*, tmp_path: Path) -> None:
    outcome = _run(tmp_path=tmp_path, action="evacuate", node_state="true|True", pods=_PODS)
    assert outcome.returncode == 0, outcome
    assert outcome.deletes() == [
        "delete pod --namespace arc-systems overseer-listener --ignore-not-found --wait=false",
        "delete pod --namespace kube-system coredns-5d78c --ignore-not-found --wait=false",
    ]
    # Every `get pods` is the node-scoped selection read or the every-pod read
    # the post-condition rests on; neither names another node.
    pod_reads = [line for line in outcome.log if line.startswith("get pods")]
    assert any("spec.nodeName=node-a" in line for line in pod_reads)
    assert all("--all-namespaces" in line for line in pod_reads)
    assert not any("spec.nodeName=node-b" in line for line in pod_reads)
    lines = outcome.stdout.splitlines()
    assert (
        "deleted arc-systems/overseer-listener "
        "(owners: AutoscalingListener; not marked for deletion)"
    ) in lines
    assert "deleted kube-system/coredns-5d78c (owners: ReplicaSet; not marked for deletion)" in (
        lines
    )
    for left in (
        "left kube-system/svclb-traefik-x: a DaemonSet owns it, so it belongs to the node",
        "left gates/gate-job-abcde: its owner (Job) does not recreate it elsewhere",
        "left arc-runners/runner-xyz: no controller owns it, so nothing would recreate it",
        "left arc-runners/runner-owned: its owner (EphemeralRunner) does not recreate it elsewhere",
        f"left factory/sandbox-run-1: {_FACTORY_REASON}",
        f"left factory/factory-web-1: {_FACTORY_REASON}",
    ):
        assert left in lines, left
    assert lines[-1] == (
        "evacuated: no deleted pod is still bound to node node-a, "
        "and each owner has its pods Running on another Ready node"
    )
    for replaced in (
        "replaced arc-systems AutoscalingListener/overseer: "
        "1 Running on another Ready node (0 before)",
        "replaced kube-system ReplicaSet/coredns: 1 Running on another Ready node (0 before)",
    ):
        assert replaced in lines, replaced
    assert "node-b arc-systems tooling-listener" in outcome.pods
    assert "node-b kube-system metrics-server-9" in outcome.pods
    assert "node-b arc-systems overseer-listener" in outcome.pods
    assert "node-b kube-system coredns-new" in outcome.pods
    assert not any(line.startswith("node-a arc-systems ") for line in outcome.pods.splitlines())
    assert len(outcome.pods.splitlines()) == len(_PODS.splitlines())


def test_evacuate_never_force_deletes(*, tmp_path: Path) -> None:
    outcome = _run(tmp_path=tmp_path, action="evacuate", node_state="true|True", pods=_PODS)
    assert outcome.deletes()
    assert not any("--force" in line or "--grace-period" in line for line in outcome.log)


def test_a_second_evacuate_finds_nothing_and_changes_nothing(*, tmp_path: Path) -> None:
    first = _run(tmp_path=tmp_path / "first", action="evacuate", node_state="true|True", pods=_PODS)
    second = _run(
        tmp_path=tmp_path / "second", action="evacuate", node_state="true|True", pods=first.pods
    )
    assert second.returncode == 0, second
    assert second.deletes() == []
    assert second.pods == first.pods
    assert second.stdout.splitlines()[-1] == "nothing to evacuate on node node-a"
    assert re.search(r"(?m)^(deleted|cleared) ", second.stdout) is None


def test_evacuate_fails_when_a_deleted_pod_is_still_bound_after_the_wait(*, tmp_path: Path) -> None:
    outcome = _run(
        tmp_path=tmp_path,
        action="evacuate",
        node_state="true|True",
        pods=_PODS,
        wait_seconds="0",
        kubelet_confirms=False,
    )
    assert outcome.returncode == 1, outcome
    assert "FAILED its post-condition after 0s." in outcome.stderr
    assert (
        "Still bound to the node: arc-systems/overseer-listener kube-system/coredns-5d78c."
        in outcome.stderr
    )
    assert "evacuated:" not in outcome.stdout


_LACKING = (
    "Owners without their replacement Running on another Ready node (replaced/deleted): "
    "arc-systems/AutoscalingListener/overseer(0/1) kube-system/ReplicaSet/coredns(0/1)."
)


def test_evacuate_fails_naming_each_owner_whose_pod_did_not_come_back(*, tmp_path: Path) -> None:
    outcome = _run(
        tmp_path=tmp_path,
        action="evacuate",
        node_state="true|True",
        pods=_PODS,
        wait_seconds="0",
        owner_recreates=False,
    )
    assert outcome.returncode == 1, outcome
    assert "Still bound to the node: none." in outcome.stderr
    assert _LACKING in outcome.stderr
    assert "evacuated:" not in outcome.stdout


def test_a_replacement_that_is_not_running_does_not_meet_the_post_condition(
    *, tmp_path: Path
) -> None:
    outcome = _run(
        tmp_path=tmp_path,
        action="evacuate",
        node_state="true|True",
        pods=_PODS,
        wait_seconds="0",
        replacement_phase="Pending",
    )
    assert outcome.returncode == 1, outcome
    assert _LACKING in outcome.stderr
    assert "evacuated:" not in outcome.stdout


def test_a_replacement_on_a_node_that_is_not_ready_does_not_meet_the_post_condition(
    *, tmp_path: Path
) -> None:
    outcome = _run(
        tmp_path=tmp_path,
        action="evacuate",
        node_state="true|True",
        pods=_PODS,
        wait_seconds="0",
        nodes="node-a|True\nnode-b|Unknown\nnode-c|True\n",
    )
    assert outcome.returncode == 1, outcome
    assert outcome.deletes() != []
    assert _LACKING in outcome.stderr


def test_a_pod_already_running_elsewhere_does_not_count_as_the_replacement(
    *, tmp_path: Path
) -> None:
    pods = _PODS + "node-b kube-system coredns-other marked: owners:ReplicaSet\n"
    failed = _run(
        tmp_path=tmp_path / "failed",
        action="evacuate",
        node_state="true|True",
        pods=pods,
        wait_seconds="0",
        owner_recreates=False,
    )
    assert failed.returncode == 1, failed
    assert "kube-system/ReplicaSet/coredns(0/1)" in failed.stderr
    passed = _run(
        tmp_path=tmp_path / "passed", action="evacuate", node_state="true|True", pods=pods
    )
    assert passed.returncode == 0, passed
    assert (
        "replaced kube-system ReplicaSet/coredns: 2 Running on another Ready node (1 before)"
        in passed.stdout.splitlines()
    )


def test_evacuate_names_the_emptydir_data_a_delete_loses(*, tmp_path: Path) -> None:
    pods = _PODS.replace(
        "node-a kube-system coredns-5d78c marked: owners:ReplicaSet\n",
        "node-a kube-system coredns-5d78c marked: owners:ReplicaSet Running {}\n",
    )
    assert pods != _PODS
    named = (
        "kube-system/coredns-5d78c (owners: ReplicaSet; not marked for deletion; "
        "its emptyDir volume data is lost with it)"
    )
    for index, dry_run in enumerate(("false", "true")):
        outcome = _run(
            tmp_path=tmp_path / str(index),
            action="evacuate",
            node_state="true|True",
            pods=pods,
            dry_run=dry_run,
        )
        assert outcome.returncode == 0, outcome
        verb = "deleted" if dry_run == "false" else "would evacuate"
        lines = outcome.stdout.splitlines()
        assert f"{verb} {named}" in lines, outcome
        assert not any("overseer-listener" in line and "emptyDir" in line for line in lines)


def test_clear_lost_reads_no_owner_table_and_no_node_list(*, tmp_path: Path) -> None:
    outcome = _run(
        tmp_path=tmp_path, action="clear-lost", node_state="true|Unknown", pods=_LOST_PODS
    )
    assert outcome.returncode == 0, outcome
    assert not any(line.startswith("get nodes") for line in outcome.log)
    assert all("spec.nodeName=node-a" in line for line in outcome.log if "get pods" in line)


def test_the_header_states_the_post_condition_the_budget_bypass_and_the_gate_job_rule() -> None:
    header = " ".join(_text().split("\n- name: ", 1)[0].replace("#", " ").split())
    for stated in (
        "HAS A BOUNDED POST-CONDITION",
        "Running on another Ready node",
        "no PodDisruptionBudget is consulted",
        "the contents of an emptyDir volume are lost with the pod",
        "`clear-lost` force-deletes a Kueue gate Job's pod (namespace `gates`) once the API "
        "has marked it for deletion",
    ):
        assert stated in header, stated


def test_clear_lost_refuses_a_ready_node(*, tmp_path: Path) -> None:
    for index, state in enumerate(("true|True", "|True", "true|")):
        outcome = _run(
            tmp_path=tmp_path / str(index), action="clear-lost", node_state=state, pods=_LOST_PODS
        )
        assert _refused_reading_only_the_node(outcome=outcome, pods=_LOST_PODS), outcome
        assert "not False or Unknown" in outcome.stderr
        assert "A force delete on a live kubelet can leave containers running." in outcome.stderr


def test_clear_lost_force_deletes_only_the_named_nodes_marked_or_recreated_pods(
    *, tmp_path: Path
) -> None:
    force = "--ignore-not-found --wait=false --grace-period=0 --force"
    for index, state in enumerate(("true|Unknown", "|False")):
        outcome = _run(
            tmp_path=tmp_path / str(index), action="clear-lost", node_state=state, pods=_LOST_PODS
        )
        assert outcome.returncode == 0, outcome
        assert outcome.deletes() == [
            f"delete pod --namespace arc-systems overseer-listener {force}",
            f"delete pod --namespace kube-system coredns-5d78c {force}",
            f"delete pod --namespace gates gate-job-abcde {force}",
            f"delete pod --namespace arc-runners runner-xyz {force}",
        ]
        assert all("spec.nodeName=node-a" in line for line in outcome.log if "get pods" in line)
        assert [line for line in outcome.log if "get pods" in line] != []
        lines = outcome.stdout.splitlines()
        assert (
            "cleared arc-systems/overseer-listener "
            "(owners: AutoscalingListener; marked for deletion at 2026-11-12T21:28:26Z)"
        ) in lines
        assert (
            "cleared arc-runners/runner-xyz "
            "(owners: none; marked for deletion at 2026-11-12T21:28:28Z)"
        ) in lines
        assert (
            "cleared kube-system/coredns-5d78c (owners: ReplicaSet; not marked for deletion)"
        ) in lines
        for left in (
            "left kube-system/svclb-traefik-x: a DaemonSet owns it, so it belongs to the node",
            "left gates/gate-job-fresh: its owner (Job) does not recreate it elsewhere",
            "left arc-runners/runner-new: no controller owns it, so nothing would recreate it",
            f"left factory/sandbox-run-1: {_FACTORY_REASON}",
        ):
            assert left in lines, left
        assert "evacuated:" not in outcome.stdout
        assert "node-a kube-system svclb-traefik-x" in outcome.pods
        assert "node-b arc-systems tooling-listener" in outcome.pods
        assert "node-b kube-system metrics-server-9" in outcome.pods
        # Four cleared; the stand-in's two recreating owners bring theirs back on node-b.
        assert "node-b arc-systems overseer-listener marked: " in outcome.pods
        assert "node-b kube-system coredns-new marked: " in outcome.pods
        assert len(outcome.pods.splitlines()) == len(_LOST_PODS.splitlines()) - 4 + 2


def test_a_second_clear_lost_finds_nothing_and_changes_nothing(*, tmp_path: Path) -> None:
    first = _run(
        tmp_path=tmp_path / "first", action="clear-lost", node_state="true|Unknown", pods=_LOST_PODS
    )
    second = _run(
        tmp_path=tmp_path / "second",
        action="clear-lost",
        node_state="true|Unknown",
        pods=first.pods,
    )
    assert second.returncode == 0, second
    assert second.deletes() == []
    assert second.pods == first.pods
    assert second.stdout.splitlines()[-1] == "nothing to clear-lost on node node-a"


def test_a_check_run_reports_what_it_would_do_and_deletes_nothing(*, tmp_path: Path) -> None:
    cases = (
        ("evacuate", "true|True", _PODS, "true", "would evacuate arc-systems/overseer-listener"),
        ("clear-lost", "|Unknown", _LOST_PODS, "true", "would clear-lost gates/gate-job-abcde"),
        ("clear-lost", "|Unknown", _LOST_PODS, "", "would clear-lost arc-runners/runner-xyz"),
    )
    for index, (action, state, pods, dry_run, expected) in enumerate(cases):
        outcome = _run(
            tmp_path=tmp_path / str(index),
            action=action,
            node_state=state,
            pods=pods,
            dry_run=dry_run,
        )
        assert outcome.returncode == 0, outcome
        assert outcome.deletes() == []
        assert outcome.pods == pods
        assert any(line.startswith(expected) for line in outcome.stdout.splitlines()), outcome
        assert re.search(r"(?m)^(deleted|cleared) ", outcome.stdout) is None


_ALREADY_ELSEWHERE = _PODS + "node-b kube-system coredns-other marked: owners:ReplicaSet\n"


def test_a_nodes_read_that_fails_before_the_deletes_refuses_and_deletes_nothing(
    *, tmp_path: Path
) -> None:
    outcome = _run(
        tmp_path=tmp_path,
        action="evacuate",
        node_state="true|True",
        pods=_ALREADY_ELSEWHERE,
        owner_recreates=False,
        nodes_read_fails="nodes-read-fails",
    )
    assert outcome.returncode == 1, outcome
    assert "the cluster's nodes could not be read. Nothing was changed." in outcome.stderr
    assert outcome.deletes() == []
    assert outcome.pods == _ALREADY_ELSEWHERE
    assert "evacuated:" not in outcome.stdout


def test_a_nodes_read_that_fails_after_the_deletes_fails_the_post_condition(
    *, tmp_path: Path
) -> None:
    outcome = _run(
        tmp_path=tmp_path,
        action="evacuate",
        node_state="true|True",
        pods=_ALREADY_ELSEWHERE,
        nodes_read_fails="nodes-read-fails-after-a-delete",
    )
    assert outcome.returncode == 1, outcome
    assert outcome.deletes() != []
    assert "the cluster's node list could not be read back after the deletes" in outcome.stderr
    assert "the post-condition is NOT established" in outcome.stderr
    assert "evacuated:" not in outcome.stdout
    assert "replaced " not in outcome.stdout


def test_evacuate_refuses_when_no_other_node_is_ready(*, tmp_path: Path) -> None:
    outcome = _run(
        tmp_path=tmp_path,
        action="evacuate",
        node_state="true|True",
        pods=_PODS,
        nodes="node-a|True\nnode-b|Unknown\n",
    )
    assert outcome.returncode == 1, outcome
    assert "no other node is Ready" in outcome.stderr
    assert "Nothing was changed." in outcome.stderr
    assert outcome.deletes() == []
    assert outcome.pods == _PODS


_STATEFUL = _PODS + "node-a monitoring store-0 marked: owners:StatefulSet\n"


def test_a_statefulset_pod_must_come_back_under_its_name_on_another_ready_node(
    *, tmp_path: Path
) -> None:
    passed = _run(
        tmp_path=tmp_path / "passed", action="evacuate", node_state="true|True", pods=_STATEFUL
    )
    assert passed.returncode == 0, passed
    assert "delete pod --namespace monitoring store-0 --ignore-not-found --wait=false" in (
        passed.deletes()
    )
    assert (
        "replaced monitoring StatefulSet/store: 1 Running on another Ready node (0 before)"
        in passed.stdout.splitlines()
    )
    assert "node-b monitoring store-0 marked: owners:StatefulSet Running" in passed.pods
    assert "node-a monitoring store-0" not in passed.pods
    pending = _run(
        tmp_path=tmp_path / "pending",
        action="evacuate",
        node_state="true|True",
        pods=_STATEFUL,
        wait_seconds="0",
        replacement_phase="Pending",
    )
    assert pending.returncode == 1, pending
    assert "monitoring/StatefulSet/store(0/1)" in pending.stderr
