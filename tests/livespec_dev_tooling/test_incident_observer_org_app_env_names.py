"""The observer converge reads the org-App env names, never the stale unsuffixed ones.

The credential wrapper projects both the pre-migration (dead) unsuffixed names and the
org-App `_ORG` names; a converge reading the unsuffixed pair would regress the on-disk
recovery-app.json to the dead App. Names only are asserted, never values.
"""

from __future__ import annotations

from tests.livespec_dev_tooling import test_incident_observer_role_production_unchanged as base

_DEFAULTS = base.role_yaml(relative="defaults/main.yml")


def test_the_recovery_app_id_is_read_from_the_org_variable() -> None:
    assert _DEFAULTS["incident_observer_recovery_app_id_env"] == "LIVESPEC_RECOVERY_ORG_APP_ID"


def test_the_recovery_app_key_is_read_from_the_org_variable() -> None:
    assert (
        _DEFAULTS["incident_observer_recovery_app_key_env"]
        == "LIVESPEC_RECOVERY_ORG_APP_PRIVATE_KEY"
    )
