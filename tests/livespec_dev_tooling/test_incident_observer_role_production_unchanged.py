"""Production's rendered incident observer files stay byte-identical beside a scratch instance.

livespec-dev-tooling-32qdja. The role gained a second, scratch-branch instance
(`ansible/incident-observer-scratch.yml`) by overriding its own variables, and
the production apply (`ansible/dev-host.yml`) must render exactly what it
rendered before that change. The fixtures under
`fixtures/incident_observer_production_render/` were rendered from the role as
it stood on master `aa3ed2cb`, before the scratch instance existed: the four
templates (controller.json, the observer unit, the reference fetch service and
timer) byte-identical to ansible-core 2.21.4's own `template` output, plus the
manifest renderer's argv (which bakes `--config` into the principal) and every
per-instance install destination. A production render that moves by one byte
fails here.

A deliberate production change updates its fixture in the same commit and says so
here: the observer unit gained `StartLimitIntervalSec=300` and `StartLimitBurst=5`
(livespec-dev-tooling-fdquen), so a crash loop ends in `failed`; its comment then
gained the reset-failed note.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jinja2
import pytest
import yaml

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-32qdja
_REPO_ROOT = Path(__file__).resolve().parents[2]
ROLE = _REPO_ROOT / "ansible" / "roles" / "incident_observer"
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "incident_observer_production_render"
_MANAGED = "Ansible managed"
_CANDIDATE = "candidate"
_CANDIDATE_UID = 1000
_REVISION = "0" * 40
_RESOLVE_DEPTH = 4
_RENDER_TASK = "Render the released-installation manifest with the serving interpreter"
_RELEASE_FIXTURE_TOKEN = "{{ incident_observer_release }}"
_SCRATCH_ROLE_TEST = Path(__file__).with_name("test_incident_observer_role_scratch_instance.py")
_TEMPLATES = {
    "controller.json": "controller.json.j2",
    "livespec-incident-observer.service": "livespec-incident-observer.service.j2",
    "livespec-incident-reference-fetch.service": "livespec-incident-reference-fetch.service.j2",
    "livespec-incident-reference-fetch.timer": "livespec-incident-reference-fetch.timer.j2",
}
DESTINATIONS = (
    "incident_observer_config_path",
    "incident_observer_manifest_path",
    "incident_observer_state_dir",
    "incident_observer_reference_dir",
    "incident_observer_port",
    "incident_observer_unit_name",
    "incident_observer_unit_path",
    "incident_observer_fetch_unit_name",
    "incident_observer_fetch_service_path",
    "incident_observer_fetch_timer_path",
)

# These are the writes shared by production and the scratch instance.  The
# scratch preflight keeps their destinations disjoint, but the production
# arguments themselves are still a security boundary: a permissive mode on a
# credential or a different destination changes the production installation.
_PRODUCTION_SHARED_WRITE_ARGUMENTS = {
    "Create the private state directory and its recovery journal": {
        "path": "{{ item }}",
        "owner": "{{ incident_observer_user }}",
        "group": "{{ incident_observer_group }}",
        "mode": "0700",
    },
    "Clone the independent reference repository at the released tag": {
        "dest": "{{ incident_observer_reference_dir }}",
        "umask": "0022",
    },
    "Keep the reference clone writable by its owner alone": {
        "path": "{{ incident_observer_reference_dir }}",
        "owner": "{{ incident_observer_user }}",
        "group": "{{ incident_observer_group }}",
        "mode": "0750",
    },
    "Install the reference fetch service and timer": {
        "dest": "{{ item.dest }}",
        "owner": "root",
        "group": "root",
        "mode": "0644",
    },
    "Install controller.json from host facts": {
        "dest": "{{ incident_observer_config_path }}",
        "owner": "{{ incident_observer_user }}",
        "group": "{{ incident_observer_group }}",
        "mode": "0600",
    },
    "Hold the reference clone's ledger directory to its owner alone": {
        "path": "{{ incident_observer_reference_dir }}/.beads",
        "owner": "{{ incident_observer_user }}",
        "group": "{{ incident_observer_group }}",
        "mode": "0700",
    },
    "Write the reference clone's ledger pointer for the canonical reader": {
        "dest": "{{ incident_observer_reference_dir }}/.beads/metadata.json",
        "owner": "{{ incident_observer_user }}",
        "group": "{{ incident_observer_group }}",
        "mode": "0600",
    },
    "Install the released-installation manifest": {
        "dest": "{{ incident_observer_manifest_path }}",
        "owner": "{{ incident_observer_user }}",
        "group": "{{ incident_observer_group }}",
        "mode": "0600",
    },
    "Install the observer's unit": {
        "dest": "{{ incident_observer_unit_path }}",
        "owner": "root",
        "group": "root",
        "mode": "0644",
    },
}


def ansible_jinja() -> jinja2.Environment:
    """Jinja as Ansible's template module configures it, with the Ansible filters the role uses."""
    jinja = jinja2.Environment(
        trim_blocks=True,
        lstrip_blocks=False,
        keep_trailing_newline=True,
        undefined=jinja2.StrictUndefined,
        autoescape=False,
    )
    jinja.filters["to_json"] = json.dumps
    jinja.filters["regex_escape"] = re.escape
    jinja.filters["regex_replace"] = lambda value, pattern, replacement: re.sub(
        pattern, replacement, value
    )
    jinja.filters["intersect"] = lambda left, right: [item for item in left if item in right]
    jinja.filters["bool"] = lambda value: (
        value if isinstance(value, bool) else str(value).strip().lower() in {"1", "true", "yes"}
    )
    jinja.tests["match"] = lambda value, pattern: re.match(pattern, value) is not None
    return jinja


