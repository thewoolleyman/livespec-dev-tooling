"""The runner scheduler's fail-open reconciler, run for real against a faked kubectl.

livespec-dev-tooling-mtvxde: a runner pod that names `ci-runner-scheduler` while it
has no ready replica is never bound, so the reconciler hands that pod to the default
scheduler. A pod's schedulerName is immutable, so the hand-over patches the
EphemeralRunner that ARC recreates the pod from, then deletes the pod.

Every claim here is about a DECISION, which reading a shell script cannot establish,
so the script runs with a fake `kubectl` first on PATH. The fake serves canned JSON
from a scratch directory and logs every argv. No cluster is reached.
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
_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "runner-scheduler"
_SCRIPT = _DIR / "reconcile-runner-scheduler-fail-open.sh"
_PLAY = _REPO_ROOT / "ansible" / "ci-pool.yml"
_TRIGGER = (
    _REPO_ROOT / "ci-runner" / "observability" / "triggers" / "k8s-controller-zero-available.json"
)
_SCHEDULER = "ci-runner-scheduler"
_NOW = 1_800_000_000
_GRACE = 60

_FAKE_KUBECTL = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DIR/argv.log"
case "$*" in
  "-n kube-system get deployment ci-runner-scheduler -o json")
    [ -f "$FAKE_DIR/deployment.err" ] && { cat "$FAKE_DIR/deployment.err" >&2; exit 1; }
    cat "$FAKE_DIR/deployment.json" ;;
  "-n arc-runners get pods -o json")
    [ -f "$FAKE_DIR/pods.json" ] || { echo 'Error from server: connection refused' >&2; exit 1; }
    cat "$FAKE_DIR/pods.json" ;;
  "-n arc-runners patch ephemeralrunner "*)
    case "$*" in *" $(cat "$FAKE_DIR/reject-patch" 2>/dev/null) "*)
      echo 'Error from server: conflict' >&2; exit 1 ;;
    esac ;;
  "-n arc-runners delete pod "*)
    if [ -f "$FAKE_DIR/reject-delete" ]; then echo 'Error from server: timeout' >&2; exit 1; fi
    ;;
  *) echo "fake kubectl: unexpected argv: $*" >&2; exit 1 ;;
esac
"""


def _pod(
    name: str,
    *,
    scheduler: str = _SCHEDULER,
    phase: str = "Pending",
    node: str | None = None,
    gated: bool = False,
) -> _Json:
    spec: _Json = {"schedulerName": scheduler}
    if node:
        spec["nodeName"] = node
    if gated:
        spec["schedulingGates"] = [{"name": "kueue.x-k8s.io/admission"}]
    return {"metadata": {"name": name}, "spec": spec, "status": {"phase": phase}}


