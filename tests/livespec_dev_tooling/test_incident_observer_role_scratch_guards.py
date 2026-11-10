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

import json
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
_SCRATCH_INCLUDE = "Converge the scratch instance only through its refusals"
_PRODUCTION_INCLUDE = "Converge the production instance"
_PUBLISH = "Publish only the declared paths through a path-scoped funnel"
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
    "Name the funnel grant and each public path's current disposition",
    "Name the public paths' disposition in the run output",
    "Read the funnel configuration back after publishing",
    "Refuse a funnel port that publishes a path beyond the declared list",
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
        task for task in base.role_yaml(relative="tasks/converge.yml") if task.get("name") == name
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
    dispatch = {task["name"]: task["when"] for task in base.role_yaml(relative="tasks/main.yml")}
    conditions = [dispatch[_SCRATCH_INCLUDE], dispatch[_PRODUCTION_INCLUDE], _GUARD]

    verdicts = _judge(cases=[(variables, conditions) for _, variables, _ in _IDENTIFIED])

    assert " ".join(dispatch[_PRODUCTION_INCLUDE].split()) == _GUARD
    for (label, _, identified), (scratch_path, production_path, shared_write_runs) in zip(
        _IDENTIFIED, verdicts, strict=True
    ):
        assert (scratch_path, production_path, shared_write_runs) == (
            identified,
            not identified,
            not identified,
        ), label


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


def _named_link(*, path: Path) -> str:
    """The link refusal's message, naming exactly one linked path and nothing else."""
    return f'"msg": "[\'{path}\']'


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
    assert _named_link(path=paths["incident_observer_scratch_root"]) in completed.stdout


@pytest.mark.parametrize(
    ("parent", "below"),
    [
        ("incident_observer_state_dir", "recovery-journal"),
        ("incident_observer_state_dir", "recovery-journal-contexts"),
        ("incident_observer_reference_dir", ".beads"),
        ("incident_observer_reference_dir", ".git"),
    ],
)
def test_the_host_check_refuses_a_link_below_the_scratch_root_the_apply_writes_through(
    tmp_path: Path, *, parent: str, below: str
) -> None:
    home = tmp_path / "home"
    production = home / "receipts" / below
    production.mkdir(parents=True)
    paths = _tree(home=home)
    paths[parent].mkdir(parents=True)
    link = paths[parent] / below
    link.symlink_to(production)

    completed = _run_host_check(root=tmp_path, paths=paths)

    assert completed.returncode != 0, completed.stdout
    assert _named_link(path=link) in completed.stdout


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


# A connection that records every call and executes nothing, so the committed
# scratch playbook can be run for real without reaching a host (the round-3
# review's method).
_RECORDING_CONNECTION = '''
DOCUMENTATION = """
name: recording
short_description: Record every call; execute nothing
description:
  - A test stand-in for livespec-dev-tooling's incident observer role tests.
author: livespec-dev-tooling
options: {}
"""

import json
import json
import os

from ansible.plugins.connection import ConnectionBase


class Connection(ConnectionBase):
    transport = "recording"
    has_pipelining = True
    always_pipeline_modules = True

    def _connect(self):
        self._connected = True
        return self

    def _record(self, kind, detail):
        with open(os.environ["RECORDING_LOG"], "a", encoding="utf-8") as log:
            log.write(json.dumps({"kind": kind, "detail": detail}) + "\\n")

    def exec_command(self, cmd, in_data=None, sudoable=True):
        super().exec_command(cmd, in_data=in_data, sudoable=sudoable)
        self._record("exec", cmd)
        if in_data:
            return 0, json.dumps({"changed": False, "ansible_facts": {}}).encode(), b""
        return 0, b"/nonexistent\\n", b""

    def put_file(self, in_path, out_path):
        super().put_file(in_path, out_path)
        self._record("put", out_path)

    def fetch_file(self, in_path, out_path):
        super().fetch_file(in_path, out_path)
        self._record("fetch", in_path)

    def close(self):
        self._connected = False
'''
_WRITE_MODULES = {
    "ansible.builtin.apt",
    "ansible.builtin.user",
    "ansible.builtin.file",
    "ansible.builtin.copy",
    "ansible.builtin.template",
    "ansible.builtin.git",
    "ansible.builtin.systemd_service",
    "ansible.builtin.command",
    "ansible.builtin.uri",
    "ansible.builtin.meta",
}
_PRE_TASK = "Refuse this scratch playbook without scratch mode, a scratch name and a scratch branch"


def _scratch_writes() -> list[str]:
    """Every converge task a scratch run would write, run or restart through."""
    return [
        task["name"]
        for task in base.role_yaml(relative="tasks/converge.yml")
        if _WRITE_MODULES & set(task)
    ] + [task["name"] for task in base.role_yaml(relative="tasks/scratch_apply.yml")]


@pytest.fixture(scope="module")
def recorded_host(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """An inventory whose one dev host is reached only through the recording connection."""
    root = tmp_path_factory.mktemp("recorded-host")
    plugins = root / "connection_plugins"
    plugins.mkdir()
    (plugins / "recording.py").write_text(_RECORDING_CONNECTION, encoding="utf-8")
    (root / "inventory.yml").write_text(
        yaml.safe_dump(
            {
                "dev_hosts": {
                    "hosts": {
                        "recorded": {
                            "ansible_connection": "recording",
                            "ansible_python_interpreter": "/usr/bin/python3",
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return root


def _run_scratch_playbook(*, root: Path, start_at: str) -> tuple[str, list[dict[str, Any]]]:
    log = root / f"recording-{abs(hash(start_at))}.jsonl"
    env = _plain_env()
    env.update(
        {
            "ANSIBLE_CONNECTION_PLUGINS": str(root / "connection_plugins"),
            "ANSIBLE_PIPELINING": "True",
            "RECORDING_LOG": str(log),
        }
    )
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            refusals.ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(root / "inventory.yml"),
            str(_PLAYBOOKS[0]),
            "--start-at-task",
            start_at,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    calls = [
        json.loads(line)
        for line in (log.read_text(encoding="utf-8").splitlines() if log.exists() else [])
    ]
    return completed.stdout + completed.stderr, calls


def _tasks_run(*, output: str) -> list[str]:
    return [
        line.split("TASK [", 1)[1].split("]", 1)[0]
        for line in output.splitlines()
        if line.startswith("TASK [") and not line.startswith("TASK [Gathering Facts]")
    ]


@pytest.mark.parametrize("task", _scratch_writes())
def test_start_at_task_naming_any_scratch_write_finds_nothing_to_run(
    recorded_host: Path, task: str
) -> None:
    output, calls = _run_scratch_playbook(root=recorded_host, start_at=task)

    assert f'No matching task "{task}" found' in output, output
    assert _tasks_run(output=output) == [], output
    # Only the play's own fact gathering reaches the connection.
    assert len([call for call in calls if call["kind"] == "put"]) == 0, calls
    assert len([call for call in calls if call["kind"] == "exec"]) <= 1, calls


def test_the_recording_harness_sees_a_task_it_can_reach(recorded_host: Path) -> None:
    """The control: a static task IS found and run, so silence above is not a blind harness."""
    output, calls = _run_scratch_playbook(root=recorded_host, start_at=_PRE_TASK)

    assert _PRE_TASK in _tasks_run(output=output), output
    assert "incident_observer : Read each scratch path on the host as root" in output, output
    assert any(call["kind"] == "exec" for call in calls), calls
