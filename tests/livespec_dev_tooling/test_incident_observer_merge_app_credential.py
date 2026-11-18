"""The converge projects the incident-merge App credential root-only and never the recovery one.

Names, paths, owners and modes only are asserted, never a value.
"""

from __future__ import annotations

from typing import Any

from tests.livespec_dev_tooling import test_incident_observer_role_production_unchanged as base

_DEFAULTS = base.role_yaml(relative="defaults/main.yml")
_TASKS: list[dict[str, Any]] = base.role_yaml(relative="tasks/converge.yml")


def _merge_task() -> dict[str, Any]:
    named = [t for t in _TASKS if "incident-merge App credential" in str(t.get("name", ""))]
    assert len(named) == 1
    return named[0]


def test_the_merge_credential_file_is_distinct_from_the_recovery_file() -> None:
    merge_path = _DEFAULTS["incident_observer_merge_app_path"]
    assert merge_path == "/etc/livespec-incident/merge-app.json"
    assert merge_path != _DEFAULTS["incident_observer_recovery_app_path"]


def test_the_merge_credential_is_written_root_only_at_mode_0600_under_no_log() -> None:
    task = _merge_task()
    copy = task["ansible.builtin.copy"]
    assert (copy["owner"], copy["group"], copy["mode"]) == ("root", "root", "0600")
    assert task["no_log"] is True
    assert task["become"] is True


def test_the_merge_credential_reads_only_the_merge_variables() -> None:
    content = str(_merge_task()["ansible.builtin.copy"]["content"])
    assert "incident_observer_merge_app_id_env" in content
    assert "incident_observer_merge_app_key_env" in content
    assert "recovery" not in content


def test_the_merge_credential_is_written_only_on_the_production_apply_with_both_variables() -> None:
    conditions = " ".join(str(c) for c in _merge_task()["when"])
    for needle in ("incident_observer_scratch", "incident_observer_installation_name"):
        assert needle in conditions
    assert conditions.count("length > 0") == 2
