"""The observer role renders one production installation per repository its inventory declares.

livespec-dev-tooling-lqp2qx (spec: the-fleet-audit-can-read, the per-repository
installation paragraph). The role's committed inventory,
`incident_observer_installations`, lists livespec-dev-tooling first: its entry
repeats the values ansible/dev-host.yml converges, byte-identical to the role
before the inventory existed. Every other entry is converged one at a time by
ansible/incident-observer-installation.yml, with its layout derived from its
name in vars/installation.yml and its public routes on the role's one funnel
port at /<name>/callback, /<name>/ordinary-action and /<name>/ci/publish, proxied to its own
listener. The refusal of an undeclared public path judges the port against the
union of every declared installation's paths.

Every verdict and every derived value here comes from the pinned ansible-core's
own template engine (the scratch refusals' engine), and the funnel behaviour
from the role's committed funnel tasks run through the pinned
`ansible-playbook` against the funnel test's fake `tailscale`.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

import pytest
import yaml

from tests.livespec_dev_tooling import test_incident_observer_role_funnel_paths as funnel
from tests.livespec_dev_tooling import test_incident_observer_role_production_unchanged as base
from tests.livespec_dev_tooling import test_incident_observer_role_scratch_refusals as refusals

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-lqp2qx
_INSTALLATION_VARS = base.ROLE / "vars" / "installation.yml"
_PREFLIGHT = "tasks/installation_preflight.yml"
_NAME = (
    "Refuse an installation run without a safe name, in scratch mode, or for livespec-dev-tooling"
)
_INVENTORY = (
    "Refuse an inventory that does not declare this installation exactly once, or is malformed"
)
_SHARED = "Refuse an installation run that would move anything the installations share"
_LAYOUT = "Refuse an installation layout other than the one its name fixes"
_DISJOINT = (
    "Refuse any installation path that is, sits inside, or contains a path"
    " livespec-dev-tooling's installation owns"
)
_ASSERTS = (_NAME, _INVENTORY, _SHARED, _LAYOUT, _DISJOINT)
_PLAYBOOK_TIMEOUT_SECONDS = 600
_IDS = ("repository_id", "owner_id")
# The owner is read from the role's own default, never spelled here (the fleet is
# moving to an organization).
_OWNER = base.role_yaml(relative="defaults/main.yml")["incident_observer_repository"].split("/")[0]
_SECOND_REPOSITORY = f"{_OWNER}/livespec"
_SECOND = {
    "repository": _SECOND_REPOSITORY,
    "required_jobs": ["check-lint", "ci-green"],
    "port": 8770,
    "tenant_project_id": "00000000-0000-0000-0000-000000000000",
    "reader_env_var": "BEADS_DOLT_PASSWORD_LIVESPEC",
}
_DERIVED = (
    "incident_observer_repository",
    "incident_observer_required_jobs",
    "incident_observer_port",
    "incident_observer_tenant_project_id",
    "incident_observer_reader_env_var",
    "incident_observer_installation_root",
    "incident_observer_config_path",
    "incident_observer_manifest_path",
    "incident_observer_reader_env_path",
    "incident_observer_state_dir",
    "incident_observer_reference_dir",
    "incident_observer_reference_repo",
    "incident_observer_reference_version",
    "incident_observer_release_reference_dir",
    "incident_observer_unit_name",
    "incident_observer_unit_path",
    "incident_observer_fetch_unit_name",
    "incident_observer_fetch_service_path",
    "incident_observer_fetch_timer_path",
    "incident_observer_funnel_paths",
    "incident_observer_funnel_targets",
)


def _defaults() -> dict[str, Any]:
    return base.role_yaml(relative="defaults/main.yml")


def _inventory(*extra: dict[str, Any]) -> list[dict[str, Any]]:
    return [_defaults()["incident_observer_installations"][0], *extra]


def run_variables(
    *, name: str, inventory: list[dict[str, Any]], overrides: dict[str, Any] | None = None
) -> dict[str, Any]:
    """An installation run's variables in Ansible's precedence: defaults, vars file, `-e`."""
    production = _defaults()
    variables: dict[str, Any] = {**production, "incident_observer_candidate_user": "candidate"}
    variables["incident_observer_installations"] = inventory
    variables.update(yaml.safe_load(_INSTALLATION_VARS.read_text(encoding="utf-8")))
    variables["incident_observer_installation_name"] = name
    variables.update(overrides or {})
    return variables


def _case(*, variables: dict[str, Any]) -> list[dict[str, Any]]:
    """One engine case per refusal, in `_ASSERTS` order."""
    tasks = {task.get("name"): task for task in base.role_yaml(relative=_PREFLIGHT)}
    return [
        {
            "variables": variables,
            "conditions": tasks[name]["ansible.builtin.assert"]["that"],
            "templates": [],
        }
        for name in _ASSERTS
    ]


def _derived(*, variables: dict[str, Any]) -> dict[str, Any]:
    """The values the role acts on, as Ansible resolves them."""
    (reply,) = refusals.run_engine(
        cases=[
            {
                "variables": variables,
                "conditions": [],
                "templates": [
                    "{{ {" + ", ".join(f"'{k}': {k}" for k in _DERIVED) + "} | to_json }}"
                ],
            }
        ]
    )
    return json.loads(reply["templates"][0])


_GOOD = run_variables(name="livespec", inventory=_inventory(_SECOND))
# Each case: an id, its variables, and the refusals it must trip (empty: holds).
_CASES: list[tuple[str, dict[str, Any], frozenset[str]]] = [
    ("declared-second-repository", _GOOD, frozenset()),
    (
        "livespec-dev-tooling-by-name",
        run_variables(name="livespec-dev-tooling", inventory=_inventory(_SECOND)),
        frozenset({_NAME}),
    ),
    (
        "undeclared-name",
        run_variables(name="livespec-runtime", inventory=_inventory(_SECOND)),
        frozenset({_INVENTORY, _LAYOUT}),
    ),
    (
        "unsafe-name",
        run_variables(name="../livespec", inventory=_inventory(_SECOND)),
        frozenset({_NAME}),
    ),
    (
        "scratch-mode-on",
        run_variables(
            name="livespec",
            inventory=_inventory(_SECOND),
            overrides={"incident_observer_scratch": True},
        ),
        frozenset({_NAME}),
    ),
    (
        "port-shared-with-livespec-dev-tooling",
        run_variables(name="livespec", inventory=_inventory({**_SECOND, "port": 8765})),
        frozenset({_INVENTORY}),
    ),
    (
        "port-shared-with-the-scratch-instance",
        run_variables(name="livespec", inventory=_inventory({**_SECOND, "port": 8766})),
        frozenset({_INVENTORY}),
    ),
    (
        "declared-twice",
        run_variables(name="livespec", inventory=_inventory(_SECOND, {**_SECOND, "port": 8771})),
        frozenset({_INVENTORY}),
    ),
    (
        "required-jobs-not-ending-in-ci-green",
        run_variables(
            name="livespec", inventory=_inventory({**_SECOND, "required_jobs": ["check-lint"]})
        ),
        frozenset({_INVENTORY}),
    ),
    (
        "port-overridden-on-the-command-line",
        run_variables(
            name="livespec",
            inventory=_inventory(_SECOND),
            overrides={"incident_observer_port": 8799},
        ),
        frozenset({_LAYOUT}),
    ),
    (
        "config-overridden-onto-livespec-dev-toolings",
        run_variables(
            name="livespec",
            inventory=_inventory(_SECOND),
            overrides={
                "incident_observer_config_path": _defaults()["incident_observer_config_path"]
            },
        ),
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "state-overridden-onto-livespec-dev-toolings",
        run_variables(
            name="livespec",
            inventory=_inventory(_SECOND),
            overrides={
                "incident_observer_state_dir": _defaults()["incident_observer_state_dir"] + "/"
            },
        ),
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "shared-secret-moved",
        run_variables(
            name="livespec",
            inventory=_inventory(_SECOND),
            overrides={
                "incident_observer_recovery_app_path": _defaults()[
                    "incident_observer_recovery_app_path"
                ]
                + ".moved"
            },
        ),
        frozenset({_SHARED}),
    ),
]


@pytest.fixture(scope="module")
def verdicts() -> list[dict[str, Any]]:
    """The engine's verdict on every case's refusals, once per module."""
    return refusals.run_engine(
        cases=[entry for _, variables, _ in _CASES for entry in _case(variables=variables)]
    )


def test_the_inventory_lists_livespec_dev_tooling_first_exactly_as_dev_host_converges_it() -> None:
    defaults = _defaults()
    (first, *_) = defaults["incident_observer_installations"]

    assert {key: first[key] for key in first if key not in _IDS} == {
        "repository": defaults["incident_observer_repository"],
        "required_jobs": defaults["incident_observer_required_jobs"],
        "port": defaults["incident_observer_port"],
        "tenant_project_id": defaults["incident_observer_tenant_project_id"],
        "reader_env_var": defaults["incident_observer_reader_env_var"],
    }
    assert (
        defaults["incident_observer_installation_routes"]
        == defaults["incident_observer_funnel_paths"]
    )


def test_every_inventory_entry_names_its_repository_and_owner_by_numeric_id() -> None:
    """The CI identity policy keys on both ids, never on the owner's login."""
    for entry in _defaults()["incident_observer_installations"]:
        assert {key: type(entry[key]) for key in _IDS} == {key: int for key in _IDS}, entry
        assert all(entry[key] > 0 for key in _IDS), entry


