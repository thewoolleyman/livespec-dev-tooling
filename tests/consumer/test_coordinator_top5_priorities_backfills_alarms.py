"""Scenario "top5 prints HOST-GUARD BACKFILLS, SEAT-WATCHDOG ALARMS and the newest priorities-record".

`scripts/coordinator/top5` prints the first line of `host-guard-backfills` (OVERDUE on its exit 3),
the newest SEAT-WATCHDOG-ALARM comments on the coordinator epic, and the P-list taken from the NEWEST
`PRIORITIES now` scope event on that epic (priority 0 included), chaining to the older record only
where the newer one says the rest is unchanged. Each section degrades to an explicit UNREAD line.

The fixture comments reproduce the real record formats measured on epic livespec-dev-tooling-6tgd2z
on 2026-11-21: a multi-line record (00:04Z) and an inline record (00:10Z) that ends "the rest unchanged".
These run a copy of the real script against a stub ledger wrapper and a temporary HOME.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOP5 = _REPO_ROOT / "scripts" / "coordinator" / "top5"

_OLD_RECORD = (
    "plan-scope-event\nauthor: legacy-coordinator-agent\ntimestamp: 2026-11-21 ~00:2xZ\n\n"
    "Requirement carriers:\n- priorities-record (NEW TOP TWO, ahead of the older list)\n"
    '- MAINTAINER, verbatim: "disable remote control".\n'
    "- PRIORITIES now:\n"
    "  1 fleet_host_guard deadlock: a clear escape valve, or delete the hook.\n"
    "  2 Remote Control: DISABLE Remote Control support completely now.\n"
    "  3 expedited-incident-response-flag (bqnzcm), deadline 2026-11-21T06:52Z\n"
    "  4 central-credential-service (overseer-iyfjbo)\n"
    "  5 bootstrap-credentials-and-onboarding (hxi-vxsmdv)\n"
    "  6 stale-base-merge-options (xowhol); 7 address-honeycomb-alerts (bd-ib-xkwdap);"
    " 8a implement-test-performance (sv6m5p); 9 dev-host-disk-retention (qgwxo4).\n"
    "  KEPT seats unchanged.\n- This supersedes the maintainer's earlier no.\n"
)
_NEW_RECORD = (
    "plan-scope-event\nauthor: legacy-coordinator-agent\ntimestamp: 2026-11-21 ~00:1xZ\n\n"
    "Requirement carriers:\n"
    '- MAINTAINER, verbatim, NEW PRIORITY 0 (above everything): "never let a 5-hour limit run out".\n'
    "- PRIORITIES now: 0 no 5-hour limit ever runs out (caam rotates on the session window);"
    " 1 fleet-host-guard-escape-valve; 2 remote-control-retirement (both due 2026-11-21T12:30Z);"
    " then 3 bqnzcm, 4 overseer-iyfjbo, 5 hxi-vxsmdv and the rest unchanged.\n"
    "- Rule E is lifted for this purpose only.\n"
)
_ANCIENT_RECORD = "plan-scope-event\nauthor: x\n\n- priorities-record\n- PRIORITIES now:\n  1 long-closed-plan (livespec-dev-tooling-aaaaaa)\n"


def _comment(*, stamp: str, text: str) -> dict[str, str]:
    return {"id": stamp, "issue_id": "e", "author": "a", "text": text, "created_at": stamp}


def _alarm(*, stamp: str, seat: str) -> dict[str, str]:
    return _comment(
        stamp=stamp, text=f"SEAT-WATCHDOG-ALARM seat {seat} stuck at a dialog for 9 min"
    )


_COMMENTS = [
    _comment(stamp="2026-11-14T00:00:00Z", text=_ANCIENT_RECORD),
    _comment(stamp="2026-11-21T00:04:23Z", text=_OLD_RECORD),
    _comment(stamp="2026-11-21T00:10:47Z", text=_NEW_RECORD),
    _alarm(stamp="2026-11-21T01:00:00Z", seat="alpha"),
    _alarm(stamp="2026-11-21T02:00:00Z", seat="bravo"),
    _alarm(stamp="2026-11-21T03:00:00Z", seat="charlie"),
    _alarm(stamp="2026-11-21T04:00:00Z", seat="delta"),
    _comment(
        stamp="2026-11-21T05:00:00Z",
        text="a note that mentions SEAT-WATCHDOG-ALARM only in passing",
    ),
]

_STUB = """#!{python}
import json, sys
args = sys.argv[1:]
args = args[args.index("bd") + 1:]
if args[0] == "comments":
    print(open({fixture!r}).read() if args[1] == "livespec-dev-tooling-6tgd2z" else "[]")
elif args[0] == "show":
    print(json.dumps([{{"status": "backlog", "updated_at": "2026-11-21T00:00:00Z", "metadata": {{}}}}]))
