"""Behavioural and shape tests for the breakage_pass host-timer role (bd-ib-voazyv, S3).

The runner script is executed for real against a stub dispatcher, so the closing
journal line and the success marker are observed rather than read from the source.
The role's own files are read for the properties the Definition of Done and the
2026-11-13 reboot note require: a schedule of at most 30 minutes, stable paths, and a
hold that starts nothing until the host variables enable it.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[1]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "breakage_pass"
_RUNNER = _ROLE / "files" / "livespec-breakage-pass"
_CACHE_SEGMENT = "/.claude/plugins/cache/"


def _stub_plugin(*, tmp_path: Path, body: str) -> Path:
    scripts = tmp_path / "plugin" / "scripts" / "bin"
    scripts.mkdir(parents=True)
    _ = (scripts / "dispatcher.py").write_text(body, encoding="utf-8")
    return tmp_path / "plugin"


def _run_runner(*, tmp_path: Path, body: str) -> tuple[subprocess.CompletedProcess[str], Path]:
    plugin = _stub_plugin(tmp_path=tmp_path, body=body)
    state = tmp_path / "state"
    state.mkdir()
    done = subprocess.run(
        [
            "/bin/bash",
            str(_RUNNER),
            "alpha",
            str(tmp_path),
            str(plugin),
            "/usr/bin/python3",
            str(state),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return done, state


def test_a_passing_pass_journals_its_verdicts_then_a_result_line_and_marks_success(
    *, tmp_path: Path
) -> None:
    done, state = _run_runner(tmp_path=tmp_path, body="print('breakage-pass wf.yml run=u green')\n")

    assert done.returncode == 0
    assert done.stdout.splitlines() == [
        "breakage-pass wf.yml run=u green",
        "breakage-pass-result repo=alpha rc=0",
    ]
    assert (state / "alpha.last-success").is_file()


def test_a_failing_pass_keeps_its_status_and_leaves_no_success_marker(*, tmp_path: Path) -> None:
    done, state = _run_runner(tmp_path=tmp_path, body="import sys\nsys.exit(1)\n")

    assert done.returncode == 1
    assert done.stdout.splitlines() == ["breakage-pass-result repo=alpha rc=1"]
    assert not (state / "alpha.last-success").exists()


def test_a_repository_watching_no_workflow_still_journals_the_result_line(
    *, tmp_path: Path
) -> None:
    done, _ = _run_runner(tmp_path=tmp_path, body="")

    assert done.stdout == "breakage-pass-result repo=alpha rc=0\n"


def _defaults() -> dict[str, object]:
    loaded: dict[str, object] = yaml.safe_load(
        (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
    )
    return loaded


def test_the_role_defaults_hold_the_timers_and_start_nothing() -> None:
    defaults = _defaults()

    assert defaults["breakage_pass_enabled"] is False
    assert defaults["breakage_pass_repos"] == []


def test_the_schedule_stays_within_thirty_minutes() -> None:
    defaults = _defaults()
    interval = int(str(defaults["breakage_pass_interval_minutes"]))
    timeout = int(str(defaults["breakage_pass_timeout_seconds"]))
    stop = int(str(defaults["breakage_pass_stop_timeout_seconds"]))

    assert stop == 90
    assert interval + (timeout + stop) / 60 <= 30
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "breakage_pass_stop_timeout_seconds | int" in tasks
    timer = (_ROLE / "templates" / "breakage-pass.timer.j2").read_text(encoding="utf-8")
    assert "OnUnitInactiveSec={{ breakage_pass_interval_minutes }}min" in timer


def test_no_role_default_path_names_a_versioned_plugin_cache_or_tmp() -> None:
    defaults = _defaults()

    for key in (
        "breakage_pass_plugin_root",
        "breakage_pass_runner_bin",
        "breakage_pass_state_dir",
    ):
        value = str(defaults[key])
        assert _CACHE_SEGMENT not in value
        assert not value.startswith("/tmp")


def test_the_service_runs_the_pass_under_the_tenant_credential_wrapper() -> None:
    service = (_ROLE / "templates" / "breakage-pass.service.j2").read_text(encoding="utf-8")

    assert (
        "ExecStart={{ breakage_pass_tenant_wrap_bin }} -- {{ breakage_pass_runner_bin }}" in service
    )
    assert "Environment=TW_REPO={{ item.repo }}" in service
    assert "TimeoutStartSec={{ breakage_pass_timeout_seconds }}" in service


def test_a_pass_cannot_overlap_itself() -> None:
    service = (_ROLE / "templates" / "breakage-pass.service.j2").read_text(encoding="utf-8")
    timer = (_ROLE / "templates" / "breakage-pass.timer.j2").read_text(encoding="utf-8")

    assert "Type=oneshot" in service
    assert "TimeoutStopSec={{ breakage_pass_stop_timeout_seconds }}" in service
    # Counted from the end of the previous pass, so a running pass is never restarted.
    assert "OnUnitInactiveSec=" in timer
    assert "OnCalendar" not in timer
    assert "OnUnitActiveSec" not in timer


def test_the_role_preflights_each_repository_and_guards_arming_under_check_mode() -> None:
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")

    assert "'/.livespec.jsonc'" in tasks
    assert "/scripts/bin/dispatcher.py" in tasks
    assert "livespec-tenant-wrap.sh --resolve" in tasks
    assert "check_mode: false" in tasks
    assert "not ansible_check_mode or item.stat.exists" in tasks


def test_the_staleness_unit_alerts_through_on_failure_and_the_dev_host_names_the_target() -> None:
    service = (_ROLE / "templates" / "breakage-pass-staleness.service.j2").read_text(
        encoding="utf-8"
    )
    host_vars = (_ANSIBLE / "inventory" / "host_vars" / "vps.yml").read_text(encoding="utf-8")

    assert "OnFailure={{ breakage_pass_staleness_on_failure }}" in service
    assert re.search(
        r"^breakage_pass_staleness_on_failure: host-unit-alert@%n\.service$",
        host_vars,
        re.MULTILINE,
    )


def test_the_revert_removes_unit_files_and_the_docs_say_so_and_name_the_apply_order() -> None:
    tasks = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
    docs = (_ROLE / "HOST_VARS.md").read_text(encoding="utf-8")

    assert "state: absent" in tasks
    assert "breakage_pass_unwanted | length > 0" in tasks
    assert "NOT currently installed" in docs
    assert "`reconcile_runs` must be reviewed and applied first" in docs
    assert "removes every breakage pass unit file" in docs


def test_the_dev_host_playbook_carries_the_role_and_the_host_variables_enable_it() -> None:
    playbook = (_ANSIBLE / "dev-host.yml").read_text(encoding="utf-8")
    host_vars = (_ANSIBLE / "inventory" / "host_vars" / "vps.yml").read_text(encoding="utf-8")

    assert re.search(r"- role: breakage_pass\n\s+tags: \[breakage_pass\]", playbook)
    assert re.search(r"^breakage_pass_enabled: true$", host_vars, re.MULTILINE)
    assert "/home/ubuntu/workspace/livespec-orchestrator-beads-fabro" in host_vars
