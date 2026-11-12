"""Consumer-tier coverage for retiring Fabro sandbox environments.

The catalog is state owned by the running Fabro instance, not a rendered file.
This scenario therefore reads the role's task graph: it must first obtain every
non-terminal run's persisted settings, reject an environment still selected by
one of them, and only then issue the authenticated catalog DELETE.  Reading the
task graph keeps the safety ordering observable without requiring a reachable
factory host in a repository test.
"""

from __future__ import annotations

import json
import re
from itertools import pairwise
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_ROOT = Path(__file__).resolve().parents[2]
_MAIN = _ROOT / "ansible" / "roles" / "fabro_server" / "tasks" / "main.yml"
_RETIRED_ENVIRONMENT = _MAIN.with_name("retired_environment.yml")
_RETIRED_RUN = _MAIN.with_name("retired_run.yml")
_INVENTORY = _ROOT / "ansible" / "inventory" / "host_vars" / "gmktec-xubuntu.yml"
_HOST_VARS = _ROOT / "ansible" / "roles" / "fabro_server" / "HOST_VARS.md"
_HEADING_COVERAGE = _ROOT / "tests" / "heading-coverage.json"


def _tasks(*, source: Path) -> list[tuple[str, str]]:
    """Return each column-zero Ansible task in source order."""
    assert source.is_file(), f"the role must carry {source.name}"
    text = source.read_text(encoding="utf-8")
    starts = [match.start() for match in re.finditer(r"^- name: ", text, re.MULTILINE)]
    assert starts, f"{source.name} must have named top-level tasks"
    return [
        (body.split("\n", 1)[0][len("- name: ") :].strip(), body)
        for start, stop in pairwise([*starts, len(text)])
        for body in [text[start:stop]]
    ]


def _task(*, source: Path, name: str) -> str:
    """Return one uniquely named role task."""
    matching = [body for task_name, body in _tasks(source=source) if task_name == name]
    assert len(matching) == 1, f"{source.name} must carry exactly one {name!r} task"
    return matching[0]


def _index(*, source: Path, name: str) -> int:
    """Return a task's position, preserving the role's safety order."""
    names = [task_name for task_name, _ in _tasks(source=source)]
    assert name in names, f"{source.name} must carry {name!r}"
    return names.index(name)


def test_the_role_reads_all_live_runs_before_retiring_catalog_entries() -> None:
    """A live run blocks every delete, and a 404 delete is an unchanged converge."""
    resolve = _task(source=_MAIN, name="Resolve this instance's axes")
    assert "fabro_server_retired_environments" in resolve

    overlap = "Refuse an environment id declared both active and retired"
    first_write = "Create the shared libexec directory"
    assert _index(source=_MAIN, name=overlap) < _index(source=_MAIN, name=first_write)

    read_runs = _task(
        source=_MAIN, name="Read this instance's non-terminal runs before retiring environments"
    )
    assert "/api/v1/runs" in read_runs
    assert "--header @-" in read_runs
    assert "FABRO_SERVER_ENV_FILE" in read_runs
    assert "include_tasks: retired_run.yml" in _task(
        source=_MAIN, name="Read every non-terminal run's selected environment"
    )
    assert (
        _index(source=_MAIN, name="Read every non-terminal run's selected environment")
        < _index(
            source=_MAIN, name="Refuse to retire an environment selected by a non-terminal run"
        )
        < _index(source=_MAIN, name="Delete each retired sandbox environment")
    )

    settings = _task(source=_RETIRED_RUN, name="Read this non-terminal run's settings")
    assert "/settings" in settings
    assert "--header @-" in settings
    assert "FABRO_SERVER_ENV_FILE" in settings
    assert "environment.id" in _task(
        source=_RETIRED_RUN, name="Record this non-terminal run's selected environment"
    )

    delete = _task(
        source=_RETIRED_ENVIRONMENT,
        name="Delete this retired environment from the instance's catalog",
    )
    assert "--request DELETE" in delete
    assert "--header @-" in delete
    assert "FABRO_SERVER_ENV_FILE" in delete
    assert "204" in delete and "404" in delete
    assert "changed_when" in delete


def _instance_block(*, unit: str) -> str:
    """Return one inventory instance mapping, excluding its siblings."""
    text = _INVENTORY.read_text(encoding="utf-8")
    opener = f"  - unit_name: {unit}\n"
    start = text.find(opener)
    assert start >= 0, f"gmktec inventory must declare {unit}"
    stop = text.find("\n  - unit_name: ", start + len(opener))
    return text[start:] if stop < 0 else text[start:stop]


def _list_items(*, block: str, key: str) -> list[str]:
    """Return scalar list items from one instance mapping."""
    match = re.search(
        rf"^    {re.escape(key)}:\n(?P<items>(?:^      - [^\n]+\n)+)", block, re.MULTILINE
    )
    return [] if match is None else [line[8:] for line in match["items"].splitlines()]


def _environment_ids(*, block: str) -> list[str]:
    """Return the catalog ids that one mapping still declares active."""
    return re.findall(r"^      - id: ([^\s]+)$", block, re.MULTILINE)


def test_gmktec_declares_the_completed_environment_rename_and_its_operator_interface() -> None:
    """The fleet and homelab mappings retire only their replaced ids."""
    fleet = _instance_block(unit="fabro-server")
    candidate = _instance_block(unit="fabro-server-candidate")
    homelab = _instance_block(unit="fabro-server-mi-homelab")

    assert not {"livespec-ci", "livespec-ci-k8s", "livespec-ci-rust"} & set(
        _environment_ids(block=fleet)
    )
    assert _list_items(block=fleet, key="retired_environments") == [
        "livespec-ci",
        "livespec-ci-k8s",
        "livespec-ci-rust",
    ]
    assert "retired_environments" not in candidate
    assert {"livespec-ci", "livespec-ci-k8s", "livespec-ci-rust"} <= set(
        _environment_ids(block=candidate)
    )
    assert _environment_ids(block=homelab) == ["factory-python"]
    assert _list_items(block=homelab, key="retired_environments") == ["livespec-ci"]

    document = _HOST_VARS.read_text(encoding="utf-8")
    assert "| `retired_environments` |" in document
    assert "DELETE /api/v1/environments/{id}" in document
    assert "non-terminal run" in document

    coverage = json.loads(_HEADING_COVERAGE.read_text(encoding="utf-8"))
    row = next(
        row
        for row in coverage
        if row["heading"]
        == "## Scenario: the fabro_server role deletes an instance's retired sandbox environments"
    )
    assert row["test"] == (
        "tests.consumer.test_fabro_retired_environment_catalog_scenario."
        "test_the_role_reads_all_live_runs_before_retiring_catalog_entries"
    )
