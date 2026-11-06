"""A first apply of the incident_observer role starts a unit it has verified.

livespec-dev-tooling-w7n3ad. The first real apply (vps, 2026-11-06) left a unit
restarting in a loop, for two reasons these tests hold shut:

- the released distribution's vendored `returns` imports `typing_extensions`,
  the release is installed with `--no-deps`, and nothing installed that module;
- the role decides "is it installed" BEFORE it installs, so on a first apply it
  skipped rendering the manifest, loading the installation and every check
  between the install and the unit's start.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-w7n3ad
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "incident_observer"
_REFRESH = "Name the installation and the account this apply has just created"
_INSTALL = "Install the released distribution from its tag, never from a checkout"
_TYPING = "Install typing-extensions beside the release"
_RENDER = "Render the released-installation manifest with the serving interpreter"
_LOAD = "Load the whole installation as the controller account before serving it"
_IMPORT = "Import the service module as the controller account before serving it"
_UNIT = "Install the observer's unit"


def _tasks() -> list[dict[str, Any]]:
    loaded = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    return loaded


def _position(*, tasks: list[dict[str, Any]], name: str) -> int:
    positions = [index for index, task in enumerate(tasks) if task.get("name") == name]
    assert len(positions) == 1, f"exactly one task must be named `{name}`"
    return positions[0]


def test_the_release_gets_the_one_module_its_vendored_runtime_imports() -> None:
    tasks = _tasks()
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    requirement = defaults["incident_observer_typing_extensions_requirement"]
    assert requirement.startswith("typing-extensions==")

    install = tasks[_position(tasks=tasks, name=_TYPING)]
    argv = install["ansible.builtin.command"]["argv"]
    assert "{{ incident_observer_typing_extensions_requirement }}" in argv
    assert "--no-deps" in argv
    assert "-I" in argv
    assert _position(tasks=tasks, name=_INSTALL) < _position(tasks=tasks, name=_TYPING)
    assert _position(tasks=tasks, name=_TYPING) < _position(tasks=tasks, name=_UNIT)


def test_a_first_apply_re_reads_what_it_installed_before_it_verifies() -> None:
    tasks = _tasks()
    refresh = tasks[_position(tasks=tasks, name=_REFRESH)]

    assert refresh["ansible.builtin.set_fact"] == {
        "incident_observer_installed": True,
        "incident_observer_account_ready": True,
    }
    assert refresh["when"] == "not ansible_check_mode", "a dry run creates nothing"
    assert _position(tasks=tasks, name=_INSTALL) < _position(tasks=tasks, name=_REFRESH)
    for verified in (_RENDER, _LOAD, _IMPORT):
        assert _position(tasks=tasks, name=_REFRESH) < _position(tasks=tasks, name=verified)


def test_the_unit_starts_only_after_the_service_module_imports() -> None:
    tasks = _tasks()
    imported = tasks[_position(tasks=tasks, name=_IMPORT)]

    argv = imported["ansible.builtin.command"]["argv"]
    assert argv[-1] == "import livespec_dev_tooling.incident_observer_service"
    assert "-I" in argv
    assert imported["become_user"] == "{{ incident_observer_user }}"
    assert imported["changed_when"] is False
    assert _position(tasks=tasks, name=_LOAD) < _position(tasks=tasks, name=_IMPORT)
    assert _position(tasks=tasks, name=_IMPORT) < _position(tasks=tasks, name=_UNIT)
