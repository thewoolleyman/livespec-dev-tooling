"""The incident_observer role installs a scratch-branch observer beside production, and tears it down.

livespec-dev-tooling-32qdja. The thhgeg host proof needs a recovery principal
bound to a SCRATCH branch on the real observer host while production stays on
master. The principal takes no branch argument: it reads `target_branch` from
the controller.json its observer's manifest names in the principal argv. So a
scratch principal means a second observer installation: its own
controller.json, its own manifest whose principal argv ends in THAT
controller.json, its own state directory, reference clone, port and units.

`ansible/incident-observer-scratch.yml` applies the same role with the
variable set in `roles/incident_observer/vars/scratch.yml`;
`ansible/incident-observer-scratch-teardown.yml` removes it. These tests render
the role the way those playbooks resolve it and evaluate its guard expressions,
so the scratch instance can be proven distinct from production, withheld from
every shared write, and removable, without touching a host.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

import livespec_dev_tooling
from livespec_dev_tooling.incident_controller_installation import (
    ControllerInstallation,
    valid_branch_name,
)
from tests.livespec_dev_tooling import test_incident_observer_role_production_unchanged as base
from tests.livespec_dev_tooling.test_incident_controller_installation import (
    host,  # noqa: F401 -- the loader's protected-installation fixture
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-32qdja
_ANSIBLE = base.ROLE.parents[1]
_SCRATCH_PLAY = _ANSIBLE / "incident-observer-scratch.yml"
_TEARDOWN_PLAY = _ANSIBLE / "incident-observer-scratch-teardown.yml"
_PRODUCTION_PLAY = _ANSIBLE / "dev-host.yml"
_VARS_FILE = "roles/incident_observer/vars/scratch.yml"
_BRANCH = "incident-scratch/thhgeg-proof"
_GUARD = "not (incident_observer_scratch | bool)"
_LOADER_KEYS = {
    "manifest",
    "candidate_uid",
    "repository",
    "repo",
    "state",
    "webhook_secret",
    "control_secret",
    "query_secret",
    "port",
}
_VENV_REFUSAL = "Refuse a scratch apply onto a venv production does not already serve"
_SCRATCH_ROOT_TASK = "Create the scratch instance's own root beside production's state"
_SHARED_WRITES = (
    "Install the interpreter's venv module and git",
    "Create the controller account",
    "Create the root-owned installation directories",
    "Create the protected configuration directory",
    "Create the controller account's home",
    "Create the isolated venv on the system interpreter",
    "Install the manifest renderer outside the package and the clones",
    "Install the released distribution from its tag, never from a checkout",
    "Clone the canonical reader at its released tag",
    "Write each secret from the control node's projected environment",
    "Write the canonical reader's credential as the unit's environment file",
    "Write the recovery App credential the principal reads beside controller.json",
)
_FUNNEL = (
    "Read this node's tailscale serve and funnel configuration",
    "Read whether the tailnet grants this node the funnel attribute",
    "Name the funnel grant and the callback path's current disposition",
    "Name the public callback path's disposition in the run output",
    "Publish only the callback path through a path-scoped funnel",
)
_NAMES = "Name what the teardown removes and every production path it reads back"


def _play(*, path: Path) -> dict[str, Any]:
    (play,) = yaml.safe_load(path.read_text(encoding="utf-8"))
    return play


def _task(*, relative: str, name: str) -> dict[str, Any]:
    (task,) = [task for task in base.role_yaml(relative=relative) if task.get("name") == name]
    return task


def scratch_variables(*, overrides: dict[str, Any]) -> dict[str, Any]:
    """The role's variables as ansible/incident-observer-scratch.yml resolves them."""
    variables = base.production_variables()
    for relative in _play(path=_SCRATCH_PLAY)["vars_files"]:
        variables.update(yaml.safe_load((_ANSIBLE / relative).read_text(encoding="utf-8")))
    variables.update(overrides)
    return variables