def resolve(*, variables: dict[str, Any]) -> dict[str, Any]:
    """Template every string value against the others, as Ansible does lazily, to a fixed point."""
    jinja = ansible_jinja()
    resolved = dict(variables)
    for _ in range(_RESOLVE_DEPTH):
        resolved = {
            key: jinja.from_string(value).render(**resolved)
            if isinstance(value, str) and "{{" in value
            else value
            for key, value in resolved.items()
        }
    unresolved = [
        key for key, value in resolved.items() if isinstance(value, str) and "{{" in value
    ]
    assert unresolved == [], f"role variables did not resolve: {unresolved}"
    return resolved


def role_yaml(*, relative: str) -> Any:
    """One YAML file of the role, parsed."""
    return yaml.safe_load((ROLE / relative).read_text(encoding="utf-8"))


def production_variables() -> dict[str, Any]:
    """The role's defaults, as ansible/dev-host.yml applies them, with a declared candidate."""
    defaults = role_yaml(relative="defaults/main.yml")
    defaults["incident_observer_candidate_user"] = _CANDIDATE
    return defaults


def render_installation(*, variables: dict[str, Any]) -> dict[str, str]:
    """Every file the role installs from a template or a rendered argv, by fixture name."""
    resolved = resolve(variables=variables)
    context = {
        **resolved,
        "ansible_managed": _MANAGED,
        "ansible_facts": {
            "getent_passwd": {_CANDIDATE: ["x", str(_CANDIDATE_UID), "1000", "", "/", "/bin/sh"]}
        },
        "incident_observer_revision": {"stdout": _REVISION},
    }
    jinja = ansible_jinja()
    rendered = {
        name: jinja.from_string((ROLE / "templates" / source).read_text(encoding="utf-8")).render(
            **context
        )
        for name, source in _TEMPLATES.items()
    }
    tasks = role_yaml(relative="tasks/converge.yml")
    (render,) = [task for task in tasks if task.get("name") == _RENDER_TASK]
    expression = render["ansible.builtin.command"]["argv"].strip()
    assert expression.startswith("{{")
    assert expression.endswith("}}")
    argv = jinja.compile_expression(expression[2:-2])(**context)
    rendered["manifest-render-argv.json"] = json.dumps(argv, indent=2) + "\n"
    destinations = {key: resolved[key] for key in DESTINATIONS}
    rendered["destinations.json"] = json.dumps(destinations, indent=2, sort_keys=True) + "\n"
    return rendered


def _fixture_bytes(*, name: str, variables: dict[str, Any]) -> bytes:
    """The expected fixture, expanding the role's single rollable release pin."""
    fixture = (_FIXTURES / name).read_bytes()
    if name == "manifest-render-argv.json":
        assert _RELEASE_FIXTURE_TOKEN.encode() in fixture
        return fixture.replace(
            _RELEASE_FIXTURE_TOKEN.encode(), variables["incident_observer_release"].encode()
        )
    return fixture


def assert_production_render_matches_fixture(
    *, rendered: dict[str, str], variables: dict[str, Any]
) -> None:
    """Reject a production render that differs from its pinned configuration fixture."""
    fixtures = sorted(path.name for path in _FIXTURES.iterdir())
    assert sorted(rendered) == fixtures
    for name in fixtures:
        assert rendered[name].encode() == _fixture_bytes(name=name, variables=variables), name


def test_the_production_apply_renders_every_installed_file_byte_identical_to_before() -> None:
    variables = production_variables()
    rendered = render_installation(variables=variables)

    assert_production_render_matches_fixture(rendered=rendered, variables=variables)


def test_the_production_render_rejects_a_manifest_with_a_release_other_than_the_pin() -> None:
    variables = production_variables()
    rendered = render_installation(variables=variables)
    argv = json.loads(rendered["manifest-render-argv.json"])
    argv[argv.index("--release") + 1] = "v0.0.0"
    rendered["manifest-render-argv.json"] = json.dumps(argv, indent=2) + "\n"

    with pytest.raises(AssertionError, match="manifest-render-argv.json"):
        assert_production_render_matches_fixture(rendered=rendered, variables=variables)


def test_the_scratch_role_test_does_not_literal_pin_the_observer_release() -> None:
    source = _SCRATCH_ROLE_TEST.read_text(encoding="utf-8")

    assert 'context["incident_observer_release"] == "v' not in source


def test_the_production_apply_declares_no_scratch_instance_and_no_target_branch() -> None:
    variables = resolve(variables=production_variables())

    assert variables["incident_observer_scratch"] is False
    assert variables["incident_observer_target_branch"] == ""
    controller = json.loads(
        render_installation(variables=production_variables())["controller.json"]
    )
    assert "target_branch" not in controller


def test_each_production_shared_write_keeps_its_pinned_security_arguments() -> None:
    """A mode, ownership, or destination mutation changes production's contract."""
    tasks = {task["name"]: task for task in role_yaml(relative="tasks/converge.yml")}

    for name, expected in _PRODUCTION_SHARED_WRITE_ARGUMENTS.items():
        task = tasks[name]
        (module,) = [key for key in task if key.startswith("ansible.builtin.")]
        arguments = task[module]
        assert {key: arguments.get(key) for key in expected} == expected, name
