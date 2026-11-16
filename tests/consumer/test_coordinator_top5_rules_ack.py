"""Scenario "top5 prints RULES-CHANGED first and exits non-zero until acknowledged".

Rule RULES-ACK (`.ai/coordinator-duties.md` §3): every coordinator tick runs
`scripts/coordinator/top5` first. Its RULES-CHANGED section shows what changed in the
seat's rules since its last `--ack` (the duties file and the charter at origin/master,
and new SCOPE / MAINTAINER / RULE / VERBATIM comments on its watched epics), and the
script exits 3 until the seat acknowledges it.

These run the real script with `--rules-only` against a temporary HOME: an origin repo
and its clone at `~/workspace/livespec-dev-tooling`, a pass-through stub for the ledger
credential wrapper, and a stub `bd` on PATH that serves comments from JSON files. The
live ledger, cluster and repository are never read.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOP5 = _REPO_ROOT / "scripts" / "coordinator" / "top5"
_DUTIES = ".ai/coordinator-duties.md"
_CHARTER = "plan/legacy-coordinator-agent/research/001-charter-legacy-coordinator-agent.md"
_EPIC = "livespec-dev-tooling-6tgd2z"
_ACK_TIME = "2026-11-16T12:00:00Z"
_LATER = "2026-11-16T16:11:37Z"
_EARLIER = "2026-11-16T09:00:00Z"


def _exe(*, path: Path, body: str) -> None:
    _ = path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _git(*args: str, cwd: Path) -> None:
    _ = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


class _Host:
    """A temporary HOME holding the fleet layout top5 reads."""

    def __init__(self, *, tmp_path: Path) -> None:
        self.home = tmp_path / "home"
        self.origin = tmp_path / "origin.git"
        self.clone = self.home / "workspace" / "livespec-dev-tooling"
        self.comments = tmp_path / "comments"
        self.bin = tmp_path / "bin"
        for directory in (self.home, self.comments, self.bin):
            directory.mkdir(parents=True)
        _ = subprocess.run(
            ["git", "init", "--quiet", "--bare", "--initial-branch=master", str(self.origin)],
            check=True,
        )
        _ = subprocess.run(
            ["git", "clone", "--quiet", str(self.origin), str(self.clone)], check=True
        )
        _git("checkout", "--quiet", "-B", "master", cwd=self.clone)
        self.wrapper = self.bin / "with-livespec-env.sh"
        _exe(path=self.wrapper, body='#!/bin/sh\n[ "$1" = "--" ] && shift\nexec "$@"\n')
        _exe(path=self.bin / "bd", body=f'#!/bin/sh\ncat "{self.comments}/$2.json"\n')
        self.set_comments([])
        self.push(duties="# Duties\n\nRule P1: run top5 first.\n", charter="# Charter\n")

    def push(self, *, duties: str, charter: str) -> None:
        for rel, text in ((_DUTIES, duties), (_CHARTER, charter)):
            path = self.clone / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            _ = path.write_text(text, encoding="utf-8")
        _git("add", "-A", cwd=self.clone)
        _git("commit", "--quiet", "-m", "rules", cwd=self.clone)
        _git("push", "--quiet", "origin", "master", cwd=self.clone)

    def set_comments(self, comments: list[dict[str, str]]) -> None:
        _ = (self.comments / f"{_EPIC}.json").write_text(json.dumps(comments), encoding="utf-8")

    def ack_file(self) -> Path:
        return (
            self.home
            / ".local"
            / "state"
            / "livespec-coordinator"
            / "rules-ack-legacy-coordinator-agent.json"
        )

    def top5(self, *args: str) -> subprocess.CompletedProcess[str]:
        env = {
            "HOME": str(self.home),
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "TOP5_LEDGER_WRAPPER": str(self.wrapper),
            "GIT_CONFIG_NOSYSTEM": "1",
        }
        return subprocess.run(
            ["bash", str(_TOP5), *args],
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )

    def acked(self) -> None:
        assert self.top5("--rules-only").returncode == 3
        assert self.top5("--ack").returncode == 0
        record = json.loads(self.ack_file().read_text(encoding="utf-8"))
        record["acked_at"] = _ACK_TIME
        record["epics"] = {_EPIC: _ACK_TIME}
        _ = self.ack_file().write_text(json.dumps(record), encoding="utf-8")


@pytest.fixture
def host(tmp_path: Path) -> _Host:
    return _Host(tmp_path=tmp_path)


def test_a_fresh_session_with_no_ack_is_told_to_read_in_full_and_exits_3(host: _Host) -> None:
    result = host.top5("--rules-only")
    assert result.returncode == 3, result.stderr
    assert (
        result.stdout.splitlines()[0]
        == "RULES-CHANGED: no ack recorded; full read required (fresh session)"
    )
    assert not host.ack_file().exists()


def test_ack_records_the_state_and_exits_0(host: _Host) -> None:
    assert host.top5("--rules-only").returncode == 3
    result = host.top5("--ack")
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("RULES-ACK seat legacy-coordinator-agent at ")
    record = json.loads(host.ack_file().read_text(encoding="utf-8"))
    assert record["seat"] == "legacy-coordinator-agent"
    assert record["duties"]
    assert record["charters"][_CHARTER]
    assert _EPIC in record["epics"]


def test_unchanged_rules_print_one_line_and_exit_0(host: _Host) -> None:
    host.acked()
    host.set_comments(
        [
            {
                "created_at": _EARLIER,
                "author": "a",
                "text": "RULE OLD: already acknowledged",
                "id": "1",
            },
            {
                "created_at": _LATER,
                "author": "a",
                "text": "progress note with no keyword",
                "id": "2",
            },
        ]
    )
    result = host.top5("--rules-only")
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip().splitlines() == [f"RULES-CHANGED: none since ack {_ACK_TIME}"]


def test_a_changed_duties_blob_prints_its_diff_and_exits_3_until_acked(host: _Host) -> None:
    host.acked()
    host.push(
        duties="# Duties\n\nRule P1: run top5 first.\nRule FLAKE: give a flake a bounded retry.\n",
        charter="# Charter\n",
    )
    result = host.top5("--rules-only")
    assert result.returncode == 3, result.stdout + result.stderr
    lines = result.stdout.splitlines()
    assert lines[0].startswith(
        f"RULES-CHANGED (seat legacy-coordinator-agent; since ack {_ACK_TIME};"
    )
    assert any(line.startswith(f"duties {_DUTIES} ") for line in lines)
    assert "  +Rule FLAKE: give a flake a bounded retry." in lines
    assert not any(line.startswith("charter ") for line in lines)
    assert host.top5("--ack").returncode == 0
    assert host.top5("--rules-only").returncode == 0


def test_new_rule_comments_and_a_charter_change_are_shown(host: _Host) -> None:
    host.acked()
    host.push(
        duties="# Duties\n\nRule P1: run top5 first.\n", charter="# Charter\n\nNew charter line.\n"
    )
    host.set_comments(
        [
            {
                "created_at": _LATER,
                "author": "lca",
                "text": "MAINTAINER VERBATIM: flakes get a root fix",
                "id": "1",
            },
            {
                "created_at": _LATER,
                "author": "lca",
                "text": "CORRECTION under RULE FLAKE\nsecond line",
                "id": "2",
            },
            {
                "created_at": _LATER,
                "author": "lca",
                "text": "status only\nRULE on a later line",
                "id": "3",
            },
        ]
    )
    result = host.top5("--rules-only")
    assert result.returncode == 3, result.stdout + result.stderr
    out = result.stdout
    assert f"comments {_EPIC}: 2 new rule comment(s) since {_ACK_TIME}" in out
    assert "MAINTAINER VERBATIM: flakes get a root fix" in out
    assert "RULE on a later line" not in out
    assert f"charter {_CHARTER} " in out
    assert "  +New charter line." in out


def test_the_section_is_capped_at_80_lines_and_each_comment_at_600_chars(host: _Host) -> None:
    host.acked()
    big = "".join(f"Rule line {n}\n" for n in range(300))
    host.push(duties="# Duties\n\n" + big, charter="# Charter\n")
    long_text = "RULE LONG: " + "x" * 1000
    host.set_comments(
        [
            {"created_at": _LATER, "author": "lca", "text": long_text, "id": str(n)}
            for n in range(40)
        ]
    )
    result = host.top5("--rules-only")
    assert result.returncode == 3, result.stdout + result.stderr
    section = result.stdout.rstrip("\n").splitlines()
    assert len(section) <= 80
    assert any(line.startswith("  +") and "more lines" in line for line in section)
    shown = [line for line in section if "RULE LONG: " in line]
    assert shown
    assert all(len(line.split(": ", 1)[1]) <= 600 for line in shown)
    assert any(f"+{len(long_text) - 600} more chars" in line for line in section)


def test_ack_keeps_a_change_that_landed_after_the_last_display(host: _Host) -> None:
    host.acked()
    host.push(duties="# Duties\n\nRule A.\n", charter="# Charter\n")
    assert host.top5("--rules-only").returncode == 3
    host.push(
        duties="# Duties\n\nRule A.\nRule B landed after the display.\n", charter="# Charter\n"
    )
    assert host.top5("--ack").returncode == 0
    result = host.top5("--rules-only")
    assert result.returncode == 3
    assert "  +Rule B landed after the display." in result.stdout.splitlines()
