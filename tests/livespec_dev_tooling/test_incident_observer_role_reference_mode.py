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