@pytest.mark.parametrize(
    ("index", "case"), list(enumerate(_CASES)), ids=[case[0] for case in _CASES]
)
def test_each_installation_refusal_holds_or_refuses_exactly_as_ansible_judges_it(
    verdicts: list[dict[str, Any]], *, index: int, case: tuple[str, dict[str, Any], frozenset[str]]
) -> None:
    _, _, refused_by = case
    replies = verdicts[index * len(_ASSERTS) : (index + 1) * len(_ASSERTS)]

    refused = {
        name
        for name, reply in zip(_ASSERTS, replies, strict=True)
        if not all(verdict is True for verdict in reply["conditions"])
    }

    # A run holds only when nothing refuses it; a bad run trips at least the
    # refusal named for it (a name that selects no entry also leaves the derived
    # layout unresolvable, which refuses too).
    if refused_by:
        assert refused_by <= refused, refused
    else:
        assert refused == set()


def test_a_declared_repository_gets_its_own_layout_derived_from_its_name() -> None:
    derived = _derived(variables=_GOOD)
    defaults = _defaults()
    # Every host path is spelled from livespec-dev-tooling's own defaults plus the
    # name, never as a literal (check-tests-host-path-free).
    etc = defaults["incident_observer_etc_dir"]
    home = defaults["incident_observer_home"]
    units = str(PurePosixPath(defaults["incident_observer_unit_path"]).parent)
    root = f"{home}/installation-livespec"

    assert derived == {
        "incident_observer_repository": _SECOND_REPOSITORY,
        "incident_observer_required_jobs": ["check-lint", "ci-green"],
        "incident_observer_port": 8770,
        "incident_observer_tenant_project_id": "00000000-0000-0000-0000-000000000000",
        "incident_observer_reader_env_var": "BEADS_DOLT_PASSWORD_LIVESPEC",
        "incident_observer_installation_root": root,
        "incident_observer_config_path": f"{etc}/controller-livespec.json",
        "incident_observer_manifest_path": f"{etc}/released-installation-livespec.json",
        "incident_observer_reader_env_path": f"{etc}/reader-livespec.env",
        "incident_observer_state_dir": f"{root}/receipts",
        "incident_observer_reference_dir": f"{root}/reference",
        "incident_observer_reference_repo": f"https://github.com/{_SECOND_REPOSITORY}.git",
        "incident_observer_reference_version": "master",
        "incident_observer_release_reference_dir": defaults["incident_observer_reference_dir"],
        "incident_observer_unit_name": "livespec-incident-observer-livespec",
        "incident_observer_unit_path": f"{units}/livespec-incident-observer-livespec.service",
        "incident_observer_fetch_unit_name": "livespec-incident-reference-fetch-livespec",
        "incident_observer_fetch_service_path": (
            f"{units}/livespec-incident-reference-fetch-livespec.service"
        ),
        "incident_observer_fetch_timer_path": (
            f"{units}/livespec-incident-reference-fetch-livespec.timer"
        ),
        "incident_observer_funnel_paths": [
            "/livespec/callback",
            "/livespec/ordinary-action",
            "/livespec/ci/publish",
        ],
        "incident_observer_funnel_targets": ["/callback", "/ordinary-action", "/ci/publish"],
    }