def _env(tmp_path: Path) -> dict[str, str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "kubectl"
    fake.write_text(_FAKE_KUBECTL, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "FAKE_DIR": str(tmp_path),
        "RUNNER_SCHEDULER_FAIL_OPEN_STATE_DIR": str(tmp_path / "state"),
        "RUNNER_SCHEDULER_FAIL_OPEN_GRACE_SECONDS": str(_GRACE),
        "RUNNER_SCHEDULER_FAIL_OPEN_NOW": str(_NOW),
    }


def _write(tmp_path: Path, *, ready: int | None, pods: list[_Json] | None = None) -> None:
    status = {} if ready is None else {"readyReplicas": ready}
    (tmp_path / "deployment.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    if pods is not None:
        (tmp_path / "pods.json").write_text(json.dumps({"items": pods}), encoding="utf-8")


def _zero_since(tmp_path: Path, seconds_ago: int) -> None:
    state = tmp_path / "state"
    state.mkdir(exist_ok=True)
    (state / "first-zero-ready-at").write_text(f"{_NOW - seconds_ago}\n", encoding="utf-8")


def _run(tmp_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(_SCRIPT), *args],
        env=_env(tmp_path),
        capture_output=True,
        text=True,
        check=False,
    )


def _writes(tmp_path: Path) -> list[str]:
    log = (tmp_path / "argv.log").read_text(encoding="utf-8").splitlines()
    return [line for line in log if " patch " in line or " delete " in line]


def test_a_ready_scheduler_changes_nothing_and_clears_the_outage_clock(tmp_path: Path) -> None:
    _write(tmp_path, ready=1, pods=[_pod("r1")])
    _zero_since(tmp_path, 300)
    run = _run(tmp_path)
    assert run.returncode == 0, run.stderr
    assert _writes(tmp_path) == []
    assert not (tmp_path / "state" / "first-zero-ready-at").exists()


def test_the_first_cycle_at_zero_ready_starts_the_grace_and_changes_nothing(
    tmp_path: Path,
) -> None:
    _write(tmp_path, ready=None, pods=[_pod("r1")])
    run = _run(tmp_path)
    assert run.returncode == 0, run.stderr
    assert _writes(tmp_path) == []
    clock = (tmp_path / "state" / "first-zero-ready-at").read_text(encoding="utf-8")
    assert clock.strip() == str(_NOW)


def test_within_the_grace_a_stranded_pod_is_left_alone(tmp_path: Path) -> None:
    _write(tmp_path, ready=0, pods=[_pod("r1")])
    _zero_since(tmp_path, _GRACE - 1)
    run = _run(tmp_path)
    assert run.returncode == 0, run.stderr
    assert _writes(tmp_path) == []


def test_past_the_grace_the_runner_is_patched_before_its_pod_is_deleted(tmp_path: Path) -> None:
    _write(tmp_path, ready=0, pods=[_pod("r1")])
    _zero_since(tmp_path, _GRACE)
    run = _run(tmp_path)
    assert run.returncode == 0, run.stderr
    assert _writes(tmp_path) == [
        "-n arc-runners patch ephemeralrunner r1 --type=merge "
        '-p {"spec":{"spec":{"schedulerName":"default-scheduler"}}}',
        "-n arc-runners delete pod r1 --ignore-not-found --wait=false",
    ]


def test_only_a_pending_unbound_ungated_pod_naming_the_scheduler_is_stranded(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        ready=0,
        pods=[
            _pod("stranded"),
            _pod("gated", gated=True),
            _pod("bound", node="gmktec-xubuntu"),
            _pod("running", phase="Running", node="gmktec-xubuntu"),
            _pod("default", scheduler="default-scheduler"),
        ],
    )
    _zero_since(tmp_path, _GRACE)
    run = _run(tmp_path)
    assert run.returncode == 0, run.stderr
    assert [line.split()[4] for line in _writes(tmp_path)] == ["stranded", "stranded"]


def test_a_deleted_deployment_counts_as_zero_ready(tmp_path: Path) -> None:
    _write(tmp_path, ready=None, pods=[_pod("r1")])
    (tmp_path / "deployment.err").write_text(
        'Error from server (NotFound): deployments.apps "ci-runner-scheduler" not found\n',
        encoding="utf-8",
    )
    _zero_since(tmp_path, _GRACE)
    run = _run(tmp_path)
    assert run.returncode == 0, run.stderr
    assert len(_writes(tmp_path)) == 2


def test_a_failed_deployment_read_changes_nothing_and_fails_the_cycle(tmp_path: Path) -> None:
    _write(tmp_path, ready=None, pods=[_pod("r1")])
    (tmp_path / "deployment.err").write_text("Error: connection refused\n", encoding="utf-8")
    _zero_since(tmp_path, _GRACE)
    run = _run(tmp_path)
    assert run.returncode != 0
    assert "connection refused" in run.stderr
    assert _writes(tmp_path) == []
    assert (tmp_path / "state" / "first-zero-ready-at").exists()


def test_a_failed_pod_list_changes_nothing_and_fails_the_cycle(tmp_path: Path) -> None:
    _write(tmp_path, ready=0)
    _zero_since(tmp_path, _GRACE)
    run = _run(tmp_path)
    assert run.returncode != 0
    assert _writes(tmp_path) == []


def test_a_rejected_patch_keeps_that_pod_and_still_rescues_the_others(tmp_path: Path) -> None:
    _write(tmp_path, ready=0, pods=[_pod("r1"), _pod("r2")])
    (tmp_path / "reject-patch").write_text("r1", encoding="utf-8")
    _zero_since(tmp_path, _GRACE)
    run = _run(tmp_path)
    assert run.returncode != 0, "a failed write must show as a failed unit"
    assert not any(" delete pod r1 " in line for line in _writes(tmp_path))
    assert any(" delete pod r2 " in line for line in _writes(tmp_path))


def test_a_rejected_delete_fails_the_cycle_so_the_next_one_retries(tmp_path: Path) -> None:
    _write(tmp_path, ready=0, pods=[_pod("r1")])
    (tmp_path / "reject-delete").write_text("", encoding="utf-8")
    _zero_since(tmp_path, _GRACE)
    run = _run(tmp_path)
    assert run.returncode != 0
    assert "the next cycle retries" in run.stderr


def test_dry_run_reports_the_rescue_and_writes_nothing(tmp_path: Path) -> None:
    _write(tmp_path, ready=0, pods=[_pod("r1")])
    _zero_since(tmp_path, _GRACE)
    run = _run(tmp_path, "--dry-run")
    assert run.returncode == 0, run.stderr
    assert "would rescue r1" in run.stdout
    assert _writes(tmp_path) == []


def test_dry_run_does_not_start_the_outage_clock(tmp_path: Path) -> None:
    _write(tmp_path, ready=0, pods=[])
    run = _run(tmp_path, "--dry-run")
    assert run.returncode == 0, run.stderr
    assert not (tmp_path / "state" / "first-zero-ready-at").exists()


def test_ci_pool_installs_the_reconciler_on_the_server_only() -> None:
    plays = yaml.safe_load(_PLAY.read_text(encoding="utf-8"))
    entries = [
        role
        for play in plays
        for role in play.get("roles", [])
        if isinstance(role, dict) and role.get("role") == "runner_scheduler_fail_open"
    ]
    assert [entry["when"] for entry in entries] == ["cluster_role == 'server'"]


def test_the_controller_trigger_alerts_on_the_scheduler_at_zero_available() -> None:
    trigger = json.loads(_TRIGGER.read_text(encoding="utf-8"))
    filters = trigger["query"]["filters"]
    names = next(f["value"] for f in filters if f["column"] == "k8s.deployment.name")
    assert _SCHEDULER in names
