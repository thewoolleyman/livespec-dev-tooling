"""Scenario "an escape-valve use with no backfill is reported, and an overdue one exits 3".

Plan fleet-host-guard-escape-valve (livespec-dev-tooling-twdyzy): `scripts/coordinator/host-guard-backfills`
lists every `HOST-GUARD-ESCAPE:` ledger comment that no later `HOST-GUARD-BACKFILL:` comment answers, and
marks one past its `backfill-due` date OVERDUE. These run the real script against a ledger wrapper stub
that answers `bd list` and `bd comments` from fixtures, in a temporary tenant directory. No live ledger
is read.
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

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "coordinator" / "host-guard-backfills"
_ESCAPE = (
    "HOST-GUARD-ESCAPE: command=just ansible-apply x.yml reason=false refusal backfill-due={due}"
)
_BACKFILL = "HOST-GUARD-BACKFILL: pr=livespec-dev-tooling#1"


def _run(*, tmp_path: Path, comments: list[str], today: str) -> subprocess.CompletedProcess[str]:
    tenant = tmp_path / "roots" / "demo"
    (tenant / ".beads").mkdir(parents=True)
    _ = (tenant / ".beads" / "config.yaml").write_text("dolt.prefix: demo\n", encoding="utf-8")
    items = [{"id": "demo-abc123", "updated_at": "2026-11-21T01:00:00Z"}]
    rows = [{"text": text} for text in comments]
    wrapper = tmp_path / "wrapper.sh"
    _ = wrapper.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        f"  *list*) cat <<'EOF'\n{json.dumps(items)}\nEOF\n;;\n"
        f"  *comments*) cat <<'EOF'\n{json.dumps(rows)}\nEOF\n;;\n"
        "esac\n",
        encoding="utf-8",
    )
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    env = {
        **os.environ,
        "HGB_LEDGER_WRAPPER": str(wrapper),
        "HGB_ROOTS": str(tmp_path / "roots"),
        "HGB_TODAY": today,
    }
    return subprocess.run(
        [str(_SCRIPT)], env=env, capture_output=True, text=True, check=False, timeout=60
    )


def test_unanswered_escape_past_its_due_date_is_overdue_and_exits_3(tmp_path: Path) -> None:
    done = _run(tmp_path=tmp_path, comments=[_ESCAPE.format(due="2026-11-22")], today="2026-11-23")
    assert done.returncode == 3, done.stderr
    assert "1 owed, 1 overdue" in done.stdout
    assert "OVERDUE demo-abc123 due 2026-11-22" in done.stdout


def test_unanswered_escape_before_its_due_date_is_owed_not_overdue(tmp_path: Path) -> None:
    done = _run(tmp_path=tmp_path, comments=[_ESCAPE.format(due="2026-11-22")], today="2026-11-21")
    assert done.returncode == 0, done.stderr
    assert "1 owed, 0 overdue" in done.stdout
    assert "owed demo-abc123 due 2026-11-22" in done.stdout


def test_a_later_backfill_comment_answers_the_escape(tmp_path: Path) -> None:
    done = _run(
        tmp_path=tmp_path,
        comments=[_ESCAPE.format(due="2026-11-22"), _BACKFILL],
        today="2026-11-25",
    )
    assert done.returncode == 0, done.stderr
    assert "0 owed, 0 overdue" in done.stdout
