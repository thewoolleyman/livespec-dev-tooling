"""Save an abandoned gate Job's last log lines before the client deletes the Job.

A Job that reached no terminal condition used to be deleted with nothing kept of
what its containers had said, so the step that hung could never be named
(livespec-dev-tooling-yrjatv). Before the delete, the client now writes the last
`LOG_TAIL_LINES` lines of every container of the Job's pod to a file on the
pushing host, beside the gate run's own record, and the no-verdict refusal names
that file.

The gate pod prints its own process tree into those lines
(`gate-process-tree-watchdog.sh`): the gates credential holds no `pods/exec`, so
the client could not read a process tree itself, and it is not widened to. The
client saves the logs BEFORE it deletes the Job, so a tree printed by the pod's
preStop hook lands after the save; the saved tree is the last periodic one.

A failure to read the pod list or a container's log, or to write the file, is
recorded in the file where it can be and never stops the delete.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import cast

from livespec_dev_tooling.gate_remote_invocation import (
    GateCommandOutcome,
    GateCommandRunner,
    GateStepFailed,
    StepOutcome,
    require_success,
)
from livespec_dev_tooling.gate_remote_request import GateRunRequest

# `returns` is VENDORED, not installed; a bare import here would resolve only
# when some earlier import in the process happened to run first.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = [
    "LOG_TAIL_LINES",
    "abandon_gate_job",
    "abandoned_job_record_path",
    "save_abandoned_job_logs",
    "with_record_path",
]

LOG_TAIL_LINES = 200
_STAMP_ENV = "LIVESPEC_GATE_RUN_PROGRESS_STAMP"
_DELETE_STEP = "delete-abandoned-gate-job"
_FALLBACK_DIR = Path("tmp") / "gate-abandoned-jobs"


def abandon_gate_job(
    *,
    request: GateRunRequest,
    runner: GateCommandRunner,
    job_name: str,
    kubectl: Sequence[str],
) -> tuple[StepOutcome, Path]:
    """Save the Job's last log lines, THEN delete it, and return the delete's outcome and the path.

    The save comes first because the delete takes the pod and its logs with it,
    and it can never stop the delete: a read or write that fails is recorded in
    the saved file. The path is returned so the no-verdict refusal can name it.
    """
    saved = save_abandoned_job_logs(
        request=request, runner=runner, job_name=job_name, kubectl=kubectl
    )
    argv = [*kubectl, "delete", "job", job_name]
    deleted = require_success(
        step=_DELETE_STEP, argv=argv, outcome=runner(argv=argv, cwd=request.repo_root)
    )
    return deleted, saved


def abandoned_job_record_path(*, request: GateRunRequest, job_name: str) -> Path:
    """Name the file: in the gate run's own directory when one is named, else under `tmp/`.

    `gate-run.sh` exports the progress stamp, which lives in the run's own record
    directory, so its parent is that directory. A client run by hand has no such
    stamp and writes under the repository's gitignored `tmp/`.
    """
    stamp = os.environ.get(_STAMP_ENV, "")
    directory = Path(stamp).parent if stamp else request.repo_root / _FALLBACK_DIR
    return directory / f"abandoned-job-{job_name}.log"


def save_abandoned_job_logs(
    *,
    request: GateRunRequest,
    runner: GateCommandRunner,
    job_name: str,
    kubectl: Sequence[str],
) -> Path:
    """Write the saved file and return its path; never raise."""
    path = abandoned_job_record_path(request=request, job_name=job_name)
    sections = [f"# abandoned gate Job {job_name}: last {LOG_TAIL_LINES} log lines per container\n"]
    sections.extend(
        _pod_sections(request=request, runner=runner, job_name=job_name, kubectl=kubectl)
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _ = path.write_text("".join(sections), encoding="utf-8")
    except OSError as unwritable:
        # The file is evidence; the delete that follows is not allowed to depend on it.
        sections.append(f"# could not write {path}: {unwritable}\n")
    return path


def with_record_path(*, failure: GateStepFailed, path: Path) -> GateStepFailed:
    """Add the saved file's path to a no-verdict refusal."""
    return dataclasses.replace(
        failure, detail=f"{failure.detail}; the abandoned Job's last log lines are saved at {path}"
    )


def _pod_sections(
    *, request: GateRunRequest, runner: GateCommandRunner, job_name: str, kubectl: Sequence[str]
) -> list[str]:
    argv = [*kubectl, "get", "pods", "--selector", f"job-name={job_name}", "--output", "json"]
    read = runner(argv=argv, cwd=request.repo_root)
    refused = _refusal(outcome=read, what="reading the Job's pods")
    if refused:
        return [refused]
    try:
        payload = cast("dict[str, list[dict[str, object]]]", json.loads(read.unwrap().stdout))
        pods = payload["items"]
    except (ValueError, KeyError, TypeError) as malformed:
        return [f"# reading the Job's pods returned an unreadable answer: {malformed}\n"]
    sections: list[str] = []
    for pod in pods:
        sections.extend(
            _container_sections(request=request, runner=runner, kubectl=kubectl, pod=pod)
        )
    return sections or ["# the Job had no pod\n"]


def _container_sections(
    *,
    request: GateRunRequest,
    runner: GateCommandRunner,
    kubectl: Sequence[str],
    pod: dict[str, object],
) -> list[str]:
    metadata = cast("dict[str, str]", pod.get("metadata", {}))
    spec = cast("dict[str, list[dict[str, str]]]", pod.get("spec", {}))
    pod_name = metadata.get("name", "")
    containers = [*spec.get("initContainers", []), *spec.get("containers", [])]
    sections: list[str] = []
    for container in containers:
        name = container.get("name", "")
        argv = [
            *kubectl,
            "logs",
            pod_name,
            "--container",
            name,
            "--tail",
            str(LOG_TAIL_LINES),
        ]
        ran = runner(argv=argv, cwd=request.repo_root)
        refused = _refusal(outcome=ran, what=f"reading the log of {pod_name}/{name}")
        body = refused or ran.unwrap().stdout
        sections.append(f"## pod {pod_name} container {name}\n{body}\n")
    return sections


def _refusal(*, outcome: GateCommandOutcome, what: str) -> str:
    """Say why a read failed, or the empty string when it succeeded."""
    if isinstance(outcome, Failure):
        return f"# {what} did not run: {outcome.failure().detail}\n"
    ran = outcome.unwrap()
    if ran.returncode == 0:
        return ""
    return f"# {what} was refused (exit {ran.returncode}): {ran.stderr.strip()}\n"
