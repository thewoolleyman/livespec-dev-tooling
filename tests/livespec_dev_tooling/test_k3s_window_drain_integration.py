"""Integration coverage for the committed k3s window-drain playbook.

This test drives the real play through the same pinned ``ansible-core`` as the
sanctioned apply recipe.  The stand-in ``kubectl`` owns the pod table: deleting
the listener removes it from the cordoned node and recreates it on the other
Ready node, so the play's post-condition is read from state the delete changed.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _ROOT / "justfile"
_PLAYBOOK = _ROOT / "ansible" / "k3s-window-drain.yml"
_COVERAGE = _ROOT / "tests" / "heading-coverage.json"
_SERVER = "window-drain-server"
_NODE = "window-drain-node-a"
_OTHER_NODE = "window-drain-node-b"
_LISTENER = "listener-a"
_HEADING = (
    "## Scenario: a planned power-off evacuation moves a cordoned node's listener pods "
    "and leaves its other pods"
)
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

_SUDO = """#!/bin/sh
while test $# -gt 0; do
  case "$1" in
    -u) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
exec "$@"
"""

_KUBECTL = r"""#!/bin/sh
set -eu
printf 'kubectl %s\n' "$*" >> "$WINDOW_DRAIN_LOG"
case "$1 $2" in
  'get node')
    case "$*" in
      *'--output=name'*) printf 'node/%s\n' "$3" ;;
      *) printf '%s' "${WINDOW_DRAIN_NODE_STATE:-true|True}" ;;
    esac
    ;;
  'get nodes') printf '%s|True|true|\n%s|True||true\n' "$WINDOW_DRAIN_NODE" "$WINDOW_DRAIN_OTHER_NODE" ;;
  'get pods')
    selector=''
    for argument in "$@"; do
      case "$argument" in spec.nodeName=*) selector="${argument#spec.nodeName=}" ;; esac
    done
    while read -r node namespace name marked owners phase; do
      test -n "$node" || continue
      if test -n "$selector"; then
        test "$node" = "$selector" || continue
        printf '%s %s %s %s\n' "$namespace" "$name" "$marked" "$owners"
      else
        owner="${owners#owners:}"
        owner_name="${name%-*}"
        printf '%s %s node:%s phase:%s %s owners:%s local:\n' \
          "$namespace" "$name" "$node" "$phase" "$marked" \
          "${owner:+${owner}/${owner_name},}"
      fi
    done < "$WINDOW_DRAIN_PODS"
    ;;
  'delete pod')
    namespace="$4"
    name="$5"
    grep -v -F " $namespace $name " "$WINDOW_DRAIN_PODS" > "$WINDOW_DRAIN_PODS.next" || true
    mv "$WINDOW_DRAIN_PODS.next" "$WINDOW_DRAIN_PODS"
    if test "$namespace/$name" = "arc-systems/$WINDOW_DRAIN_LISTENER"; then
      printf '%s arc-systems %s marked: owners:AutoscalingListener Running\n' \
        "$WINDOW_DRAIN_OTHER_NODE" "$WINDOW_DRAIN_LISTENER" >> "$WINDOW_DRAIN_PODS"
    fi
    ;;
  *) printf 'unexpected kubectl invocation: %s\n' "$*" >&2; exit 1 ;;