"""


def _exe(*, path: Path, body: str) -> None:
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class _Host:
    """A temporary HOME, a copy of top5 beside stub siblings, and a ledger wrapper stub."""

    def __init__(self, *, tmp_path: Path, comments: list[dict[str, str]] | None) -> None:
        self.home = tmp_path / "home"
        (self.home / "workspace" / "livespec-dev-tooling").mkdir(parents=True)
        self.coordinator = tmp_path / "coordinator"
        self.coordinator.mkdir()
        self.script = self.coordinator / "top5"
        _ = shutil.copy(_TOP5, self.script)
        _exe(path=self.coordinator / "fleet-utilization.sh", body="#!/bin/sh\nexit 0\n")
        fixture = tmp_path / "comments.json"
        _ = fixture.write_text(json.dumps(comments or []), encoding="utf-8")
        self.wrapper = tmp_path / "wrapper.sh"
        if comments is None:
            _exe(path=self.wrapper, body="#!/bin/sh\nexit 0\n")
        else:
            _exe(path=self.wrapper, body=_STUB.format(python=sys.executable, fixture=str(fixture)))

    def backfills(self, *, body: str) -> None:
        _exe(path=self.coordinator / "host-guard-backfills", body=body)

    def output(self) -> list[str]:
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
        return result.stdout.splitlines()

    def section(self, *, head: str) -> list[str]:
        lines = self.output()
        start = next(i for i, ln in enumerate(lines) if ln.startswith(head))
        end = next((i for i in range(start, len(lines)) if not lines[i].strip()), len(lines))
        return [ln.strip() for ln in lines[start + 1 : end]]


@pytest.fixture
def host(tmp_path: Path) -> _Host:
    return _Host(tmp_path=tmp_path, comments=_COMMENTS)


def test_priorities_come_from_the_newest_record_including_priority_zero(host: _Host) -> None:
    lines = [ln for ln in host.output() if ln.startswith("P")]
    labels = [ln.split(" ", 1)[0] for ln in lines]
    assert labels == ["P0", "P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8a", "P9"], lines
    assert lines[0].startswith("P0 no 5-hour limit ever runs out")
    assert lines[1].startswith("P1 fleet-host-guard-escape-valve")
    assert lines[3].startswith("P3 bqnzcm (livespec-dev-tooling-bqnzcm)")
    assert not any("long-closed-plan" in ln or "fleet_host_guard deadlock" in ln for ln in lines)


def test_the_priorities_source_line_names_the_newest_record(host: _Host) -> None:
    assert any(ln.startswith("priorities-record 2026-11-21T00:10:47Z") for ln in host.output())


def test_an_unreadable_ledger_prints_unread_and_the_built_in_list(tmp_path: Path) -> None:
    lines = _Host(tmp_path=tmp_path, comments=None).output()
    assert any(ln.startswith("UNREAD priorities-record:") for ln in lines), lines


def test_the_alarm_section_prints_the_newest_three_alarms_with_timestamps(host: _Host) -> None:
    got = host.section(head="SEAT-WATCHDOG ALARMS")
    assert len(got) == 3, got
    assert got[0].startswith("2026-11-21T02:00:00Z") and "bravo" in got[0]
    assert got[2].startswith("2026-11-21T04:00:00Z") and "delta" in got[2]


def test_the_alarm_section_says_unread_when_the_ledger_cannot_be_read(tmp_path: Path) -> None:
    got = _Host(tmp_path=tmp_path, comments=None).section(head="SEAT-WATCHDOG ALARMS")
    assert got and got[0].startswith("UNREAD"), got


def test_the_backfill_section_prints_the_first_line_only(host: _Host) -> None:
    host.backfills(body="#!/bin/sh\necho 'BACKFILLS: 0 owed'\necho 'second line'\nexit 0\n")
    assert host.section(head="HOST-GUARD BACKFILLS") == ["BACKFILLS: 0 owed"]


def test_the_backfill_section_marks_exit_three_overdue(host: _Host) -> None:
    host.backfills(body="#!/bin/sh\necho 'BACKFILLS: 1 owed 30 h'\nexit 3\n")
    assert host.section(head="HOST-GUARD BACKFILLS") == ["OVERDUE BACKFILLS: 1 owed 30 h"]


def test_the_backfill_section_says_unread_for_an_absent_or_failing_script(host: _Host) -> None:
    absent = host.section(head="HOST-GUARD BACKFILLS")
    assert absent and absent[0].startswith("UNREAD"), absent
    host.backfills(body="#!/bin/sh\necho boom >&2\nexit 2\n")
    failing = host.section(head="HOST-GUARD BACKFILLS")
    assert failing and failing[0].startswith("UNREAD") and "boom" in failing[0], failing
