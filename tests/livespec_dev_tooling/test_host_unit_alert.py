"""Tests for role `host_unit_alert` and the units routed to it (livespec-dev-tooling-l7f72q).

A unit that a livespec-dev-tooling role installs alerts through this repository's
`host-unit-alert@` template, never through dolt-server's `dolt-backup-alert@`,
which reports every failure as a dolt backup failure. On 2026-11-14 a stale
reconcile pass mailed the operator "dolt-backup run failed" while every backup
was succeeding.

The script runs against a fake `curl`, `journalctl` and `hostname` on PATH, each
alert state is exercised, and the wiring is read from the committed role
defaults and host variables.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "host_unit_alert"
_SCRIPT = _ROLE / "files" / "host-unit-alert"
_UNIT = "reconcile-runs-staleness.service"
_HOST = "fixture-host"
_KEY = "fixture-ingest-key"
_TOKEN = "fixture-ntfy-token"
# Trigger 9HKs4W3UYN8, "dolt-backup run failed", counts events whose source is
# one of these (dolt-server runbooks/alerting.md).
_BACKUP_TRIGGER_SOURCES = frozenset({"backup-sync", "onfailure"})

_FAKE_CURL = """#!/usr/bin/env bash
# Records each call: argv as JSON lines, stdin (the --config secrets) as text.
n=$(find "$FAKE_LOG" -name 'call-*.argv' | wc -l)
printf '%s\\n' "$@" > "$FAKE_LOG/call-$n.argv"
cat > "$FAKE_LOG/call-$n.stdin"
for arg in "$@"; do
  case "$arg" in
    *"/1/events/"*) exit "${FAKE_HONEYCOMB_EXIT:-0}" ;;
    *"/fixture-topic") exit "${FAKE_NTFY_EXIT:-0}" ;;
  esac
