"""The fail-open drill script, run for real against a faked kubectl and systemctl.

livespec-dev-tooling-mtvxde. The claims are about decisions: when the drill refuses,
what counts as proof, and that the scheduler comes back on every exit. So the script
runs, with a fake `kubectl` serving one canned pod list per poll. No cluster is reached.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import yaml

__all__: list[str] = []

_Json = dict[str, Any]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = (
    _REPO_ROOT
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "runner-scheduler"
    / "drill-runner-scheduler-fail-open.sh"
)
_PLAY = _REPO_ROOT / "ansible" / "runner-scheduler-fail-open-drill.yml"
_SCHEDULER = "ci-runner-scheduler"
_RESTORE = "-n kube-system scale deployment ci-runner-scheduler --replicas=2"
_ZERO = "-n kube-system scale deployment ci-runner-scheduler --replicas=0"

_FAKE_KUBECTL = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DIR/argv.log"
case "$*" in
  "-n kube-system get deployment ci-runner-scheduler -o json") cat "$FAKE_DIR/deployment.json" ;;
  "-n arc-runners get pods -o json")
    n="$(cat "$FAKE_DIR/poll" 2>/dev/null || echo 0)"; n=$((n + 1)); echo "$n" >"$FAKE_DIR/poll"
    if [ -f "$FAKE_DIR/pods-$n.json" ]; then cat "$FAKE_DIR/pods-$n.json"
    else cat "$FAKE_DIR/pods-last.json"; fi ;;
  "-n arc-runners get autoscalingrunnerset livespec-dev-tooling-k3s "*) cat "$FAKE_DIR/template" ;;
  "-n kube-system scale deployment ci-runner-scheduler --replicas="*)
    if [ -f "$FAKE_DIR/reject-restore" ] && [ "${*##*=}" != 0 ]; then
      echo 'Error from server: timeout' >&2; exit 1
    fi ;;
  "-n kube-system rollout status "*) ;;
  *) echo "fake kubectl: unexpected argv: $*" >&2; exit 1 ;;
esac
"""

_FAKE_SYSTEMCTL = r"""#!/usr/bin/env bash
cat "$FAKE_DIR/timer"
"""


def _pod(
    name: str, uid: str, *, scheduler: str, phase: str = "Pending", node: str | None = None
) -> _Json:
    spec: _Json = {"schedulerName": scheduler}
    if node:
        spec["nodeName"] = node
    return {"metadata": {"name": name, "uid": uid}, "spec": spec, "status": {"phase": phase}}


_STRANDED = _pod("r1", "old", scheduler=_SCHEDULER)
_REPLACED = _pod("r1", "new", scheduler="default-scheduler")
_RUNNING = _pod("r1", "new", scheduler="default-scheduler", phase="Running", node="poweredge")


def _set_up(
    tmp_path: Path,
    polls: list[list[_Json]],
    *,
    ready: int = 2,
    timer: str = "active",
    template: str = _SCHEDULER,
) -> None:
    (tmp_path / "deployment.json").write_text(
        json.dumps({"spec": {"replicas": 2}, "status": {"readyReplicas": ready}}), encoding="utf-8"
    )
    (tmp_path / "timer").write_text(f"{timer}\n", encoding="utf-8")
    (tmp_path / "template").write_text(template, encoding="utf-8")
    for index, pods in enumerate(polls, start=1):
        (tmp_path / f"pods-{index}.json").write_text(json.dumps({"items": pods}), encoding="utf-8")
    (tmp_path / "pods-last.json").write_text(json.dumps({"items": polls[-1]}), encoding="utf-8")


def _run(
    tmp_path: Path, *, min_polls: int = 1, max_polls: int = 4
) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("kubectl", _FAKE_KUBECTL), ("systemctl", _FAKE_SYSTEMCTL)):
        fake = bin_dir / name
        fake.write_text(body, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return subprocess.run(
        ["bash", str(_SCRIPT)],
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_DIR": str(tmp_path),
            "RUNNER_SCHEDULER_DRILL_INTERVAL_SECONDS": "0",
            "RUNNER_SCHEDULER_DRILL_MIN_POLLS": str(min_polls),
            "RUNNER_SCHEDULER_DRILL_MAX_POLLS": str(max_polls),
        },
        capture_output=True,
        text=True,
        check=False,
    )


