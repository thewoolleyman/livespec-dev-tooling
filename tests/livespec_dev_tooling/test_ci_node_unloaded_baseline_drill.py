"""The unloaded-baseline drill script, run for real against a faked kubectl.

livespec-dev-tooling-6e5pyj, Stage B phase 1 (plan ci-runtime-and-cost). The
claims are about decisions: when a node is skipped instead of measured, what
counts as a baseline, what the Job asks the cluster for, and that every Job is
deleted on every exit. So the script runs, with a fake `kubectl` serving canned
pod lists, Job status and logs. No cluster is reached.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

__all__: list[str] = []

_Json = dict[str, Any]

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = (
    _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "kueue" / "drill-ci-node-unloaded-baseline.sh"
)
_PLAY = _REPO_ROOT / "ansible" / "ci-node-unloaded-baseline.yml"
_NODE = "hp-xubuntu"
_UNLOADED_LOGS = (
    "RESULT threads=1 rep=1 events_per_second=1000.0\n"
    "LOAD ncpu=16 node_busy_excl_self=0.100 psi_end_avg60=1.00\n"
    "VERDICT unloaded\n"
)
_LOADED_LOGS = (
    "RESULT threads=1 rep=1 events_per_second=600.0\n"
    "LOAD ncpu=16 node_busy_excl_self=0.700 psi_end_avg60=40.00\n"
    "VERDICT loaded\n"
)

_FAKE_KUBECTL = r"""#!/usr/bin/env bash
printf '%s\n' "$*" >>"$FAKE_DIR/argv.log"
case "$*" in
  "get node "*" -l "*)
    echo "error: name cannot be provided when a selector is specified" >&2; exit 1 ;;
  "get nodes -l k3s-role=arc-runner-host -o name")
    [ -f "$FAKE_DIR/labelled" ] && cat "$FAKE_DIR/labelled" ;;
  "-n arc-runners get pods "*) cat "$FAKE_DIR/runners.json" ;;
  "-n factory get pods "*) cat "$FAKE_DIR/factory.json" ;;
  "-n factory-mi-homelab get pods "*) echo '{"items": []}' ;;
  "create -f -") cat >"$FAKE_DIR/manifest.json" ;;
  "-n arc-runners get job "*) cat "$FAKE_DIR/job.json" ;;
  "-n arc-runners logs "*) cat "$FAKE_DIR/logs.txt" ;;
  "-n arc-runners delete job "*) ;;
  *) echo "fake kubectl: unexpected argv: $*" >&2; exit 1 ;;