done
exit 0
"""


def _fake_bin(*, root: Path) -> Path:
    bin_dir = root / "bin"
    bin_dir.mkdir()
    fakes = {
        "curl": _FAKE_CURL,
        "journalctl": "#!/bin/sh\necho 'fixture journal line: stale tenant'\n",
        "hostname": f"#!/bin/sh\necho {_HOST}\n",
    }
    for name, text in fakes.items():
        path = bin_dir / name
        _ = path.write_text(text, encoding="utf-8")
        path.chmod(0o755)
    return bin_dir


def _run(*, tmp_path: Path, env: dict[str, str]) -> tuple[int, list[dict[str, object]]]:
    log = tmp_path / "log"
    log.mkdir()
    bin_dir = _fake_bin(root=tmp_path)
    base = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "FAKE_LOG": str(log)}
    done = subprocess.run(
        [str(_SCRIPT), _UNIT],
        env=base | env,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    calls = [
        {
            "argv": argv.read_text(encoding="utf-8").splitlines(),
            "stdin": argv.with_suffix(".stdin").read_text(encoding="utf-8"),
        }
        for argv in sorted(log.glob("call-*.argv"))
    ]
    return done.returncode, calls


_HONEYCOMB = {
    "HONEYCOMB_INGEST_KEY": _KEY,
    "HONEYCOMB_DATASET": "fixture-dataset",
    "HONEYCOMB_API": "https://honeycomb.invalid",
}
_NTFY = {
    "ALERT_NTFY_TOPIC": "fixture-topic",
    "ALERT_NTFY_SERVER": "https://ntfy.invalid",
    "ALERT_NTFY_TOKEN": _TOKEN,
    "ALERT_EMAIL": "operator@example.invalid",
}


def _call_to(*, calls: list[dict[str, object]], url_part: str) -> dict[str, object]:
    matches = [call for call in calls if any(url_part in arg for arg in call["argv"])]  # type: ignore[union-attr]
    assert len(matches) == 1, calls
    return matches[0]


def _event(*, call: dict[str, object]) -> dict[str, object]:
    argv: list[str] = call["argv"]  # type: ignore[assignment]
    return json.loads(argv[argv.index("-d") + 1])


def test_a_failed_unit_raises_one_event_and_one_push_naming_the_unit_and_host(
    tmp_path: Path,
) -> None:
    code, calls = _run(tmp_path=tmp_path, env=_HONEYCOMB | _NTFY)
    assert code == 0
    honeycomb = _call_to(calls=calls, url_part="https://honeycomb.invalid/1/events/fixture-dataset")
    event = _event(call=honeycomb)
    assert event["unit"] == _UNIT
    assert event["host"] == _HOST
    assert (event["name"], event["outcome"]) == ("host-unit-failure", "unit_failure")
    # The dolt-backup failure trigger never counts it.
    assert event["source"] not in _BACKUP_TRIGGER_SOURCES
    assert "backup" not in json.dumps(event)
    ntfy = _call_to(calls=calls, url_part="https://ntfy.invalid/fixture-topic")
    assert f"Title: {_HOST}: {_UNIT} failed" in ntfy["argv"]  # type: ignore[operator]
    for call in calls:
        # Secrets reach curl on stdin, never in its argv.
        assert not any(_KEY in arg or _TOKEN in arg for arg in call["argv"])  # type: ignore[union-attr]
    assert f"X-Honeycomb-Team: {_KEY}" in honeycomb["stdin"]  # type: ignore[operator]
    assert f"Authorization: Bearer {_TOKEN}" in ntfy["stdin"]  # type: ignore[operator]


@pytest.mark.parametrize(
    ("env", "honeycomb_exit", "ntfy_exit", "expected"),
    [
        ({}, "0", "0", 1),
        (_HONEYCOMB | _NTFY, "22", "22", 1),
        (_HONEYCOMB | _NTFY, "22", "0", 0),
        (_HONEYCOMB | _NTFY, "0", "22", 0),
        (_HONEYCOMB, "0", "0", 0),
        (_NTFY, "0", "0", 0),
    ],
    ids=[
        "no-channel-configured",
        "every-channel-fails",
        "honeycomb-fails-ntfy-delivers",
        "ntfy-fails-honeycomb-delivers",
        "honeycomb-only",
        "ntfy-only",
    ],
)
def test_the_alert_fails_only_when_no_channel_accepted_it(
    tmp_path: Path, env: dict[str, str], honeycomb_exit: str, ntfy_exit: str, expected: int
) -> None:
    fakes = {"FAKE_HONEYCOMB_EXIT": honeycomb_exit, "FAKE_NTFY_EXIT": ntfy_exit}
    code, _ = _run(tmp_path=tmp_path, env=env | fakes)
    assert code == expected


def _yaml(*, path: Path) -> dict[str, object]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_the_units_roles_install_route_their_failure_to_the_host_unit_alert() -> None:
    template = _yaml(path=_ROLE / "defaults" / "main.yml")["host_unit_alert_unit"]
    prefix = str(template).removesuffix(".service")
    host_vars = _yaml(path=_ANSIBLE / "inventory" / "host_vars" / "vps.yml")
    assert str(host_vars["reconcile_runs_staleness_on_failure"]).startswith(prefix)
    recipients = _yaml(
        path=_ANSIBLE / "roles" / "honeycomb_trigger_recipients_check" / "defaults" / "main.yml"
    )
    assert recipients["honeycomb_trigger_recipients_check_alert_unit"] == template
    assert str(recipients["honeycomb_trigger_recipients_check_alert_target"]).startswith(prefix)
    play = (_ANSIBLE / "dev-host.yml").read_text(encoding="utf-8")
    # Installed before the roles whose alert-unit checks look for it.
    assert play.index("role: host_unit_alert") < play.index(
        "role: honeycomb_trigger_recipients_check"
    )
    assert play.index("role: host_unit_alert") < play.index("role: reconcile_runs")


def test_no_role_or_host_var_routes_a_failure_to_the_dolt_backup_alert() -> None:
    offending = [
        f"{path.relative_to(_REPO_ROOT)}:{number}"
        for path in sorted(_ANSIBLE.rglob("*"))
        if path.suffix in {".yml", ".yaml", ".j2"}
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if "dolt-backup-alert@" in line and not line.lstrip().startswith("#")
    ]
    assert offending == []


def test_the_role_refuses_a_host_with_no_alert_channel_before_changing_it() -> None:
    tasks = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    assert isinstance(tasks, list)
    probe, refusal = tasks[0], tasks[1]
    argv = probe["ansible.builtin.command"]["argv"]
    assert argv[-1] == "{{ host_unit_alert_env_file }}"
    assert "HONEYCOMB_INGEST_KEY" in argv[-2]
    assert "ALERT_NTFY_TOPIC" in argv[-2]
    assert probe["check_mode"] is False
    assert refusal["ansible.builtin.assert"]["that"] == ["host_unit_alert_env_probe.rc == 0"]
    assert "{{ host_unit_alert_env_file }}" in refusal["ansible.builtin.assert"]["fail_msg"]
    # Nothing that writes to the host comes before the refusal.
    writes = [
        i
        for i, task in enumerate(tasks)
        if {"ansible.builtin.copy", "ansible.builtin.template"} & task.keys()
    ]
    assert min(writes) > 1