def test_the_installation_renders_its_own_controller_and_units_beside_livespec_dev_toolings() -> (
    None
):
    derived = _derived(variables=_GOOD)
    variables = {**base.production_variables(), **derived}
    variables.pop("incident_observer_installations")
    rendered = base.render_installation(variables=variables)
    production = base.render_installation(variables=base.production_variables())

    controller = json.loads(rendered["controller.json"])
    assert controller["repository"] == _SECOND_REPOSITORY
    assert controller["port"] == 8770
    assert controller["manifest"] == derived["incident_observer_manifest_path"]
    assert controller["state"] == derived["incident_observer_state_dir"]
    assert "target_branch" not in controller
    unit = rendered["livespec-incident-observer.service"]
    assert "--config " + derived["incident_observer_config_path"] in unit
    assert "EnvironmentFile=" + derived["incident_observer_reader_env_path"] in unit
    argv = json.loads(rendered["manifest-render-argv.json"])
    assert argv[argv.index("--config") + 1] == derived["incident_observer_config_path"]
    assert [arg for arg in argv if arg.startswith("--required-job=")] == [
        "--required-job=check-lint",
        "--required-job=ci-green",
    ]
    ours = json.loads(rendered["destinations.json"])
    theirs = json.loads(production["destinations.json"])
    assert {key for key in ours if ours[key] == theirs[key]} == set()


