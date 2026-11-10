"""No spelling of the scratch flag, and no started-late play, sends a scratch run down production's path.

livespec-dev-tooling-32qdja, re-review of livespec-dev-tooling#3969 at
`188b9c2d`. Three guards close what that review found:

- the role takes the scratch preflight whenever ANY scratch-identifying
  variable is set (the flag, the name, a target branch), and the preflight's
  first assert refuses scratch variables without scratch mode, so
  `-e incident_observer_scratch=false` on the scratch playbook refuses instead
  of taking production's path;
- each production-shared write and each funnel task carries that refusal on
  the task itself, so even a play started past the preflight with
  `--start-at-task` cannot re-point production's public `/callback` funnel or
  write a shared file;
- both scratch playbooks refuse, as their first task, unless scratch mode, a
  name and an `incident-scratch/` branch are set.

A fourth closes the symlink case: the preflight reads each scratch path on the
HOST without following links and refuses a link. That check is exercised by
running the role's own two tasks through the pinned `ansible-playbook` on a
throwaway tree. Every other verdict comes from the pinned ansible-core's
Templar (see test_incident_observer_role_scratch_refusals.py).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.livespec_dev_tooling import test_incident_observer_role_production_unchanged as base
from tests.livespec_dev_tooling import test_incident_observer_role_scratch_refusals as refusals

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-32qdja
_ANSIBLE = base.ROLE.parents[1]
_PLAYBOOKS = (
    _ANSIBLE / "incident-observer-scratch.yml",
    _ANSIBLE / "incident-observer-scratch-teardown.yml",
)
_PLAYBOOK_TIMEOUT_SECONDS = 600
_INCLUDE = "Take the scratch instance's refusals before writing anything"
_PUBLISH = "Publish only the callback path through a path-scoped funnel"
_STAT = "Read each scratch path on the host as root, without following a link"
_LINK = "Refuse a scratch path that is a symbolic link on the host"
_GUARD = (
    "not (incident_observer_scratch | bool)"
    " and incident_observer_scratch_name is not defined"
    " and incident_observer_target_branch | default('', true) | length == 0"
)
_GUARDED = (
    "Install the interpreter's venv module and git",
    "Create the controller account",
    "Create the root-owned installation directories",
    "Create the protected configuration directory",
    "Create the controller account's home",
    "Create the isolated venv on the system interpreter",
    "Install the released distribution from its tag, never from a checkout",
    "Clone the canonical reader at its released tag",
    "Write each secret from the control node's projected environment",
    "Write the canonical reader's credential as the unit's environment file",
    "Write the recovery App credential the principal reads beside controller.json",
    "Install the manifest renderer outside the package and the clones",
    "Read this node's tailscale serve and funnel configuration",
    "Read whether the tailnet grants this node the funnel attribute",
    "Name the funnel grant and the callback path's current disposition",
    "Name the public callback path's disposition in the run output",
    _PUBLISH,
)
_SCRATCH_PATH_VARIABLES = (
    "incident_observer_scratch_root",
    "incident_observer_state_dir",
    "incident_observer_reference_dir",
    "incident_observer_config_path",
    "incident_observer_manifest_path",
    "incident_observer_unit_path",
    "incident_observer_fetch_service_path",
    "incident_observer_fetch_timer_path",
)


def _main_task(*, name: str) -> dict[str, Any]:
    (task,) = [
        task for task in base.role_yaml(relative="tasks/main.yml") if task.get("name") == name
    ]
    return task


def _production_variables(*, extra: dict[str, Any]) -> dict[str, Any]:
    """The production apply's variables (ansible/dev-host.yml), plus any `-e`."""
    return {**base.production_variables(), **extra}


def _scratch_variables(*, extra: dict[str, Any]) -> dict[str, Any]:
    """The scratch playbook's variables (vars/scratch.yml loaded), plus any `-e`."""
    return {**refusals.scratch_run_variables(overrides={}), **extra}


def _judge(*, cases: list[tuple[dict[str, Any], list[str]]]) -> list[list[object]]:
    replies = refusals.run_engine(
        cases=[
            {"variables": variables, "conditions": conditions, "templates": []}
            for variables, conditions in cases
        ]
    )
    return [reply["conditions"] for reply in replies]


_IDENTIFIED = [
    ("production", _production_variables(extra={}), False),
    (
        "production-with-scratch-flag",
        _production_variables(extra={"incident_observer_scratch": True}),
        True,
    ),
    (
        "production-with-a-scratch-name",
        _production_variables(extra={"incident_observer_scratch_name": "32qdja-x"}),
        True,
    ),
    (
        "production-with-a-target-branch",
        _production_variables(
            extra={"incident_observer_target_branch": "incident-scratch/32qdja-x"}
        ),
        True,
    ),
    ("scratch-playbook", _scratch_variables(extra={}), True),
    (
        "scratch-playbook-flag-false",
        _scratch_variables(extra={"incident_observer_scratch": False}),
        True,
    ),
    (
        "scratch-playbook-flag-no",
        _scratch_variables(extra={"incident_observer_scratch": "no"}),
        True,
    ),
    (
        "scratch-playbook-flag-zero",
        _scratch_variables(extra={"incident_observer_scratch": "0"}),
        True,
    ),
]


def test_the_role_takes_the_preflight_whenever_any_scratch_variable_is_set() -> None:
    include = _main_task(name=_INCLUDE)["when"]
    guard = _GUARD

    verdicts = _judge(cases=[(variables, [include, guard]) for _, variables, _ in _IDENTIFIED])

    for (label, _, identified), (takes_preflight, shared_write_runs) in zip(
        _IDENTIFIED, verdicts, strict=True
    ):
        assert (takes_preflight, shared_write_runs) == (identified, not identified), label


