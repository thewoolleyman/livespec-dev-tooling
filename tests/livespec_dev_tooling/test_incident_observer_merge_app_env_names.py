"""The observer role names the incident-merge App's variables and one task reads them.

The role declares the two variable NAMES the credential wrapper projects for the
incident-merge principal, beside the recovery App's and distinct from them, and they
are the names `incident_merge_app` reads. Exactly one task, the converge's root-only
credential write, reads them, and it enables no merge by itself. Names only are
asserted, never values.
"""

from __future__ import annotations

from livespec_dev_tooling.incident_merge_app import MERGE_APP_ID_ENV, MERGE_APP_KEY_ENV
from tests.livespec_dev_tooling import test_incident_observer_role_production_unchanged as base

_DEFAULTS = base.role_yaml(relative="defaults/main.yml")
_NAMES = ("incident_observer_merge_app_id_env", "incident_observer_merge_app_key_env")


def test_the_role_names_the_variables_the_merge_app_reads() -> None:
    assert [_DEFAULTS[name] for name in _NAMES] == [MERGE_APP_ID_ENV, MERGE_APP_KEY_ENV]


def test_the_merge_app_variables_are_not_the_recovery_apps() -> None:
    recovery = {
        _DEFAULTS["incident_observer_recovery_app_id_env"],
        _DEFAULTS["incident_observer_recovery_app_key_env"],
    }
    assert recovery.isdisjoint({MERGE_APP_ID_ENV, MERGE_APP_KEY_ENV})


def test_only_the_converge_credential_task_reads_the_merge_app_variables() -> None:
    readers = [
        path.relative_to(base.ROLE).as_posix()
        for path in sorted(base.ROLE.rglob("*"))
        if path.is_file()
        and path.relative_to(base.ROLE).parts[0] != "defaults"
        and any(name in path.read_text(encoding="utf-8", errors="replace") for name in _NAMES)
    ]
    assert readers == ["tasks/converge.yml"]