def test_declaring_a_second_repository_leaves_livespec_dev_toolings_render_byte_identical() -> None:
    variables = {
        **base.production_variables(),
        "incident_observer_installations": _inventory(_SECOND),
    }

    base.assert_production_render_matches_fixture(
        rendered=base.render_installation(variables=variables), variables=variables
    )


def test_every_observer_unit_is_kept_off_the_oom_killers_early_list() -> None:
    rendered = base.render_installation(variables=base.production_variables())

    assert "OOMScoreAdjust=-500" in rendered["livespec-incident-observer.service"]
    assert "OOMScoreAdjust=-500" in rendered["livespec-incident-reference-fetch.service"]


# --- the funnel: one port, every installation's routes, judged as a union -----

_DNS = "node.example.ts.net"
_HOST = _DNS + ":10000"
_DEV = "http://127.0.0.1:8765"
_SECOND_LISTENER = "http://127.0.0.1:8770"
_DEV_ROUTES = {
    "/callback": _DEV + "/callback",
    "/ordinary-action": _DEV + "/ordinary-action",
    "/ci/publish": _DEV + "/ci/publish",
}
_SECOND_ROUTES = {
    "/livespec/callback": _SECOND_LISTENER + "/callback",
    "/livespec/ordinary-action": _SECOND_LISTENER + "/ordinary-action",
    "/livespec/ci/publish": _SECOND_LISTENER + "/ci/publish",
}


def _serve(*, handlers: dict[str, str]) -> dict[str, Any]:
    return {
        "TCP": {"10000": {"HTTPS": True}},
        "Web": {_HOST: {"Handlers": {path: {"Proxy": proxy} for path, proxy in handlers.items()}}},
        "AllowFunnel": {_HOST: True},
    }


def _production_vars(*, inventory: list[dict[str, Any]]) -> dict[str, Any]:
    defaults = _defaults()
    return {
        "incident_observer_scratch": False,
        "incident_observer_target_branch": "",
        "incident_observer_port": defaults["incident_observer_port"],
        "incident_observer_funnel_https_port": defaults["incident_observer_funnel_https_port"],
        "incident_observer_funnel_paths": defaults["incident_observer_funnel_paths"],
        "incident_observer_installation_routes": defaults["incident_observer_installation_routes"],
        "incident_observer_installations": inventory,
    }


