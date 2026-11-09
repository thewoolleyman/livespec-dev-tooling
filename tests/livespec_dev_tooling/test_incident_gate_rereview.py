"""Re-review findings on livespec-dev-tooling#3862 (work-item livespec-dev-tooling-oqpw6t).

- A refused CI admission is STICKY: after its one retry, every later launch is
  refused without another observer read, so a revocation cannot queue two
  serialized reads per remaining member into the job timeout.
- A deadline run works where `os.waitid` is absent (CPython on macOS).
- The CI job log receives each member's output at once, not when a block
  buffer on a pipe happens to fill.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from livespec_dev_tooling import _check_target_isolation as isolation
from livespec_dev_tooling import incident_ci_entry, incident_ci_process
from livespec_dev_tooling._check_target_runner import COMPLETED, TIMED_OUT, TargetRun, run_targets
from livespec_dev_tooling.incident_ci_policy import CiEvent, CiTarget
from tests.livespec_dev_tooling.test_incident_ci_payload import packet

__all__: list[str] = []


def test_a_refused_admission_is_sticky(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(incident_ci_entry, "current_allowed_cpu_count", lambda: 1)
    names = tuple(f"check-t{index}" for index in range(10))
    (tmp_path / "justfile").write_text("".join(f"{name}:\n    true\n" for name in names))
    reads: list[int] = []

    def current(**_: object) -> bool:
        reads.append(1)
        # The plan the caller holds and the first recheck confirm; then revoked.
        return len(reads) <= 2

    entry = incident_ci_entry.CiEntry(
        repo=tmp_path,
        targets=tuple(CiTarget(name=name, classification="fast") for name in names),
        current=current,
        observer=lambda **_: True,
        admission_window_seconds=0.0,
    )
    event = CiEvent(
        kind="pull_request",
        repository="owner/repo",
        base_sha="a" * 40,
        head_sha="b" * 40,
        pr_number=7,
        labels=("expedited-incident-response",),
    )
    payload = json.dumps(packet())
    plan = entry.plan(event=event, payload=payload, environ=dict(os.environ))
    assert plan is not None
    code = entry.execute(
        plan=plan,
        names=names,
        report=tmp_path / "outcomes.jsonl",
        payload=payload,
        environ=dict(os.environ),
    )
    # At most the refusal and its one retry after the confirmation, not two per member.
    assert (code, len(reads) - 2 <= 2) == (2, True)


def test_a_deadline_run_works_without_waitid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delattr(isolation.os, "waitid")
    outcomes = run_targets(
        runs=[
            TargetRun(name="quick", argv=("/bin/sh", "-c", "exit 3")),
            TargetRun(name="slow", argv=("/bin/sh", "-c", "sleep 30")),
        ],
        cwd=tmp_path,
        max_workers=2,
        deadline_seconds=1.0,
    )
    assert [(o.status, o.returncode) for o in outcomes] == [(COMPLETED, 3), (TIMED_OUT, None)]


def test_member_output_is_flushed_to_the_job_log(monkeypatch: pytest.MonkeyPatch) -> None:
    written: list[str] = []
    flushed: list[int] = []

    class Stream:
        def write(self, text: str) -> int:
            written.append(text)
            return len(text)

        def flush(self) -> None:
            flushed.append(len(written))

    monkeypatch.setattr(incident_ci_process.sys, "stdout", Stream())
    incident_ci_process._echo(text="::: just check-a [exit 0]\n")  # noqa: SLF001
    assert (written, flushed) == (["::: just check-a [exit 0]\n"], [1])