def _context(*, variables: dict[str, Any]) -> dict[str, Any]:
    """The variables a task's conditions see: resolved role variables and production's."""
    resolved = base.resolve(variables=variables)
    return {
        **resolved,
        "incident_observer_production": base.role_yaml(relative="defaults/main.yml"),
    }


def _holds(*, task: dict[str, Any], context: dict[str, Any]) -> bool:
    """Whether every condition of the task's assert holds in the context."""
    jinja = base.ansible_jinja()
    return all(
        jinja.compile_expression(condition)(**context)
        for condition in task["ansible.builtin.assert"]["that"]
    )


def _scratch_removed() -> list[str]:
    """The teardown's removal list, resolved against the committed scratch variables."""
    context = _context(variables=scratch_variables(overrides={}))
    names = _task(relative="tasks/scratch_teardown.yml", name=_NAMES)["ansible.builtin.set_fact"]
    jinja = base.ansible_jinja()
    return [
        jinja.from_string(item).render(**context)
        for item in names["incident_observer_scratch_removed"]
    ]


def test_the_scratch_play_applies_the_one_role_with_the_scratch_variable_set() -> None:
    play = _play(path=_SCRATCH_PLAY)

    assert play["hosts"] == "dev_hosts"
    assert play["vars_files"] == [_VARS_FILE]
    assert play["roles"] == [{"role": "incident_observer"}]
    assert "scratch" not in _PRODUCTION_PLAY.read_text(encoding="utf-8")


def test_the_scratch_controller_json_binds_the_scratch_branch_beside_production() -> None:
    scratch = base.render_installation(variables=scratch_variables(overrides={}))
    production = base.render_installation(variables=base.production_variables())
    controller = json.loads(scratch["controller.json"])
    original = json.loads(production["controller.json"])
    destinations = json.loads(scratch["destinations.json"])

    assert set(controller) == _LOADER_KEYS | {"target_branch"}
    assert controller["target_branch"] == _BRANCH
    assert valid_branch_name(name=controller["target_branch"])
    assert controller["port"] == 8766
    for key in ("manifest", "repo", "state", "port"):
        assert controller[key] != original[key], key
    for key in ("webhook_secret", "control_secret", "query_secret", "repository"):
        assert controller[key] == original[key], key
    config = Path(destinations["incident_observer_config_path"])
    assert (
        config.parent
        == Path(json.loads(production["destinations.json"])["incident_observer_config_path"]).parent
    )
    assert config.name == "controller-scratch-thhgeg.json"


def test_every_per_instance_destination_differs_from_production() -> None:
    scratch = json.loads(
        base.render_installation(variables=scratch_variables(overrides={}))["destinations.json"]
    )
    production = json.loads(
        base.render_installation(variables=base.production_variables())["destinations.json"]
    )

    assert set(scratch) == set(production) == set(base.DESTINATIONS)
    for key in base.DESTINATIONS:
        assert scratch[key] != production[key], key
        assert "scratch" in str(scratch[key]) or key == "incident_observer_port", key


def test_the_instance_name_moves_every_path_and_the_branch_together() -> None:
    renamed = base.resolve(
        variables=scratch_variables(overrides={"incident_observer_scratch_name": "other"})
    )

    assert renamed["incident_observer_target_branch"] == "incident-scratch/other-proof"
    assert renamed["incident_observer_config_path"].endswith("controller-scratch-other.json")
    assert renamed["incident_observer_state_dir"].startswith(
        "/var/lib/livespec-incident/scratch-other/"
    )


