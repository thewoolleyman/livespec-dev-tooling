"""The role provisions each installation's CI identity policy only from its inventory entry.

livespec-dev-tooling-bqnzcm.4. With no approved publisher commit the role provisions
no policy and production's render is unchanged; with one, the manifest binds the
policy and the policy is rendered from the installation's own inventory ids, never
from a spelled owner.
"""

from __future__ import annotations

import json
from typing import Any

from tests.livespec_dev_tooling import test_incident_observer_role_production_unchanged as base

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-bqnzcm.4
_SHA = "1" * 40
_RENDER_POLICY = "Render this installation's CI identity policy from its inventory entry"
_INSTALL_POLICY = "Install the CI identity policy, private to the controller account"
_CI_TASKS = (
    "Install the CI identity policy renderer beside the manifest renderer",
    "Read the forge's OIDC signing keys for the CI identity policy",
    "Keep the fetched signing keys beside the policy they feed",
    _RENDER_POLICY,
    _INSTALL_POLICY,
    "Remove a CI identity policy no approved publisher commit supports",
)


def _tasks() -> dict[str, dict[str, Any]]:
    return {task["name"]: task for task in base.role_yaml(relative="tasks/converge.yml")}


def _argv(*, variables: dict[str, Any]) -> list[str]:
    return json.loads(base.render_installation(variables=variables)["manifest-render-argv.json"])


def test_no_approved_publisher_commit_provisions_no_policy() -> None:
    variables = base.production_variables()
    assert variables["incident_observer_ci_publisher_shas"] == []
    assert "--ci-identity-policy" not in _argv(variables=variables)
    base.assert_production_render_matches_fixture(
        rendered=base.render_installation(variables=variables), variables=variables
    )


def test_an_approved_publisher_commit_binds_the_policy_into_the_manifest() -> None:
    variables = {**base.production_variables(), "incident_observer_ci_publisher_shas": [_SHA]}
    argv = _argv(variables=variables)
    assert argv[-2:] == ["--ci-identity-policy", "/etc/livespec-incident/ci-identity.json"]


def test_the_policy_is_rendered_from_the_installations_own_inventory_ids() -> None:
    variables = {**base.production_variables(), "incident_observer_ci_publisher_shas": [_SHA]}
    resolved = base.resolve(variables=variables)
    task = _tasks()[_RENDER_POLICY]
    jinja = base.ansible_jinja()
    context = {
        **resolved,
        "incident_observer_ci_entry": jinja.compile_expression(
            task["vars"]["incident_observer_ci_entry"].strip()[2:-2]
        )(**resolved),
    }
    expression = task["ansible.builtin.command"]["argv"].strip()
    argv = jinja.compile_expression(expression[2:-2])(**context)
    entry = resolved["incident_observer_installations"][0]
    assert argv[argv.index("--repository") + 1] == resolved["incident_observer_repository"]
    assert argv[argv.index("--repository-id") + 1] == str(entry["repository_id"])
    assert argv[argv.index("--owner-id") + 1] == str(entry["owner_id"])
    assert argv[argv.index("--publisher-repository") + 1] == entry["repository"]
    assert argv[argv.index("--jwks") + 1] == resolved["incident_observer_ci_jwks_path"]
    assert argv[-1] == "--publisher-sha=" + _SHA


def test_the_policy_is_private_to_the_controller_account() -> None:
    install = _tasks()[_INSTALL_POLICY]["ansible.builtin.copy"]
    assert install["dest"] == "{{ incident_observer_ci_identity_policy_path }}"
    assert install["owner"] == "{{ incident_observer_user }}"
    assert install["mode"] == "0600"


def test_no_ci_identity_task_or_default_spells_an_owner() -> None:
    owner = base.production_variables()["incident_observer_repository"].split("/")[0]
    tasks = _tasks()
    for name in _CI_TASKS:
        assert owner not in json.dumps(tasks[name]), name
    defaults = (base.ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
    section = defaults.split("# --- CI identity policy", 1)[1].split(
        "# The controller account's", 1
    )[0]
    assert owner not in section