def _second_vars() -> dict[str, Any]:
    derived = _derived(variables=_GOOD)
    return {
        **_production_vars(inventory=_inventory(_SECOND)),
        "incident_observer_port": derived["incident_observer_port"],
        "incident_observer_funnel_paths": derived["incident_observer_funnel_paths"],
        "incident_observer_funnel_targets": derived["incident_observer_funnel_targets"],
    }


# Each node: its recorded funnel status and the role variables its run applies.
def _nodes() -> dict[str, tuple[dict[str, Any], dict[str, Any]]]:
    return {
        "second-fresh": (_serve(handlers=_DEV_ROUTES), _second_vars()),
        "second-public": (_serve(handlers={**_DEV_ROUTES, **_SECOND_ROUTES}), _second_vars()),
        "dev-beside-second": (
            _serve(handlers={**_DEV_ROUTES, **_SECOND_ROUTES}),
            _production_vars(inventory=_inventory(_SECOND)),
        ),
        "dev-sibling-mistargeted": (
            _serve(
                handlers={
                    **_DEV_ROUTES,
                    "/livespec/callback": _DEV + "/callback",
                    "/livespec/ordinary-action": _SECOND_LISTENER + "/ordinary-action",
                    "/livespec/ci/publish": _SECOND_LISTENER + "/ci/publish",
                }
            ),
            _production_vars(inventory=_inventory(_SECOND)),
        ),
        "dev-undeclared-second": (
            _serve(handlers={**_DEV_ROUTES, **_SECOND_ROUTES}),
            _production_vars(inventory=_inventory()),
        ),
        "second-beside-stranger": (
            _serve(
                handlers={**_DEV_ROUTES, "/stranger/callback": "http://127.0.0.1:9999/callback"}
            ),
            _second_vars(),
        ),
    }


@dataclass(frozen=True, kw_only=True)
class _Outcome:
    failed: bool
    published: list[list[str]]
    output: str


@pytest.fixture(scope="module")
def outcomes(tmp_path_factory: pytest.TempPathFactory) -> dict[str, _Outcome]:
    """Run the role's funnel tasks once over every node; each node's result, by name."""
    root = tmp_path_factory.mktemp("installation-funnel")
    tasks = base.role_yaml(relative="tasks/converge.yml")
    names = [task.get("name") for task in tasks]
    funnel_tasks = [
        {key: value for key, value in task.items() if key != "become"}
        for task in tasks[
            names.index(funnel.FIRST_FUNNEL_TASK) : names.index(funnel.LAST_FUNNEL_TASK) + 1
        ]
    ]
    bin_dir = root / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "tailscale"
    fake.write_text(funnel.FAKE_TAILSCALE, encoding="utf-8")
    fake.chmod(0o755)
    nodes = _nodes()
    hosts: dict[str, dict[str, Any]] = {}
    for node, (serve, variables) in nodes.items():
        state = root / (node + ".json")
        state.write_text(
            json.dumps({"dns": _DNS + ".", "granted": True, "publishes": True, "serve": serve}),
            encoding="utf-8",
        )
        (root / (node + ".jsonl")).touch()
        hosts[node] = {
            "ansible_connection": "local",
            "fake_state": str(state),
            "fake_log": str(root / (node + ".jsonl")),
            **variables,
        }
    inventory = root / "inventory.yml"
    inventory.write_text(yaml.safe_dump({"all": {"hosts": hosts}}), encoding="utf-8")
    play = root / "funnel.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "all",
                    "gather_facts": False,
                    "environment": {
                        "FAKE_TAILSCALE_STATE": "{{ fake_state }}",
                        "FAKE_TAILSCALE_LOG": "{{ fake_log }}",
                    },
                    "tasks": funnel_tasks,
                }
            ]
        ),
        encoding="utf-8",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update(
        {
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_LOCALHOST_WARNING": "false",
            "ANSIBLE_STDOUT_CALLBACK": "oneline",
            "PATH": str(bin_dir) + os.pathsep + env.get("PATH", ""),
        }
    )
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            refusals.ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(inventory),
            "--forks",
            str(len(nodes)),
            str(play),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    lines = completed.stdout.splitlines()
    return {
        node: _Outcome(
            failed=any(line.startswith(node + " | FAILED!") for line in lines),
            published=[
                json.loads(line)
                for line in (root / (node + ".jsonl")).read_text(encoding="utf-8").splitlines()
            ],
            output="\n".join(line for line in lines if line.startswith(node + " | ")),
        )
        for node in nodes
    }