def test_the_scratch_manifest_names_the_scratch_controller_json_in_its_principal(
    tmp_path: Path,
) -> None:
    scratch = base.render_installation(variables=scratch_variables(overrides={}))
    destinations = json.loads(scratch["destinations.json"])
    argv = json.loads(scratch["manifest-render-argv.json"])
    assert argv[argv.index("--config") + 1] == destinations["incident_observer_config_path"]

    spec = importlib.util.spec_from_file_location(
        "render_released_installation", base.ROLE / "files" / "render_released_installation.py"
    )
    assert spec is not None
    assert spec.loader is not None
    renderer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = renderer
    spec.loader.exec_module(renderer)
    config = tmp_path / Path(destinations["incident_observer_config_path"]).name
    config.write_text(scratch["controller.json"], encoding="utf-8")
    reader = tmp_path / "incident_authority.py"
    reader.write_text("", encoding="utf-8")
    manifest = renderer.render_manifest(
        inputs=renderer.ManifestInputs(
            release="v1.0.0",
            revision="a" * 40,
            reader_release="v0.1.0",
            reader_script=reader,
            config=config,
            required_jobs=("ci-green",),
            interpreter=Path(sys.executable),
        ),
        package_root=Path(livespec_dev_tooling.__file__).resolve().parent,
    )

    assert manifest["principal"][-1] == str(config)
    assert config.name == "controller-scratch-thhgeg.json"


def test_the_scratch_units_run_the_scratch_controller_json_and_fetch_the_scratch_clone() -> None:
    scratch = base.render_installation(variables=scratch_variables(overrides={}))
    production = base.render_installation(variables=base.production_variables())
    destinations = json.loads(scratch["destinations.json"])
    (exec_start,) = [
        line
        for line in scratch["livespec-incident-observer.service"].splitlines()
        if line.startswith("ExecStart=")
    ]

    assert exec_start.endswith(f"--config {destinations['incident_observer_config_path']}")
    assert (
        destinations["incident_observer_reference_dir"]
        in (scratch["livespec-incident-reference-fetch.service"])
    )
    assert (
        "/var/lib/livespec-incident/reference "
        not in (scratch["livespec-incident-reference-fetch.service"])
    )
    # The timer carries no per-instance value: systemd activates the service
    # whose name it shares, so the scratch timer starts the scratch fetch.
    assert (
        scratch["livespec-incident-reference-fetch.timer"]
        == (production["livespec-incident-reference-fetch.timer"])
    )
    assert destinations["incident_observer_fetch_timer_path"].endswith(
        destinations["incident_observer_fetch_unit_name"] + ".timer"
    )


def test_the_loader_reads_the_branch_the_role_renders_and_master_when_none(host) -> None:  # noqa: F811
    _, config, _, write = host
    scratch = json.loads(
        base.render_installation(variables=scratch_variables(overrides={}))["controller.json"]
    )
    production = json.loads(
        base.render_installation(variables=base.production_variables())["controller.json"]
    )

    config.update(target_branch=scratch["target_branch"])
    loaded = ControllerInstallation.load(config=write())
    assert loaded is not None
    assert loaded.target_branch == _BRANCH

    _ = config.pop("target_branch")
    assert set(config) == set(production)
    loaded = ControllerInstallation.load(config=write())
    assert loaded is not None
    assert loaded.target_branch == "master"


@pytest.mark.parametrize(
    ("installed", "stdout", "holds"),
    [(True, "1.193.0\n", True), (True, "1.187.0\n", False), (False, "", False)],
)
def test_a_scratch_apply_refuses_a_venv_production_does_not_already_serve(
    *, installed: bool, stdout: str, holds: bool
) -> None:
    task = _task(relative="tasks/converge.yml", name=_VENV_REFUSAL)
    context = _context(variables=scratch_variables(overrides={}))
    context["incident_observer_installed"] = installed
    context["incident_observer_installed_version"] = {"rc": 0, "stdout": stdout}

    assert context["incident_observer_release"] == "v1.193.0"
    assert task["when"] == "incident_observer_scratch | bool"
    assert _holds(task=task, context=context) is holds


