"""The incident_observer role leaves a reference clone the loader accepts.

livespec-dev-tooling-w7n3ad. The second real apply (vps, 2026-11-06) refused at
the isolated installation load, for one reason: the reference clone's directory
was mode 0775. The clone is made as the controller account, whose umask is
0002, and `ControllerInstallation.load` refuses a repository whose own
directory is group- or other-writable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-w7n3ad
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "incident_observer"
_CLONE = "Clone the independent reference repository at the released tag"
_MODE = "Keep the reference clone writable by its owner alone"
_LOAD = "Load the whole installation as the controller account before serving it"
_REFERENCE = "{{ incident_observer_reference_dir }}"


def _tasks() -> list[dict[str, Any]]:
    loaded = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    return loaded


def _position(*, tasks: list[dict[str, Any]], name: str) -> int:
    positions = [index for index, task in enumerate(tasks) if task.get("name") == name]
    assert len(positions) == 1, f"exactly one task must be named `{name}`"
    return positions[0]


def test_a_fresh_reference_clone_is_made_without_group_or_other_write() -> None:
    tasks = _tasks()
    clone = tasks[_position(tasks=tasks, name=_CLONE)]

    assert clone["ansible.builtin.git"]["dest"] == _REFERENCE
    assert clone["ansible.builtin.git"]["umask"] == "0022"
    assert clone["become_user"] == "{{ incident_observer_user }}"


def test_an_existing_reference_clone_is_repaired_before_the_installation_loads() -> None:
    tasks = _tasks()
    mode = tasks[_position(tasks=tasks, name=_MODE)]

    assert mode["ansible.builtin.file"] == {
        "path": _REFERENCE,
        "state": "directory",
        "owner": "{{ incident_observer_user }}",
        "group": "{{ incident_observer_group }}",
        "mode": "0750",
    }
    assert int(mode["ansible.builtin.file"]["mode"], 8) & 0o022 == 0
    assert mode["when"] == "incident_observer_account_ready"
    assert _position(tasks=tasks, name=_CLONE) < _position(tasks=tasks, name=_MODE)
    assert _position(tasks=tasks, name=_MODE) < _position(tasks=tasks, name=_LOAD)


# The first `POST /arm` (vps, 2026-11-06 16:27Z) refused `canonical pre-merge
# authority unavailable`: run as the controller account against the reference
# clone, the reader's first `bd show` answered `no beads database found`,
# because the clone carried the committed `.beads/config.yaml` and not the
# gitignored `.beads/metadata.json` pointer `bd` resolves its workspace from.
_CONNECTION = "Read the reference clone's committed tenant connection"
_LEDGER_DIR = "Hold the reference clone's ledger directory to its owner alone"
_POINTER = "Write the reference clone's ledger pointer for the canonical reader"
_POINTER_KEYS = (
    "dolt_mode",
    "dolt_server_host",
    "dolt_server_port",
    "dolt_server_user",
    "dolt_database",
    "project_id",
)


def test_the_reference_clone_gets_a_ledger_pointer_before_the_installation_loads() -> None:
    tasks = _tasks()
    connection = tasks[_position(tasks=tasks, name=_CONNECTION)]
    ledger_dir = tasks[_position(tasks=tasks, name=_LEDGER_DIR)]
    pointer = tasks[_position(tasks=tasks, name=_POINTER)]

    assert connection["ansible.builtin.slurp"]["src"] == f"{_REFERENCE}/.beads/config.yaml"
    assert connection["register"] == "incident_observer_beads_config"
    assert ledger_dir["ansible.builtin.file"] == {
        "path": f"{_REFERENCE}/.beads",
        "state": "directory",
        "owner": "{{ incident_observer_user }}",
        "group": "{{ incident_observer_group }}",
        "mode": "0700",
    }
    copy = pointer["ansible.builtin.copy"]
    assert copy["dest"] == f"{_REFERENCE}/.beads/metadata.json"
    assert (copy["owner"], copy["group"], copy["mode"]) == (
        "{{ incident_observer_user }}",
        "{{ incident_observer_group }}",
        "0600",
    )
    # One expression renders the whole pointer, so the port stays a JSON
    # integer: `bd` dials port 0 without `dolt_server_port`, and a per-key
    # `vars:` template would have written it as a string.
    content = copy["content"]
    assert content.count("{{") == 1
    assert "to_nice_json" in content
    assert all(f"'{key}'" in content for key in _POINTER_KEYS)
    assert "'dolt.server-port'] | int" in content
    for task in (connection, ledger_dir, pointer):
        assert task["when"] == "incident_observer_account_ready"
    assert (
        _position(tasks=tasks, name=_MODE)
        < _position(tasks=tasks, name=_CONNECTION)
        < _position(tasks=tasks, name=_LEDGER_DIR)
        < _position(tasks=tasks, name=_POINTER)
        < _position(tasks=tasks, name=_LOAD)
    )


def test_the_pointer_project_id_is_declared_as_a_default() -> None:
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))

    assert isinstance(defaults, dict)
    assert defaults["incident_observer_tenant_project_id"] == "c8dcb5d9-1d1c-47d9-a1e5-f856e60b9544"
