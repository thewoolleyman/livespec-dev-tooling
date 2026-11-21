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


def _run(
    *, tmp_path: Path, comments: list[str], today: str, extra: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    tenant = tmp_path / "roots" / "demo"
    (tenant / ".beads").mkdir(parents=True, exist_ok=True)
    _ = (tenant / ".beads" / "config.yaml").write_text("dolt.prefix: demo\n", encoding="utf-8")
    items = [{"id": "demo-abc123", "updated_at": "2026-11-21T01:00:00Z"}]
    rows = [{"text": text} for text in comments]
    wrapper = tmp_path / "wrapper.sh"
    _ = wrapper.write_text(
        "#!/bin/sh\n"
        f'echo "$*" >> {tmp_path}/calls.log\n'
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
        [str(_SCRIPT), *(extra or [])],
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
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


def test_default_scan_filters_on_the_label_and_all_does_not(tmp_path: Path) -> None:
    comments = [_ESCAPE.format(due="2026-11-22")]
    _ = _run(tmp_path=tmp_path, comments=comments, today="2026-11-21")
    fast = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "--label host-guard-escape" in fast
    (tmp_path / "calls.log").unlink()
    done = _run(tmp_path=tmp_path, comments=comments, today="2026-11-21", extra=["--all"])
    slow = (tmp_path / "calls.log").read_text(encoding="utf-8")
    assert "--label" not in slow
    assert "1 owed, 0 overdue" in done.stdout


def test_a_tenant_is_read_through_the_launcher_its_livespec_jsonc_declares(tmp_path: Path) -> None:
    """A tenant with its own scoped launcher is not read through the fleet wrapper.

    hetzner-xubuntu-info answers the fleet wrapper with a credential refusal, which read as a tenant
    that could not be read. The script reads `credential_wrapper` from the tenant's `.livespec.jsonc`
    (comments, a `//` inside a string, and a trailing comma included) and runs `bd` through it.
    """
    tenant = tmp_path / "roots" / "scoped"
    (tenant / ".beads").mkdir(parents=True)
    _ = (tenant / ".beads" / "config.yaml").write_text("dolt.prefix: scoped\n", encoding="utf-8")
    _ = (tenant / ".livespec.jsonc").write_text(
        "{\n"
        "  // a comment that mentions credential_wrapper\n"
        '  "docs": "https://example.invalid/a//b",\n'
        '  "credential_wrapper": ["./launcher.sh", "--", "/bin/sh", "-c", "ignored"],\n'
        "}\n",
        encoding="utf-8",
    )
    launcher = tenant / "launcher.sh"
    _ = launcher.write_text(
        '#!/bin/sh\necho launched >> "$HGB_TEST_LOG"\n[ "$1" = "--" ] && shift\nexec "$@"\n',
        encoding="utf-8",
    )
    launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    items = [{"id": "scoped-abc123", "updated_at": "2026-11-21T01:00:00Z"}]
    rows = [{"text": _ESCAPE.format(due="2026-11-22")}]
    stub = bin_dir / "bd"
    _ = stub.write_text(
        "#!/bin/sh\n"
        'case "$*" in\n'
        f"  *list*) cat <<'EOF'\n{json.dumps(items)}\nEOF\n;;\n"
        f"  *comments*) cat <<'EOF'\n{json.dumps(rows)}\nEOF\n;;\n"
        "esac\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)
    log = tmp_path / "launcher.log"
    env = {key: value for key, value in os.environ.items() if key != "HGB_LEDGER_WRAPPER"} | {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "HGB_ROOTS": str(tmp_path / "roots"),
        "HGB_TODAY": "2026-11-21",
        "HGB_TEST_LOG": str(log),
    }
    done = subprocess.run(
        [str(_SCRIPT)], env=env, capture_output=True, text=True, check=False, timeout=60
    )
    assert done.returncode == 0, done.stderr
    assert "1 owed, 0 overdue, 0 tenant(s) UNREAD" in done.stdout
    assert log.read_text(encoding="utf-8").count("launched") >= 2


def test_a_tenant_whose_declared_launcher_is_not_installed_falls_back_to_the_fleet_wrapper(
    tmp_path: Path,
) -> None:
    """A launcher declared for another host is not a reason to lose the tenant on this one."""
    tenant = tmp_path / "roots" / "elsewhere"
    (tenant / ".beads").mkdir(parents=True)
    _ = (tenant / ".beads" / "config.yaml").write_text("dolt.prefix: elsewhere\n", encoding="utf-8")
    _ = (tenant / ".livespec.jsonc").write_text(
        '{"credential_wrapper": ["/nonexistent/with-elsewhere-env.sh", "--"]}\n', encoding="utf-8"
    )
    items = [{"id": "elsewhere-abc123", "updated_at": "2026-11-21T01:00:00Z"}]
    rows = [{"text": _ESCAPE.format(due="2026-11-22")}]
    fleet = tmp_path / "fleet.sh"
    _ = fleet.write_text(
        "#!/bin/sh\n"
        '[ "$1" = "--" ] && shift\n'
        'case "$*" in\n'
        f"  *list*) cat <<'EOF'\n{json.dumps(items)}\nEOF\n;;\n"
        f"  *comments*) cat <<'EOF'\n{json.dumps(rows)}\nEOF\n;;\n"
        "esac\n",
        encoding="utf-8",
    )
    fleet.chmod(fleet.stat().st_mode | stat.S_IXUSR)
    env = {key: value for key, value in os.environ.items() if key != "HGB_LEDGER_WRAPPER"} | {
        "HGB_DEFAULT_WRAPPER": str(fleet),
        "HGB_ROOTS": str(tmp_path / "roots"),
        "HGB_TODAY": "2026-11-21",
    }
    done = subprocess.run(
        [str(_SCRIPT)], env=env, capture_output=True, text=True, check=False, timeout=60
    )
    assert done.returncode == 0, done.stderr
    assert "1 owed, 0 overdue, 0 tenant(s) UNREAD" in done.stdout


def _failing_tenant_run(
    *, tmp_path: Path, name: str, message: str
) -> subprocess.CompletedProcess[str]:
    tenant = tmp_path / "roots" / name
    (tenant / ".beads").mkdir(parents=True)
    _ = (tenant / ".beads" / "config.yaml").write_text("dolt.prefix: x\n", encoding="utf-8")
    wrapper = tmp_path / "failing.sh"
    _ = wrapper.write_text(f"#!/bin/sh\necho '{message}' >&2\nexit 1\n", encoding="utf-8")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IXUSR)
    env = {
        **os.environ,
        "HGB_LEDGER_WRAPPER": str(wrapper),
        "HGB_ROOTS": str(tmp_path / "roots"),
        "HGB_TODAY": "2026-11-21",
    }
    return subprocess.run(
        [str(_SCRIPT)], env=env, capture_output=True, text=True, check=False, timeout=60
    )


def test_a_tenant_with_no_beads_database_here_is_not_applicable_not_unread(tmp_path: Path) -> None:
    done = _failing_tenant_run(
        tmp_path=tmp_path, name="resume", message="Error: no beads database found"
    )
    assert done.returncode == 0, done.stderr
    assert "0 tenant(s) UNREAD, 1 not applicable" in done.stdout
    assert "N/A" in done.stdout
    assert "no beads database on this host" in done.stdout


def test_a_tenant_read_on_another_host_names_that_host_and_its_owner(tmp_path: Path) -> None:
    done = _failing_tenant_run(
        tmp_path=tmp_path, name="homelab", message="Missing the installed homelab launcher"
    )
    assert done.returncode == 0, done.stderr
    assert "0 tenant(s) UNREAD, 1 read elsewhere" in done.stdout
    assert "read on vps, owner vps-control-node-ops" in done.stdout