@pytest.mark.parametrize("name", [*_SHARED_WRITES, *_FUNNEL])
def test_a_scratch_apply_withholds_every_shared_write_and_the_funnel(name: str) -> None:
    when = _task(relative="tasks/converge.yml", name=name)["when"]
    first = when[0] if isinstance(when, list) else when
    jinja = base.ansible_jinja()

    assert first.strip().startswith(_GUARD)
    assert jinja.compile_expression(first)(incident_observer_scratch=True) is False


def test_production_still_publishes_its_callback_and_never_creates_a_scratch_root() -> None:
    jinja = base.ansible_jinja()
    publish = _task(relative="tasks/converge.yml", name=_FUNNEL[-1])["when"]
    root = _task(relative="tasks/converge.yml", name=_SCRATCH_ROOT_TASK)["when"]

    assert jinja.compile_expression(publish)(
        incident_observer_scratch=False,
        incident_observer_funnel_granted=True,
        incident_observer_funnel_served=False,
    )
    assert not jinja.compile_expression(root)(incident_observer_scratch=False)


def test_the_teardown_play_runs_the_teardown_tasks_on_the_same_instance() -> None:
    play = _play(path=_TEARDOWN_PLAY)
    (task,) = play["tasks"]

    assert play["hosts"] == "dev_hosts"
    assert play["vars_files"] == _play(path=_SCRATCH_PLAY)["vars_files"]
    assert task["ansible.builtin.include_role"] == {
        "name": "incident_observer",
        "tasks_from": "scratch_teardown",
    }


def test_the_teardown_removes_exactly_the_scratch_units_stamp_controller_json_and_manifest() -> (
    None
):
    removal = _task(
        relative="tasks/scratch_teardown.yml",
        name="Remove the scratch unit files, timer stamp, controller.json and manifest",
    )

    assert _scratch_removed() == [
        "/etc/systemd/system/livespec-incident-observer-scratch.service",
        "/etc/systemd/system/livespec-incident-reference-fetch-scratch.service",
        "/etc/systemd/system/livespec-incident-reference-fetch-scratch.timer",
        "/var/lib/systemd/timers/stamp-livespec-incident-reference-fetch-scratch.timer",
        "/etc/livespec-incident/controller-scratch-thhgeg.json",
        "/etc/livespec-incident/released-installation-scratch-thhgeg.json",
    ]
    assert removal["ansible.builtin.file"]["state"] == "absent"
    assert removal["loop"] == "{{ incident_observer_scratch_removed }}"


def test_the_teardown_stops_and_disables_the_scratch_observer_and_its_fetch_timer() -> None:
    unit = _task(
        relative="tasks/scratch_teardown.yml", name="Stop and disable the scratch observer"
    )
    timer = _task(
        relative="tasks/scratch_teardown.yml",
        name="Stop and disable the scratch reference fetch timer",
    )

    assert unit["ansible.builtin.systemd_service"] == {
        "name": "{{ incident_observer_unit_name }}",
        "state": "stopped",
        "enabled": False,
    }
    assert timer["ansible.builtin.systemd_service"] == {
        "name": "{{ incident_observer_fetch_unit_name }}.timer",
        "state": "stopped",
        "enabled": False,
    }
    tasks = base.role_yaml(relative="tasks/scratch_teardown.yml")
    assert all("notify" not in task for task in tasks), "the teardown never restarts a unit"


def test_the_teardown_keeps_the_scratch_evidence_store_unless_asked() -> None:
    purge = _task(
        relative="tasks/scratch_teardown.yml",
        name="Remove the scratch evidence store only when asked",
    )
    variables = base.resolve(variables=scratch_variables(overrides={}))

    assert variables["incident_observer_scratch_teardown_purge"] is False
    assert purge["when"] == "incident_observer_scratch_teardown_purge | bool"
    assert purge["ansible.builtin.file"] == {
        "path": (
            "{{ incident_observer_production.incident_observer_home }}"
            "/scratch-{{ incident_observer_scratch_name }}"
        ),
        "state": "absent",
    }
