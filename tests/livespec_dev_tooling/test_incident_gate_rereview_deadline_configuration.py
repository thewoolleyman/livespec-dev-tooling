"""Deadline configuration coverage for the incident-gate re-review test."""

from __future__ import annotations

from pathlib import Path

import pytest

from livespec_dev_tooling._check_target_runner import COMPLETED, TIMED_OUT, TargetOutcome
from tests.livespec_dev_tooling import test_incident_gate_rereview as rereview

__all__: list[str] = []


def test_deadline_rereview_gives_quick_and_slow_targets_separate_budgets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[tuple[tuple[str, ...], float | None]] = []

    def run_targets(**kwargs: object) -> tuple[TargetOutcome, ...]:
        runs = kwargs["runs"]
        deadline_seconds = kwargs["deadline_seconds"]
        assert isinstance(runs, list)
        assert isinstance(deadline_seconds, float)
        names = tuple(run.name for run in runs)
        calls.append((names, deadline_seconds))
        return tuple(
            TargetOutcome(
                name=run.name,
                status=COMPLETED if run.name == "quick" else TIMED_OUT,
                returncode=3 if run.name == "quick" else None,
            )
            for run in runs
        )

    monkeypatch.setattr(rereview, "run_targets", run_targets)

    rereview.test_a_deadline_run_works_without_waitid(tmp_path=tmp_path, monkeypatch=monkeypatch)

    assert calls == [(("quick",), 30.0), (("slow",), 1.0)]
