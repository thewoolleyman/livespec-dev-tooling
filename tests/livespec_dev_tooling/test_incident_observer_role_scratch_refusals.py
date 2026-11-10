"""The scratch instance's refusals hold under operator typos, judged by ansible-core itself.

livespec-dev-tooling-32qdja. The scratch apply and its teardown run on the
PRODUCTION host as production's own account, so nothing but the role's asserts
stands between a mistyped `-e` override and production's receipts, recovery
journal, credentials or venv. The independent review of
livespec-dev-tooling#3969 showed that a plain string comparison let a trailing
slash, an ancestor directory or a `..` name through.

Every verdict here comes from the pinned ansible-core's own template engine
(`Templar.evaluate_conditional`, the `ansible-apply` recipe's exact pin, run
through `uvx` as `just ansible-apply` runs it), over the role's committed
assert expressions and variables. Nothing is emulated. All cases go to the
engine in one batch, once per module.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.livespec_dev_tooling import test_incident_observer_role_production_unchanged as base

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-32qdja
_REPO_ROOT = base.ROLE.parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_SCRATCH_VARS = base.ROLE / "vars" / "scratch.yml"
_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")
_ENGINE_TIMEOUT_SECONDS = 600
_PREFLIGHT = "tasks/scratch_preflight.yml"
_TEARDOWN = "tasks/scratch_teardown.yml"
_MAIN = "tasks/main.yml"
_FACTS = "Name the layout the scratch name fixes, and every path production owns"
_NAME = "Refuse a scratch name that is not one safe path segment, or production's branch or port"
_SHARED = "Refuse a scratch run that would move anything the two instances share"
_LAYOUT = "Refuse a scratch layout other than the one its name fixes"
_DISJOINT = "Refuse any scratch path that is, sits inside, or contains a path production owns"
_ASSERTS = (_NAME, _SHARED, _LAYOUT, _DISJOINT)
_VENV = "Refuse a scratch apply onto a venv production does not already serve"
_READY = "Name whether the reference clone can be read on this run"
_TEARDOWN_NAMES = "Name what the teardown removes and every production path it reads back"
_READ_BACK = "Refuse a teardown that moved a byte of production"
_PURGE = "Remove the scratch evidence store only when asked"

# The engine runs as its own interpreter: ansible-core 2.21 needs Python 3.12,
# above this repository's floor, so it is invoked, never imported (ansible/README.md).
_ENGINE = r"""
import json
import sys

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template


def trusted(value):
    # Ansible trusts every string it reads from a role or vars file as a template.
    if isinstance(value, str):
        return trust_as_template(value)
    if isinstance(value, list):
        return [trusted(item) for item in value]
    if isinstance(value, dict):
        return {key: trusted(item) for key, item in value.items()}
    return value


def judge(templar, condition):
    try:
        return bool(templar.evaluate_conditional(trusted(condition)))
    except Exception as error:  # a refusal by error is reported, never hidden
        return f"error: {type(error).__name__}: {error}"


replies = []
for case in json.load(sys.stdin):
    templar = Templar(loader=DataLoader(), variables=trusted(case["variables"]))
    replies.append(
        {
            "conditions": [judge(templar, condition) for condition in case["conditions"]],
            "templates": [str(templar.template(trusted(text))) for text in case["templates"]],
        }
    )
