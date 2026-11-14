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
    # The empty list is SET here, so a committed rollout that lists a commit does
    # not break the property: an empty list leaves production's render unchanged.
    variables = {**base.production_variables(), "incident_observer_ci_publisher_shas": []}
    assert "--ci-identity-policy" not in _argv(variables=variables)
    base.assert_production_render_matches_fixture(
        rendered=base.render_installation(variables=variables), variables=variables
    )


def test_an_approved_publisher_commit_binds_the_policy_into_the_manifest() -> None:
    variables = {**base.production_variables(), "incident_observer_ci_publisher_shas": [_SHA]}
    argv = _argv(variables=variables)
    resolved = base.resolve(variables=variables)
    assert argv[-2:] == [
        "--ci-identity-policy",
        resolved["incident_observer_ci_identity_policy_path"],
    ]


def _policy_argv(*, variables: dict[str, Any]) -> tuple[list[str], dict[str, Any]]:
    """The policy render task's argv as Ansible resolves it for these variables."""
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
    return jinja.compile_expression(expression[2:-2])(**context), resolved


def _value(*, argv: list[str], flag: str) -> str:
    return argv[argv.index(flag) + 1]


def test_production_renders_its_policy_from_its_own_inventory_entry() -> None:
    variables = {**base.production_variables(), "incident_observer_ci_publisher_shas": [_SHA]}
    argv, resolved = _policy_argv(variables=variables)
    (own,) = [
        entry
        for entry in resolved["incident_observer_installations"]
        if entry["repository"] == resolved["incident_observer_repository"]
    ]
    assert _value(argv=argv, flag="--repository") == own["repository"]
    assert _value(argv=argv, flag="--repository-id") == str(own["repository_id"])
    assert _value(argv=argv, flag="--owner-id") == str(own["owner_id"])
    assert _value(argv=argv, flag="--jwks") == resolved["incident_observer_ci_jwks_path"]
    assert argv[-1] == "--publisher-sha=" + _SHA


def test_a_further_installation_takes_its_own_ids_and_the_first_entrys_publisher() -> None:
    # Production is both its own entry and the first, so only a further
    # installation tells "this installation's ids" from "the publisher repository".
    inventory = base.production_variables()["incident_observer_installations"]
    first, further = inventory[0], inventory[1]
    variables = {
        **base.production_variables(),
        "incident_observer_ci_publisher_shas": [_SHA],
        "incident_observer_repository": further["repository"],
    }
    argv, _ = _policy_argv(variables=variables)
    assert further["repository_id"] != first["repository_id"]
    assert _value(argv=argv, flag="--repository") == further["repository"]
    assert _value(argv=argv, flag="--repository-id") == str(further["repository_id"])
    assert _value(argv=argv, flag="--owner-id") == str(further["owner_id"])
    assert _value(argv=argv, flag="--publisher-repository") == first["repository"]


def test_an_approved_publisher_commit_makes_the_policy_required_at_the_load_check() -> None:
    load = _tasks()["Load the whole installation as the controller account before serving it"]
    expression = load["ansible.builtin.command"]["argv"][-1]
    jinja = base.ansible_jinja()
    modes = {
        name: jinja.from_string(expression).render(
            **base.resolve(
                variables={
                    **base.production_variables(),
                    "incident_observer_ci_publisher_shas": shas,
                }
            )
        )
        for name, shas in (("approved", [_SHA]), ("none", []))
    }
    assert modes == {"approved": "required", "none": "optional"}
    assert "loaded.ci_identity_policy is not None" in load["ansible.builtin.command"]["argv"][3]


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