def _argv(tmp_path: Path) -> list[str]:
    return (tmp_path / "argv.log").read_text(encoding="utf-8").splitlines()


def test_a_stranded_pod_replaced_and_running_proves_the_rescue_and_restores(
    tmp_path: Path,
) -> None:
    _set_up(tmp_path, [[_STRANDED], [_REPLACED], [_RUNNING]])
    run = _run(tmp_path, min_polls=3)
    assert run.returncode == 0, run.stderr
    assert "STRANDED r1" in run.stdout
    assert "REPLACED r1 old-uid=old new-uid=new" in run.stdout
    assert "PROVEN r1 node=poweredge" in run.stdout
    argv = _argv(tmp_path)
    assert argv.index(_ZERO) < argv.index(_RESTORE)


def test_the_hold_continues_to_the_minimum_after_the_first_rescue(tmp_path: Path) -> None:
    _set_up(tmp_path, [[_STRANDED], [_RUNNING]])
    run = _run(tmp_path, min_polls=4, max_polls=9)
    assert run.returncode == 0, run.stderr
    assert "polls=4 " in run.stdout


def test_a_replacement_not_yet_running_is_not_proof(tmp_path: Path) -> None:
    _set_up(tmp_path, [[_STRANDED], [_REPLACED]])
    run = _run(tmp_path)
    assert run.returncode == 3, run.stdout
    assert "NO EVIDENCE" in run.stderr
    assert _RESTORE in _argv(tmp_path)


def test_a_pod_that_never_stranded_is_not_proof(tmp_path: Path) -> None:
    _set_up(tmp_path, [[_RUNNING]])
    run = _run(tmp_path)
    assert run.returncode == 3
    assert _RESTORE in _argv(tmp_path)


def test_a_same_uid_pod_naming_the_default_scheduler_is_not_a_replacement(tmp_path: Path) -> None:
    same = _pod("r1", "old", scheduler="default-scheduler", phase="Running", node="poweredge")
    _set_up(tmp_path, [[_STRANDED], [same]])
    run = _run(tmp_path)
    assert run.returncode == 3


def test_a_stopped_reconciler_timer_refuses_before_any_write(tmp_path: Path) -> None:
    _set_up(tmp_path, [[_STRANDED]], timer="inactive")
    run = _run(tmp_path)
    assert run.returncode == 1
    assert "refuses" in run.stderr
    assert not (tmp_path / "argv.log").exists()


def test_a_scheduler_already_down_refuses_and_does_not_scale(tmp_path: Path) -> None:
    _set_up(tmp_path, [[_STRANDED]], ready=0)
    run = _run(tmp_path)
    assert run.returncode == 1
    assert not any(" scale " in line for line in _argv(tmp_path))


def test_a_changed_scale_set_template_fails_the_drill_and_still_restores(tmp_path: Path) -> None:
    _set_up(tmp_path, [[_STRANDED], [_RUNNING]], template="default-scheduler")
    run = _run(tmp_path, min_polls=2)
    assert run.returncode == 1
    assert "must leave it unchanged" in run.stderr
    assert _RESTORE in _argv(tmp_path)


def test_a_failed_restore_fails_the_drill_loudly(tmp_path: Path) -> None:
    _set_up(tmp_path, [[_STRANDED], [_RUNNING]])
    (tmp_path / "reject-restore").write_text("", encoding="utf-8")
    run = _run(tmp_path, min_polls=2)
    assert run.returncode == 1
    assert "FAILED TO RESTORE" in run.stderr


def test_the_play_only_acts_for_the_confirmed_server_and_never_under_check() -> None:
    play = yaml.safe_load(_PLAY.read_text(encoding="utf-8"))[0]
    assert (
        "cluster_role | default('') == 'server'"
        in (play["vars"]["runner_scheduler_fail_open_drill_named"])
    )
    block = next(task for task in play["tasks"] if "block" in task)
    assert block["when"] == [
        "runner_scheduler_fail_open_drill_named | bool",
        "not ansible_check_mode",
    ]
