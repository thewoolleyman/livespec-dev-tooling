"""Consumer-tier: a coverage consumer that did not reuse reaches the maintainer.

Covers the `SPECIFICATION/scenarios.md` acceptance scenario "a coverage
consumer that did not reuse reaches the maintainer". The scheduled detector is
run through its `main` entry point against a fleet CI run on a NON-master
branch whose mandatory coverage consumer recorded an outcome other than
`reused`, with the GitHub reads answered by a fake budgeted client. The
notification record on stdout must name the repository, run, job and outcome.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from livespec_dev_tooling.budgeted_gh import GhRead
from livespec_dev_tooling.reuse_outcome_detector import main

__all__: list[str] = []

_REPOSITORY = "thewoolleyman/livespec-dev-tooling"
_RUN_ID = 4242
_JOB_ID = 8484


def _fake_read(*, args: list[str]) -> GhRead:
    """Answer the detector's GitHub reads for one non-master run."""
    if args[:2] == ["run", "list"]:
        runs = [{"databaseId": _RUN_ID}]
        assert "--branch" not in args, "the run listing must not narrow to one branch"
        return GhRead(returncode=0, stdout=json.dumps(runs), stderr="")
    if args[1].endswith("/jobs?per_page=100"):
        job = {"id": _JOB_ID, "name": "check-coverage", "completed_at": "2026-11-13T10:00:00Z"}
        return GhRead(returncode=0, stdout=json.dumps({"jobs": [job]}) + "\n", stderr="")
    record = {
        "repository": _REPOSITORY,
        "run_id": str(_RUN_ID),
        "job_id": "check-coverage",
        "duration_ms": 721_000,
        "outcome": "missing_receipt",
    }
    log = f"2026-11-13T10:00:01.0000000Z LIVESPEC_COVERAGE_REUSE_OUTCOME {json.dumps(record)}\n"
    return GhRead(returncode=0, stdout=log, stderr="")


def test_non_reused_consumer_on_any_branch_raises_a_notification(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A non-reused mandatory consumer is reported whatever branch its run was on."""
    exit_code = main(
        argv=["--repo", _REPOSITORY, "--state-file", str(tmp_path / "state.json")],
        read=_fake_read,
        now=lambda: datetime(2026, 11, 13, 10, 5, tzinfo=timezone.utc),
    )

    assert exit_code == 0
    notifications = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert notifications == [
        {
            "notification": (
                f"coverage reuse fallback: repository={_REPOSITORY} "
                f"run={_RUN_ID} job={_JOB_ID} outcome=missing_receipt"
            )
        }
    ]