esac
"""


def _pod(*, churn_slot: bool) -> _Json:
    requests = {"ci-runner.io/churn-slot": "1"} if churn_slot else {}
    return {"spec": {"containers": [{"resources": {"requests": requests}}]}}


def _set_up(
    tmp_path: Path,
    *,
    runners: int = 0,
    workflow_pods: int = 0,
    factory: int = 0,
    labelled: bool = True,
    job: str = "Complete",
    logs: str = _UNLOADED_LOGS,
) -> None:
    pods = [_pod(churn_slot=True)] * runners + [_pod(churn_slot=False)] * workflow_pods
    _ = (tmp_path / "runners.json").write_text(json.dumps({"items": pods}), encoding="utf-8")
    _ = (tmp_path / "factory.json").write_text(
        json.dumps({"items": [{}] * factory}), encoding="utf-8"
    )
    if labelled:
        _ = (tmp_path / "labelled").write_text(f"node/{_NODE}\nnode/other-node\n", encoding="utf-8")
    conditions = [] if job == "running" else [{"type": job, "status": "True"}]
    _ = (tmp_path / "job.json").write_text(
        json.dumps({"status": {"conditions": conditions}}), encoding="utf-8"
    )
    _ = (tmp_path / "logs.txt").write_text(logs, encoding="utf-8")


def _run(tmp_path: Path, *nodes: str) -> subprocess.CompletedProcess[str]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fake = bin_dir / "kubectl"
    _ = fake.write_text(_FAKE_KUBECTL, encoding="utf-8")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return subprocess.run(
        ["bash", str(_SCRIPT), *nodes],
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "FAKE_DIR": str(tmp_path),
            "CI_NODE_BASELINE_INTERVAL_SECONDS": "0",
            "CI_NODE_BASELINE_MAX_POLLS": "3",
        },
        capture_output=True,
        text=True,
        check=False,
    )


def _argv(tmp_path: Path) -> list[str]:
    return (tmp_path / "argv.log").read_text(encoding="utf-8").splitlines()


def _created(tmp_path: Path) -> bool:
    return any(line == "create -f -" for line in _argv(tmp_path))


def _deleted(tmp_path: Path) -> bool:
    return any(line.startswith("-n arc-runners delete job ") for line in _argv(tmp_path))


def test_a_quiet_node_with_an_unloaded_verdict_yields_a_baseline(tmp_path: Path) -> None:
    _set_up(tmp_path, runners=2, workflow_pods=5, factory=2)
    run = _run(tmp_path, _NODE)
    assert run.returncode == 0, run.stdout + run.stderr
    assert f"PRECONDITION node={_NODE} runner_pods=2 factory_pods=2" in run.stdout
    assert f"BASELINE node={_NODE}" in run.stdout
    assert f"{_NODE}: VERDICT unloaded" in run.stdout
    assert _deleted(tmp_path)


def test_the_job_takes_one_churn_slot_through_the_dev_tooling_queue_on_the_named_node(
    tmp_path: Path,
) -> None:
    _set_up(tmp_path)
    _ = _run(tmp_path, _NODE)
    job = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert job["metadata"]["namespace"] == "arc-runners"
    assert job["metadata"]["labels"]["kueue.x-k8s.io/queue-name"] == "livespec-dev-tooling-lq"
    assert job["spec"]["suspend"] is True
    pod = job["spec"]["template"]["spec"]
    assert pod["nodeSelector"] == {"kubernetes.io/hostname": _NODE}
    (container,) = pod["containers"]
    # Only the churn slot: the ClusterQueue covers no other resource.
    assert container["resources"]["requests"] == {"ci-runner.io/churn-slot": "1"}
    assert "sysbench cpu" in container["command"][2]


def test_more_runner_pods_than_the_limit_skips_the_node_without_a_job(tmp_path: Path) -> None:
    _set_up(tmp_path, runners=3)
    run = _run(tmp_path, _NODE)
    assert run.returncode == 3
    assert f"ABORT node={_NODE} reason=busy" in run.stdout
    assert not _created(tmp_path)


def test_workflow_pods_do_not_count_as_runner_pods(tmp_path: Path) -> None:
    _set_up(tmp_path, runners=1, workflow_pods=9)
    run = _run(tmp_path, _NODE)
    assert run.returncode == 0, run.stdout
    assert "runner_pods=1 " in run.stdout


def test_more_factory_pods_than_the_limit_skips_the_node_without_a_job(tmp_path: Path) -> None:
    _set_up(tmp_path, factory=3)
    run = _run(tmp_path, _NODE)
    assert run.returncode == 3
    assert "factory_pods=3>2" in run.stdout
    assert not _created(tmp_path)


def test_a_node_outside_the_churn_slot_flavor_is_skipped(tmp_path: Path) -> None:
    _set_up(tmp_path, labelled=False)
    run = _run(tmp_path, _NODE)
    assert run.returncode == 3
    assert "reason=no-node-carrying-k3s-role=arc-runner-host" in run.stdout
    assert not _created(tmp_path)


def test_a_loaded_verdict_is_a_record_not_a_baseline(tmp_path: Path) -> None:
    _set_up(tmp_path, logs=_LOADED_LOGS)
    run = _run(tmp_path, _NODE)
    assert run.returncode == 3
    assert f"LOADED node={_NODE}" in run.stdout
    assert "BASELINE" not in run.stdout
    assert _deleted(tmp_path)


def test_a_failed_job_is_not_a_baseline_and_is_still_deleted(tmp_path: Path) -> None:
    _set_up(tmp_path, job="Failed", logs="ABORT psi_avg60=40.00 at or above 10\n")
    run = _run(tmp_path, _NODE)
    assert run.returncode == 3
    assert "reason=job-failed" in run.stdout
    assert f"{_NODE}: ABORT psi_avg60=40.00" in run.stdout
    assert _deleted(tmp_path)


def test_a_job_that_never_finishes_is_abandoned_and_deleted(tmp_path: Path) -> None:
    _set_up(tmp_path, job="running")
    run = _run(tmp_path, _NODE)
    assert run.returncode == 3
    assert "reason=job-running-after-3-polls" in run.stdout
    assert _deleted(tmp_path)


def test_a_skipped_node_does_not_stop_the_next_one(tmp_path: Path) -> None:
    _set_up(tmp_path, labelled=False)
    run = _run(tmp_path, "gone-node", _NODE)
    assert run.returncode == 3
    assert run.stdout.count("ABORT node=") == 2


def test_naming_no_node_refuses(tmp_path: Path) -> None:
    _set_up(tmp_path)
    run = _run(tmp_path)
    assert run.returncode == 1
    assert "name at least one node" in run.stderr
    assert not (tmp_path / "argv.log").exists()


def test_the_play_acts_only_for_the_confirmed_server_never_under_check_and_names_no_node() -> None:
    play = yaml.safe_load(_PLAY.read_text(encoding="utf-8"))[0]
    assert (
        "cluster_role | default('') == 'server'" in play["vars"]["ci_node_unloaded_baseline_named"]
    )
    assert "ci_node_unloaded_baseline_nodes" not in play["vars"]
    block = next(task for task in play["tasks"] if "block" in task)
    assert "not ansible_check_mode" in block["when"]
    assert "ci_node_unloaded_baseline_named | bool" in block["when"]


_FAKE_SYSBENCH = r"""#!/bin/sh
case "$1" in
  --version) echo "sysbench 1.0.20" ;;
  *) echo "    events per second:  1234.56" ;;