def _publish(*, path: str, target: str) -> list[str]:
    return ["funnel", "--bg", "--yes", "--https=10000", "--set-path=" + path, target]


def test_a_second_installation_publishes_its_prefixed_routes_to_its_own_listener(
    outcomes: dict[str, _Outcome],
) -> None:
    outcome = outcomes["second-fresh"]

    # The pending paths come out of `difference`, which keeps no order, so the
    # publishes are compared as a set of argvs.
    assert outcome.failed is False, outcome.output
    assert sorted(outcome.published) == sorted(
        [
            _publish(path="/livespec/callback", target=_SECOND_LISTENER + "/callback"),
            _publish(
                path="/livespec/ordinary-action", target=_SECOND_LISTENER + "/ordinary-action"
            ),
            _publish(path="/livespec/ci/publish", target=_SECOND_LISTENER + "/ci/publish"),
        ]
    )


def test_a_second_installation_already_public_publishes_nothing(
    outcomes: dict[str, _Outcome],
) -> None:
    outcome = outcomes["second-public"]

    assert outcome.failed is False, outcome.output
    assert outcome.published == []


def test_livespec_dev_tooling_converges_beside_a_declared_installations_routes(
    outcomes: dict[str, _Outcome],
) -> None:
    outcome = outcomes["dev-beside-second"]

    assert outcome.failed is False, outcome.output
    assert outcome.published == []


def test_a_public_route_no_installation_declares_is_still_refused_and_named(
    outcomes: dict[str, _Outcome],
) -> None:
    undeclared = outcomes["dev-undeclared-second"]
    stranger = outcomes["second-beside-stranger"]

    # `difference` keeps no order, so each undeclared path is checked on its own.
    assert undeclared.failed is True
    assert "which the role does not declare" in undeclared.output
    assert "/livespec/callback" in undeclared.output.split("which the role does not declare")[0]
    assert (
        "/livespec/ordinary-action" in undeclared.output.split("which the role does not declare")[0]
    )
    assert stranger.failed is True
    assert "publishes /stranger/callback, which the role does not declare" in stranger.output


def test_a_declared_path_proxied_to_another_installations_listener_is_refused(
    outcomes: dict[str, _Outcome],
) -> None:
    outcome = outcomes["dev-sibling-mistargeted"]

    assert outcome.failed is True
    assert outcome.published == []
    assert "funnel port 10000 proxies /livespec/callback to a listener other than" in (
        outcome.output
    )


_SHARED_WRITES = (
    "Install the interpreter's venv module and git",
    "Create the controller account",
    "Create the root-owned installation directories",
    "Create the protected configuration directory",
    "Create the controller account's home",
    "Create the isolated venv on the system interpreter",
    "Install the released distribution from its tag, never from a checkout",
    "Clone the canonical reader at its released tag",
    "Write each secret from the control node's projected environment",
    "Install the manifest renderer outside the package and the clones",
    "Write the recovery App credential the principal reads beside controller.json",
)


@pytest.mark.parametrize("name", _SHARED_WRITES)
def test_an_installation_run_skips_every_write_livespec_dev_tooling_owns(name: str) -> None:
    (task,) = [
        task for task in base.role_yaml(relative="tasks/converge.yml") if task.get("name") == name
    ]
    when = task["when"]
    first = when[0] if isinstance(when, list) else when
    jinja = base.ansible_jinja()
    production = {
        "incident_observer_scratch": False,
        "incident_observer_target_branch": "",
        # The release install also asks whether the venv already serves the
        # release; a first apply reads it as not installed.
        "incident_observer_installed": False,
        "incident_observer_installed_version": {"rc": 1, "stdout": ""},
    }

    assert jinja.compile_expression(first)(**production) is True
    assert (
        jinja.compile_expression(first)(
            **production, incident_observer_installation_name="livespec"
        )
        is False
    )