@pytest.mark.parametrize("name", _GUARDED)
def test_each_shared_write_and_funnel_task_carries_the_guard_on_itself(name: str) -> None:
    when = _main_task(name=name)["when"]
    first = when[0] if isinstance(when, list) else when

    assert " ".join(first.split()).startswith(_GUARD), name


def test_the_funnel_publish_never_runs_with_a_scratch_variable_set_even_started_late() -> None:
    publish = _main_task(name=_PUBLISH)["when"]
    granted = {"incident_observer_funnel_granted": True, "incident_observer_funnel_served": False}

    verdicts = _judge(
        cases=[
            (_production_variables(extra=granted), [publish]),
            (_scratch_variables(extra={**granted, "incident_observer_scratch": False}), [publish]),
            (
                _scratch_variables(extra={**granted, "incident_observer_scratch": "False"}),
                [publish],
            ),
        ]
    )

    assert verdicts == [[True], [False], [False]]


_PLAYBOOK_CASES = [
    ("committed", {}, True),
    ("flag-false", {"incident_observer_scratch": False}, False),
    ("flag-no", {"incident_observer_scratch": "no"}, False),
    ("flag-zero", {"incident_observer_scratch": "0"}, False),
    ("branch-master", {"incident_observer_target_branch": "master"}, False),
    ("branch-refs-heads-master", {"incident_observer_target_branch": "refs/heads/master"}, False),
    ("branch-32qdja", {"incident_observer_target_branch": "incident-scratch/32qdja-proof"}, True),
]


@pytest.mark.parametrize("playbook", _PLAYBOOKS, ids=lambda path: path.name)
def test_each_scratch_playbook_refuses_first_without_scratch_mode_name_and_branch(
    playbook: Path,
) -> None:
    (play,) = yaml.safe_load(playbook.read_text(encoding="utf-8"))
    first = play["pre_tasks"][0]
    that = first["ansible.builtin.assert"]["that"]

    verdicts = _judge(
        cases=[(_scratch_variables(extra=extra), that) for _, extra, _ in _PLAYBOOK_CASES]
    )

    assert list(play)[:5] == ["name", "hosts", "gather_facts", "vars_files", "pre_tasks"]
    for (label, _, holds), conditions in zip(_PLAYBOOK_CASES, verdicts, strict=True):
        assert all(isinstance(verdict, bool) for verdict in conditions), (label, conditions)
        assert all(conditions) is holds, label


def _plain_env() -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update({"ANSIBLE_NOCOWS": "1", "ANSIBLE_LOCALHOST_WARNING": "false"})
    return env


def _run_host_check(*, root: Path, paths: dict[str, Path]) -> subprocess.CompletedProcess[str]:
    """Run the preflight's own stat and link refusal, as committed, over a throwaway tree.

    The one change: `become` is dropped, because the test runs as an ordinary
    account; on the host the stat runs as root. A path the account cannot read
    then fails the stat, which refuses as surely as the link assert does.
    """
    tasks = [
        {key: value for key, value in task.items() if key != "become"}
        for task in base.role_yaml(relative="tasks/scratch_preflight.yml")
        if task.get("name") in {_STAT, _LINK}
    ]
    assert [task["name"] for task in tasks] == [_STAT, _LINK]
    play = root / "host-check.yml"
    play.write_text(
        yaml.safe_dump(
            [
                {
                    "hosts": "localhost",
                    "connection": "local",
                    "gather_facts": False,
                    "vars": {key: str(path) for key, path in paths.items()},
                    "tasks": tasks,
                }
            ]
        ),
        encoding="utf-8",
    )
    return subprocess.run(
        [
            "uvx",
            "--from",
            refusals.ansible_core_pin(),
            "ansible-playbook",
            "-i",
            "localhost,",
            str(play),
        ],
        cwd=root,
        env=_plain_env(),
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )


def _tree(*, home: Path) -> dict[str, Path]:
    """The eight scratch paths beneath a throwaway home, in the role's layout."""
    root = home / "scratch-32qdja-drill"
    names = (
        root,
        root / "receipts",
        root / "reference",
        home / "controller-scratch-32qdja-drill.json",
        home / "released-installation-scratch-32qdja-drill.json",
        home / "observer-scratch.service",
        home / "fetch-scratch.service",
        home / "fetch-scratch.timer",
    )
    return dict(zip(_SCRATCH_PATH_VARIABLES, names, strict=True))


def test_the_host_check_passes_real_and_absent_scratch_paths(tmp_path: Path) -> None:
    home = tmp_path / "home"
    paths = _tree(home=home)
    paths["incident_observer_state_dir"].mkdir(parents=True)

    completed = _run_host_check(root=tmp_path, paths=paths)

    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "no scratch path is a link on the host" in completed.stdout


def test_the_host_check_refuses_a_scratch_root_linked_into_production_receipts(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    receipts = home / "receipts"
    receipts.mkdir(parents=True)
    paths = _tree(home=home)
    paths["incident_observer_scratch_root"].symlink_to(receipts)

    completed = _run_host_check(root=tmp_path, paths=paths)

    assert completed.returncode != 0, completed.stdout
    assert "is a symbolic link on the host" in completed.stdout


def test_the_host_check_refuses_a_link_the_control_node_cannot_see_behind_an_unreadable_parent(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    paths = _tree(home=home)
    home.mkdir()
    paths["incident_observer_scratch_root"].symlink_to(receipts)
    home.chmod(0o000)
    try:
        completed = _run_host_check(root=tmp_path, paths=paths)
    finally:
        home.chmod(0o700)

    assert completed.returncode != 0, completed.stdout
    assert "no scratch path is a link on the host" not in completed.stdout