json.dump(replies, sys.stdout)
"""

Production = dict[str, Any]
Override = Callable[[Production], object]


def _pin() -> str:
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, "the justfile must carry the `ansible-apply *args:` recipe"
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, "the `ansible-apply` recipe must pin ansible-core exactly"
    return pin[0]


def _task(*, relative: str, name: str) -> dict[str, Any]:
    (task,) = [task for task in base.role_yaml(relative=relative) if task.get("name") == name]
    return task


def _production() -> Production:
    return base.role_yaml(relative="defaults/main.yml")


def _variables(*, overrides: dict[str, Override]) -> dict[str, Any]:
    """A scratch run's variables in Ansible's precedence: defaults, vars file, facts, `-e`."""
    production = _production()
    variables: dict[str, Any] = {**production, "incident_observer_candidate_user": "candidate"}
    variables.update(yaml.safe_load(_SCRATCH_VARS.read_text(encoding="utf-8")))
    variables["incident_observer_production"] = production
    variables.update(_task(relative=_PREFLIGHT, name=_FACTS)["ansible.builtin.set_fact"])
    variables.update({key: override(production) for key, override in overrides.items()})
    return variables


def _assert_case(*, relative: str, name: str, variables: dict[str, Any]) -> dict[str, Any]:
    task = _task(relative=relative, name=name)
    return {
        "variables": {**variables, **task.get("vars", {})},
        "conditions": task["ansible.builtin.assert"]["that"],
        "templates": [],
    }


def _home(production: Production) -> str:
    return production["incident_observer_home"]


# Each case: an id, the `-e` overrides (computed from production's own values, so
# no host path is spelled here), and the asserts expected to REFUSE it.
_CASES: list[tuple[str, dict[str, Override], frozenset[str]]] = [
    ("committed-defaults", {}, frozenset()),
    ("another-safe-name", {"incident_observer_scratch_name": lambda _: "drill-2"}, frozenset()),
    (
        "dotdot-name",
        {"incident_observer_scratch_name": lambda _: "x/../.."},
        frozenset({_NAME, _DISJOINT}),
    ),
    ("slash-name", {"incident_observer_scratch_name": lambda _: "a/b"}, frozenset({_NAME})),
    ("dot-name", {"incident_observer_scratch_name": lambda _: ".."}, frozenset({_NAME})),
    ("newline-name", {"incident_observer_scratch_name": lambda _: "abc\n"}, frozenset({_NAME})),
    ("upper-name", {"incident_observer_scratch_name": lambda _: "Thhgeg"}, frozenset({_NAME})),
    ("hyphen-lead-name", {"incident_observer_scratch_name": lambda _: "-x"}, frozenset({_NAME})),
    ("empty-name", {"incident_observer_scratch_name": lambda _: ""}, frozenset({_NAME})),
    ("long-name", {"incident_observer_scratch_name": lambda _: "a" * 41}, frozenset({_NAME})),
    ("master-branch", {"incident_observer_target_branch": lambda _: "master"}, frozenset({_NAME})),
    ("empty-branch", {"incident_observer_target_branch": lambda _: ""}, frozenset({_NAME})),
    (
        "production-port",
        {"incident_observer_port": lambda p: p["incident_observer_port"]},
        frozenset({_NAME}),
    ),
    (
        "root-is-home-with-trailing-slash",
        {"incident_observer_scratch_root": lambda p: _home(p) + "/"},
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "root-is-ancestor-of-home",
        {"incident_observer_scratch_root": lambda p: str(Path(_home(p)).parent)},
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "root-is-production-state",
        {"incident_observer_scratch_root": lambda p: p["incident_observer_state_dir"] + "/."},
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "state-inside-production-reference",
        {
            "incident_observer_state_dir": lambda p: p["incident_observer_reference_dir"]
            + "/receipts"
        },
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "state-is-production-venv",
        {"incident_observer_state_dir": lambda p: p["incident_observer_venv"]},
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "manifest-is-recovery-app",
        {"incident_observer_manifest_path": lambda p: p["incident_observer_recovery_app_path"]},
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "config-is-reader-env",
        {"incident_observer_config_path": lambda p: p["incident_observer_reader_env_path"]},
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "config-is-control-secret",
        {"incident_observer_config_path": lambda p: p["incident_observer_secrets"][1]["path"]},
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "manifest-inside-reader-clone",
        {
            "incident_observer_manifest_path": lambda p: p["incident_observer_reader_dir"]
            + "/m.json"
        },
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "config-is-production-config",
        {"incident_observer_config_path": lambda p: p["incident_observer_config_path"]},
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "unit-path-is-production-unit",
        {"incident_observer_unit_path": lambda p: p["incident_observer_unit_path"]},
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "fetch-service-is-production-fetch-service",
        {
            "incident_observer_fetch_service_path": lambda p: p[
                "incident_observer_fetch_service_path"
            ]
        },
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "fetch-timer-is-production-fetch-timer",
        {"incident_observer_fetch_timer_path": lambda p: p["incident_observer_fetch_timer_path"]},
        frozenset({_LAYOUT, _DISJOINT}),
    ),
    (
        "unit-name-is-production-unit",
        {"incident_observer_unit_name": lambda p: p["incident_observer_unit_name"]},
        frozenset({_LAYOUT}),
    ),
    (
        "fetch-unit-name-is-production-fetch",
        {"incident_observer_fetch_unit_name": lambda p: p["incident_observer_fetch_unit_name"]},
        frozenset({_LAYOUT}),
    ),
    (
        "moved-recovery-app",
        {
            "incident_observer_recovery_app_path": lambda p: p["incident_observer_etc_dir"]
            + "/other.json"
        },
        frozenset({_SHARED}),
    ),
    (
        "moved-reader-env",
        {
            "incident_observer_reader_env_path": lambda p: p["incident_observer_etc_dir"]
            + "/other.env"
        },
        frozenset({_SHARED}),
    ),
    (
        "moved-secrets",
        {"incident_observer_secrets": lambda p: p["incident_observer_secrets"][:2]},
        frozenset({_SHARED}),
    ),
    (
        "moved-venv",
        {"incident_observer_venv": lambda p: p["incident_observer_install_dir"] + "/v2"},
        frozenset({_SHARED}),
    ),
    (
        "moved-home",
        {"incident_observer_home": lambda p: _home(p) + "-2"},
        frozenset({_SHARED, _LAYOUT}),
    ),
    ("moved-account", {"incident_observer_user": lambda _: "root"}, frozenset({_SHARED})),
]

# The disjointness assert alone: a scratch state directory equal to each path
# production owns is refused by that list. For a file path no other entry
# covers (the fetch service and timer, review finding 5) dropping the entry
# from the list fails here.
_EXCLUSIVE_KEYS = (
    "incident_observer_config_path",
    "incident_observer_manifest_path",
    "incident_observer_state_dir",
    "incident_observer_reference_dir",
    "incident_observer_unit_path",
    "incident_observer_fetch_service_path",
    "incident_observer_fetch_timer_path",
    "incident_observer_install_dir",
    "incident_observer_venv",
    "incident_observer_bin_dir",
    "incident_observer_reader_dir",
    "incident_observer_reader_env_path",
    "incident_observer_recovery_app_path",
)


def _exclusive_cases() -> list[tuple[str, str]]:
    production = _production()
    paths = [(key, production[key]) for key in _EXCLUSIVE_KEYS]
    paths += [
        (f"secret:{secret['name']}", secret["path"])
        for secret in production["incident_observer_secrets"]
    ]
    return paths


def _batch() -> list[dict[str, Any]]:
    cases = [
        _assert_case(relative=_PREFLIGHT, name=name, variables=_variables(overrides=overrides))
        for _, overrides, _ in _CASES
        for name in _ASSERTS
    ]
    for _, path in _exclusive_cases():
        # The scratch state directory set to exactly one production path, with
        # the layout list moved alongside it so only the disjointness list judges.
        variables = _variables(overrides={})
        variables["incident_observer_state_dir"] = path
        cases.append(_assert_case(relative=_PREFLIGHT, name=_DISJOINT, variables=variables))
    return cases


def _run_engine(*, cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    completed = subprocess.run(
        ["uvx", "--from", _pin(), "python", "-I", "-c", _ENGINE],
        input=json.dumps(cases),
        env=env,
        capture_output=True,
        text=True,
        timeout=_ENGINE_TIMEOUT_SECONDS,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    replies = json.loads(completed.stdout)
    assert isinstance(replies, list)
    assert len(replies) == len(cases)
    return replies


@pytest.fixture(scope="module")
def verdicts() -> list[dict[str, Any]]:
    """The engine's verdict on every batched case, once per module."""
    return _run_engine(cases=_batch())