esac
"""


def _run_pod_script(tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    """Run the in-Job measurement under `sh` with apt-get and sysbench faked."""
    pod_script = subprocess.run(
        [
            "bash",
            "-c",
            f'eval "$(sed -n \'/^POD_SCRIPT=/,/^)"$/p\' {_SCRIPT})"; printf %s "$POD_SCRIPT"',
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    for name, body in (("apt-get", "#!/bin/sh\nexit 0\n"), ("sysbench", _FAKE_SYSBENCH)):
        fake = bin_dir / name
        _ = fake.write_text(body, encoding="utf-8")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
    return subprocess.run(
        ["sh", "-c", pod_script],
        env={
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "REPS": "2",
            "SECONDS_PER_RUN": "1",
            **env,
        },
        capture_output=True,
        text=True,
        check=False,
    )


_HAS_PSI = Path("/proc/pressure/cpu").exists()


@pytest.mark.skipif(not _HAS_PSI, reason="the kernel exposes no CPU pressure file here")
def test_the_in_job_measurement_reports_each_run_the_load_and_a_verdict(tmp_path: Path) -> None:
    run = _run_pod_script(tmp_path, PSI_MAX="1000", BUSY_MAX="1.01")
    assert run.returncode == 0, run.stdout + run.stderr
    results = [line for line in run.stdout.splitlines() if line.startswith("RESULT ")]
    assert results == [
        f"RESULT threads={th} rep={rep} events_per_second=1234.56"
        for th in (1, 3)
        for rep in (1, 2)
    ]
    assert "LOAD ncpu=" in run.stdout
    assert run.stdout.splitlines()[-1] == "VERDICT unloaded"


@pytest.mark.skipif(not _HAS_PSI, reason="the kernel exposes no CPU pressure file here")
def test_the_in_job_measurement_aborts_before_measuring_under_pressure(tmp_path: Path) -> None:
    run = _run_pod_script(tmp_path, PSI_MAX="0", BUSY_MAX="1.01")
    assert run.returncode == 3
    assert "ABORT psi_avg60=" in run.stdout
    assert "RESULT " not in run.stdout


@pytest.mark.skipif(not _HAS_PSI, reason="the kernel exposes no CPU pressure file here")
def test_the_in_job_measurement_reports_a_busy_node_as_loaded(tmp_path: Path) -> None:
    run = _run_pod_script(tmp_path, PSI_MAX="1000", BUSY_MAX="0")
    assert run.returncode == 0, run.stderr
    assert run.stdout.splitlines()[-1] == "VERDICT loaded"