esac
"""


def _ansible_core_pin() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, "justfile must define the sanctioned ansible-apply recipe"
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, "ansible-apply must pin ansible-core"
    return pin[0]


def _write_executable(*, path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


_EVACUATE_PODS = (
    "{node} arc-systems {listener} marked: owners:AutoscalingListener Running\n"
    "{node} kube-system node-daemon marked: owners:DaemonSet Running\n"
    "{node} gates gate-job marked: owners:Job Running\n"
    "{node} arc-runners runner marked: owners: Running\n"
    "{node} factory sandbox marked: owners:ReplicaSet Running\n"
)
_STUCK_LISTENER_PODS = (
    "{node} arc-systems {listener} marked:2026-11-18T00:00:00Z "
    "owners:AutoscalingListener Terminating\n"
)


def _run_play(
    *,
    root: Path,
    action: str,
    pods_text: str,
    node_state: str,
    node_confirm: str | None,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    _write_executable(path=bin_dir / "sudo", content=_SUDO)
    _write_executable(path=bin_dir / "kubectl", content=_KUBECTL)
    pods = root / "pods"
    pods.write_text(pods_text.format(node=_NODE, listener=_LISTENER), encoding="utf-8")
    inventory = root / "inventory.yml"
    inventory.write_text(
        "all:\n"
        "  children:\n"
        "    ci_pool:\n"
        "      hosts:\n"
        f"        {_SERVER}:\n"
        "          ansible_connection: local\n"
        "          cluster_role: server\n",
        encoding="utf-8",
    )
    log = root / "kubectl.log"
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "WINDOW_DRAIN_LOG": str(log),
            "WINDOW_DRAIN_PODS": str(pods),
            "WINDOW_DRAIN_NODE": _NODE,
            "WINDOW_DRAIN_NODE_STATE": node_state,
            "WINDOW_DRAIN_OTHER_NODE": _OTHER_NODE,
            "WINDOW_DRAIN_LISTENER": _LISTENER,
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
        }
    )
    result = subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(inventory),
            "-e",
            f"k3s_window_action={action}",
            "-e",
            f"k3s_window_confirm={action}",
            "-e",
            f"k3s_window_node={_NODE}",
            *(["-e", f"k3s_window_node_confirm={node_confirm}"] if node_confirm else []),
            "-e",
            "k3s_window_evacuate_wait_seconds=0",
            "-e",
            "k3s_window_evacuate_poll_seconds=0",
            str(_PLAYBOOK),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    return result, pods, log


def _log_lines(*, log: Path) -> list[str]:
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def _assert_mapped(*, heading: str, test_name: str) -> None:
    coverage = json.loads(_COVERAGE.read_text(encoding="utf-8"))
    [entry] = [item for item in coverage if item["heading"] == heading]
    assert (
        entry["test"] == f"tests.livespec_dev_tooling.test_k3s_window_drain_integration.{test_name}"
    )


def test_evacuation_moves_listener_pods_and_leaves_other_pods(*, tmp_path: Path) -> None:
    result, pods, log = _run_play(
        root=tmp_path,
        action="evacuate",
        pods_text=_EVACUATE_PODS,
        node_state="true|True",
        node_confirm=_NODE,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert (
        log.read_text(encoding="utf-8")
        .splitlines()
        .count(
            f"kubectl delete pod --namespace arc-systems {_LISTENER} --ignore-not-found --wait=false"
        )
        == 1
    )
    state = pods.read_text(encoding="utf-8")
    assert f"{_OTHER_NODE} arc-systems {_LISTENER} " in state
    for bound in (
        f"{_NODE} kube-system node-daemon ",
        f"{_NODE} gates gate-job ",
        f"{_NODE} arc-runners runner ",
        f"{_NODE} factory sandbox ",
    ):
        assert bound in state
    for report in (
        "left kube-system/node-daemon: a DaemonSet owns it, so it belongs to the node",
        "left gates/gate-job: its owner (Job) does not recreate it elsewhere",
        "left arc-runners/runner: no controller owns it, so nothing would recreate it",
        "left factory/sandbox: a factory namespace pod follows the dispatcher's cancel-and-re-dispatch route",
    ):
        assert report in output

    coverage = json.loads(_COVERAGE.read_text(encoding="utf-8"))
    [entry] = [item for item in coverage if item["heading"] == _HEADING]
    assert entry["test"] == (
        "tests.livespec_dev_tooling.test_k3s_window_drain_integration."
        "test_evacuation_moves_listener_pods_and_leaves_other_pods"
    )


def test_clear_lost_force_deletes_stuck_listener_pods_and_reports_each(*, tmp_path: Path) -> None:
    result, pods, log = _run_play(
        root=tmp_path,
        action="clear-lost",
        pods_text=_STUCK_LISTENER_PODS,
        node_state="false|False",
        node_confirm=_NODE,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert (
        f"kubectl delete pod --namespace arc-systems {_LISTENER} "
        "--ignore-not-found --wait=false --grace-period=0 --force"
    ) in _log_lines(log=log)
    assert f"cleared arc-systems/{_LISTENER} " in output
    assert f"{_NODE} arc-systems {_LISTENER} " not in pods.read_text(encoding="utf-8")
    _assert_mapped(
        heading=(
            "## Scenario: clearing a lost node force-deletes its stuck listener pods "
            "and reports each pod it cleared"
        ),
        test_name="test_clear_lost_force_deletes_stuck_listener_pods_and_reports_each",
    )


def test_clear_lost_is_refused_for_a_node_that_reads_ready(*, tmp_path: Path) -> None:
    result, pods, log = _run_play(
        root=tmp_path,
        action="clear-lost",
        pods_text=_STUCK_LISTENER_PODS,
        node_state="false|True",
        node_confirm=_NODE,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "its Ready condition is 'True', not False or Unknown" in output
    assert "Nothing was changed." in output
    assert not [line for line in _log_lines(log=log) if line.startswith("kubectl delete")]
    assert f"{_NODE} arc-systems {_LISTENER} " in pods.read_text(encoding="utf-8")
    _assert_mapped(
        heading="## Scenario: clearing a lost node is refused for a node that reads Ready",
        test_name="test_clear_lost_is_refused_for_a_node_that_reads_ready",
    )


@pytest.mark.parametrize("node_confirm", [None, _OTHER_NODE])
def test_uncordon_with_absent_or_other_node_confirmation_changes_nothing(
    *, tmp_path: Path, node_confirm: str | None
) -> None:
    result, _pods, log = _run_play(
        root=tmp_path,
        action="uncordon",
        pods_text=_EVACUATE_PODS,
        node_state="true|True",
        node_confirm=node_confirm,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "Nothing was read and nothing was changed." in output
    assert _log_lines(log=log) == []
    _assert_mapped(
        heading=(
            "## Scenario: an uncordon whose node confirmation is absent or names another node "
            "changes nothing"
        ),
        test_name="test_uncordon_with_absent_or_other_node_confirmation_changes_nothing",
    )
