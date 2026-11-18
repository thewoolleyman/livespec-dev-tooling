"""Scenario "top5 prints a hold carrying a DRAINED: line as DRAINED, not STALE HOLD".

Rule HOLD-ENDS-ARE-DRIVEN (`.ai/coordinator-duties.md` §3): `scripts/coordinator/top5`
prints every live launch hold and marks one older than 60 minutes STALE HOLD. A drained
hold ends only when a priorities-record re-adds its plan, so it prints DRAINED instead;
a line starting with `DRAINED:` marks it, beside the legacy END CONDITION marker.

These run a copy of the real script beside a silent stub `fleet-utilization.sh`, against
a temporary HOME holding the hold directory, with a ledger wrapper stub that answers
nothing. The live ledger, cluster and hold files are never read.
"""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import time
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOP5 = _REPO_ROOT / "scripts" / "coordinator" / "top5"
_END_CONDITION = "END CONDITION: the plan is back on the priorities record"
_HOLD_BODY = f"OWNER: legacy-coordinator-agent\n{_END_CONDITION}\n"
_DRAINED_LINE = "  DRAINED: some-plan off the priorities record as of 2026-11-18\n"
_TWO_HOURS_S = 2 * 60 * 60


def _exe(*, path: Path, body: str) -> None:
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class _Host:
    """A temporary HOME with the hold directory top5 reads, and a copy of top5."""

    def __init__(self, *, tmp_path: Path) -> None:
        self.home = tmp_path / "home"
        self.holds = (
            self.home / "workspace" / "livespec-orchestrator-beads-fabro" / "tmp" / "petri-canary"
        )
        self.holds.mkdir(parents=True)
        coordinator = tmp_path / "coordinator"
        coordinator.mkdir()
        self.script = coordinator / "top5"
        _ = shutil.copy(_TOP5, self.script)
        _exe(path=coordinator / "fleet-utilization.sh", body="#!/bin/sh\nexit 0\n")
        self.wrapper = tmp_path / "wrapper.sh"
        _exe(path=self.wrapper, body="#!/bin/sh\nexit 0\n")

    def hold(self, *, name: str, body: str) -> None:
        path = self.holds / name
        _ = path.write_text(body, encoding="utf-8")
        old = time.time() - _TWO_HOURS_S
        os.utime(path, (old, old))

    def hold_lines(self) -> list[str]:
        env = {
            "HOME": str(self.home),
            "PATH": os.environ["PATH"],
            "TOP5_LEDGER_WRAPPER": str(self.wrapper),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        result = subprocess.run(
            ["bash", str(self.script)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        return [line.strip() for line in result.stdout.splitlines() if "hold-" in line]


@pytest.fixture
def host(tmp_path: Path) -> _Host:
    return _Host(tmp_path=tmp_path)


def test_an_old_hold_with_a_drained_line_prints_drained_with_its_end_condition(
    host: _Host,
) -> None:
    host.hold(name="hold-some-plan", body=_HOLD_BODY + _DRAINED_LINE)
    lines = host.hold_lines()
    assert len(lines) == 1, lines
    assert lines[0].startswith("DRAINED hold-some-plan age ")
    assert _END_CONDITION in lines[0]
    assert "STALE HOLD" not in lines[0]


def test_the_same_old_hold_without_the_drained_line_prints_stale_hold(host: _Host) -> None:
    host.hold(name="hold-some-plan", body=_HOLD_BODY)
    lines = host.hold_lines()
    assert len(lines) == 1, lines
    assert lines[0].startswith("STALE HOLD hold-some-plan age ")
