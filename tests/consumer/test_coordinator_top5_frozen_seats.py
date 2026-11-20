"""Scenario "top5 prints a FROZEN-SEATS section for seats stuck at an Enter-to-select dialog".

Rule PERMISSION-PROMPT (`.ai/coordinator-duties.md`): on 2026-11-20 the whole fleet sat frozen
for 14 h at a Remote Control dialog and nobody could see it. `scripts/coordinator/top5` now
prints, before RULES-CHANGED, every herdr seat whose last screen lines carry the dialog footer.

These run a copy of the real script against a stub `herdr` on PATH that answers from a JSON
fixture, with a ledger wrapper stub that answers nothing. No live herdr or ledger is read.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TOP5 = _REPO_ROOT / "scripts" / "coordinator" / "top5"
_DIALOG = "Enter to select · Esc to cancel"
_STUB = """#!/usr/bin/env python3
import json, os, sys, time
fx = json.load(open(os.environ["STUB_FIXTURE"]))
argv = sys.argv[1:]
if argv[:1] == ["--machine"]:
    argv = argv[2:]
if argv[:2] == ["machine", "list"]:
    print("\\n".join(fx["machines"]))
    sys.exit(0)
if argv[:2] == ["pane", "read"]:
    if fx.get("sleep"):
        time.sleep(fx["sleep"])
    print(fx["screens"].get(argv[2], ""))
    sys.exit(0)
print(json.dumps({"id": "x", "result": fx[argv[0] + "_" + argv[1]]}))
"""


def _agent(*, pane: str, title: str) -> dict[str, str]:
    return {
        "pane_id": pane,
        "tab_id": f"w1:t{pane}",
        "workspace_id": "w1",
        "agent_status": "done",
        "terminal_title_stripped": title,
    }


def _fixture(*, panes: dict[str, tuple[str, str]], sleep: float = 0) -> dict[str, object]:
    return {
        "machines": [],
        "sleep": sleep,
        "agent_list": {"agents": [_agent(pane=p, title=t) for p, (t, _) in panes.items()]},
        "tab_list": {"tabs": [{"tab_id": f"w1:t{p}", "label": t} for p, (t, _) in panes.items()]},
        "workspace_list": {"workspaces": [{"workspace_id": "w1", "label": "ws"}]},
        "screens": {p: s for p, (_, s) in panes.items()},
    }


def _run(*, tmp_path: Path, fixture: dict[str, object]) -> str:
    home = tmp_path / "home"
    home.mkdir()
    coordinator = tmp_path / "coordinator"
    coordinator.mkdir()
    script = coordinator / "top5"
    _ = shutil.copy(_TOP5, script)
    fleet = coordinator / "fleet-utilization.sh"
    _ = fleet.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    wrapper = tmp_path / "wrapper.sh"
    _ = wrapper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    herdr = bindir / "herdr"
    _ = herdr.write_text(_STUB, encoding="utf-8")
    for path in (herdr, fleet, wrapper):
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
    fixture_path = tmp_path / "fixture.json"
    _ = fixture_path.write_text(json.dumps(fixture), encoding="utf-8")
    env = {
        "HOME": str(home),
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "TOP5_LEDGER_WRAPPER": str(wrapper),
        "STUB_FIXTURE": str(fixture_path),
        "TOP5_FROZEN_CALL_TIMEOUT_S": "1",
        "TOP5_FROZEN_SECTION_TIMEOUT_S": "5",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    result = subprocess.run(
        ["bash", str(script), "--seat", "throughput-plans-coordinator"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    return result.stdout


def test_footer_match_prints_frozen_before_rules_changed(*, tmp_path: Path) -> None:
    out = _run(
        tmp_path=tmp_path,
        fixture=_fixture(
            panes={"p1": ("worker-a", f"x\n{_DIALOG}"), "p2": ("worker-b", "all quiet")}
        ),
    )
    assert out.startswith('FROZEN-SEATS (a seat at an "Enter to select" dialog is frozen;')
    assert f"FROZEN local/ws/worker-a (p1) last screen: {_DIALOG}" in out
    assert "worker-b" not in out
    assert out.index("FROZEN local/") < out.index("RULES-CHANGED")


def test_own_pane_and_resume_updates_are_skipped(*, tmp_path: Path) -> None:
    out = _run(
        tmp_path=tmp_path,
        fixture=_fixture(
            panes={
                "p1": ("throughput-plans-coordinator", _DIALOG),
                "p2": ("resume-updates", _DIALOG),
            }
        ),
    )
    assert "FROZEN-SEATS: none" in out
    assert "FROZEN local" not in out


def test_footer_needs_esc_and_must_be_in_the_last_twelve_lines(*, tmp_path: Path) -> None:
    old = "\n".join([_DIALOG] + ["filler"] * 12)
    out = _run(
        tmp_path=tmp_path,
        fixture=_fixture(panes={"p1": ("a", old), "p2": ("b", "Enter to select only")}),
    )
    assert "FROZEN-SEATS: none" in out


def test_slow_pane_read_prints_unread_and_top5_continues(*, tmp_path: Path) -> None:
    out = _run(
        tmp_path=tmp_path,
        fixture=_fixture(panes={"p1": ("worker-a", _DIALOG)}, sleep=3),
    )
    assert "UNREAD local/ws/worker-a (p1)" in out
    assert "INCIDENT MODE" in out


def test_idle_fleet_reports_no_timestamp(*, tmp_path: Path) -> None:
    out = _run(tmp_path=tmp_path, fixture=_fixture(panes={"p1": ("a", "quiet")}))
    assert "IDLE-FLEET: UNREAD no timestamp in herdr agent list" in out


def test_idle_fleet_flags_an_old_last_turn(*, tmp_path: Path) -> None:
    fixture = _fixture(panes={"p1": ("a", "quiet")})
    agents = fixture["agent_list"]
    assert isinstance(agents, dict)
    agents["agents"][0]["completed_at"] = "2020-01-01T00:00:00Z"
    out = _run(tmp_path=tmp_path, fixture=fixture)
    assert "IDLE-FLEET: oldest last turn ended" in out
    assert "(a)" in out