def _holds(*, reply: dict[str, Any]) -> bool:
    conditions = reply["conditions"]
    assert all(isinstance(verdict, bool) for verdict in conditions), conditions
    return all(conditions)


@pytest.mark.parametrize(
    ("index", "case"), list(enumerate(_CASES)), ids=[case[0] for case in _CASES]
)
def test_each_refusal_holds_or_refuses_exactly_as_ansible_judges_it(
    verdicts: list[dict[str, Any]],
    *,
    index: int,
    case: tuple[str, dict[str, Override], frozenset[str]],
) -> None:
    _, _, refused_by = case
    replies = verdicts[index * len(_ASSERTS) : (index + 1) * len(_ASSERTS)]

    refused = {
        name for name, reply in zip(_ASSERTS, replies, strict=True) if not _holds(reply=reply)
    }

    assert refused == refused_by


@pytest.mark.parametrize(
    ("offset", "label"),
    list(enumerate(label for label, _ in _exclusive_cases())),
    ids=[label for label, _ in _exclusive_cases()],
)
def test_the_disjointness_list_itself_refuses_every_production_path(
    verdicts: list[dict[str, Any]], *, offset: int, label: str
) -> None:
    reply = verdicts[len(_CASES) * len(_ASSERTS) + offset]

    assert not _holds(reply=reply), label


def test_the_preflight_names_every_production_path_the_two_instances_share() -> None:
    facts = _task(relative=_PREFLIGHT, name=_FACTS)["ansible.builtin.set_fact"]
    listed = facts["incident_observer_production_exclusive_paths"]
    parents = facts["incident_observer_production_parent_paths"]

    for key in _EXCLUSIVE_KEYS:
        assert f"incident_observer_production.{key}" in listed, key
    assert "incident_observer_secrets | map(attribute='path')" in listed
    assert parents == [
        "{{ incident_observer_production.incident_observer_home }}",
        "{{ incident_observer_production.incident_observer_etc_dir }}",
    ]


def test_the_apply_and_the_teardown_take_the_same_preflight_before_any_write() -> None:
    main = base.role_yaml(relative=_MAIN)
    teardown = base.role_yaml(relative=_TEARDOWN)
    include = {"ansible.builtin.include_tasks": "scratch_preflight.yml"}
    writes = {
        "ansible.builtin.apt",
        "ansible.builtin.user",
        "ansible.builtin.file",
        "ansible.builtin.copy",
        "ansible.builtin.template",
        "ansible.builtin.git",
        "ansible.builtin.systemd_service",
    }

    def first_scratch_write(tasks: list[dict[str, Any]]) -> int:
        """The first task a scratch run would execute that can write to the host."""
        return min(
            index
            for index, task in enumerate(tasks)
            if writes & set(task)
            and not str(task.get("when", "")).startswith("not (incident_observer_scratch | bool)")
        )

    (preflight,) = [i for i, task in enumerate(main) if include.items() <= task.items()]
    venv = [task.get("name") for task in main].index(_VENV)
    assert main[preflight]["when"] == "incident_observer_scratch | bool"
    assert preflight < venv < first_scratch_write(main)
    assert include.items() <= teardown[0].items()
    assert first_scratch_write(teardown) > 0


def test_a_purge_removes_only_the_scratch_root_its_validated_name_fixes() -> None:
    purge = _task(relative=_TEARDOWN, name=_PURGE)
    variables = _variables(
        overrides={"incident_observer_scratch_root": lambda p: str(Path(_home(p)).parent)}
    )
    (reply,) = _run_engine(
        cases=[
            {
                "variables": variables,
                "conditions": [],
                "templates": [purge["ansible.builtin.file"]["path"]],
            }
        ]
    )

    assert "incident_observer_scratch_root" not in purge["ansible.builtin.file"]["path"]
    assert reply["templates"] == [_home(_production()) + "/scratch-thhgeg"]
    assert purge["when"] == "incident_observer_scratch_teardown_purge | bool"


def _read_back(*, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    variables = _variables(overrides={})
    variables.update(_task(relative=_TEARDOWN, name=_TEARDOWN_NAMES)["ansible.builtin.set_fact"])
    variables.update(before)
    variables.update(after)
    return _assert_case(relative=_TEARDOWN, name=_READ_BACK, variables=variables)


def _readings(
    *, prefix: str, checksum: str, exists: bool, files: list[dict[str, str]]
) -> dict[str, Any]:
    return {
        f"incident_observer_production_{prefix}": {
            "results": [
                {"stat": {"exists": exists, "checksum": checksum}},
                {"stat": {"exists": True}},
            ]
        },
        f"incident_observer_production_state_{prefix}": {"files": files},
    }


def test_the_teardown_read_back_refuses_any_moved_production_byte_or_journal_entry() -> None:
    journal = [
        {"path": "receipts/a.json", "checksum": "1"},
        {"path": "receipts/j/b.json", "checksum": "2"},
    ]
    same = _readings(prefix="before", checksum="x", exists=True, files=journal)
    cases = [
        _read_back(
            before=same, after=_readings(prefix="after", checksum="x", exists=True, files=journal)
        ),
        _read_back(
            before=same, after=_readings(prefix="after", checksum="y", exists=True, files=journal)
        ),
        _read_back(
            before=same, after=_readings(prefix="after", checksum="", exists=False, files=journal)
        ),
        _read_back(
            before=same,
            after=_readings(prefix="after", checksum="x", exists=True, files=journal[:1]),
        ),
        _read_back(
            before=same,
            after=_readings(
                prefix="after",
                checksum="x",
                exists=True,
                files=[journal[0], {**journal[1], "checksum": "3"}],
            ),
        ),
    ]

    held = [_holds(reply=reply) for reply in _run_engine(cases=cases)]

    assert held == [True, False, False, False, False]


def test_the_teardown_reads_back_every_production_credential_unit_and_its_state() -> None:
    names = _task(relative=_TEARDOWN, name=_TEARDOWN_NAMES)["ansible.builtin.set_fact"]
    files = names["incident_observer_production_files"]

    for key in (
        "incident_observer_unit_path",
        "incident_observer_config_path",
        "incident_observer_manifest_path",
        "incident_observer_fetch_service_path",
        "incident_observer_fetch_timer_path",
        "incident_observer_recovery_app_path",
        "incident_observer_reader_env_path",
    ):
        assert f"incident_observer_production.{key}" in files, key
    assert "incident_observer_secrets | map(attribute='path')" in files
    assert (
        "{{ incident_observer_production.incident_observer_state_dir }}"
        in (names["incident_observer_production_directories"])
    )


@pytest.mark.parametrize(
    ("check_mode", "exists", "ready"),
    [(True, False, False), (True, True, True), (False, False, True), (False, True, True)],
)
def test_a_dry_run_tolerates_an_absent_reference_clone_and_an_apply_does_not(
    *, check_mode: bool, exists: bool, ready: bool
) -> None:
    fact = _task(relative=_MAIN, name=_READY)["ansible.builtin.set_fact"]
    variables = _variables(overrides={})
    variables.update(
        {
            "ansible_check_mode": check_mode,
            "incident_observer_account_ready": True,
            "incident_observer_reference_config_stat": {"stat": {"exists": exists}},
        }
    )
    (expression,) = fact.values()
    (reply,) = _run_engine(
        cases=[
            {
                "variables": variables,
                "conditions": [expression.strip()[2:-2].strip()],
                "templates": [],
            }
        ]
    )

    assert reply["conditions"] == [ready]
