"""The root merge unit runs from a root-owned working directory, never the reference clone.

Work-item livespec-dev-tooling-o6u7jm, repair of the independent re-review. `bd` takes its
tenant and its Dolt host, port and user from the `.beads/config.yaml` of its working directory,
and the root runner's ledger call carries the tenant password. The unit's working directory was
the observer-owned reference clone, so a changed config there would send root's `bd`, with that
password, to another host. The unit now starts in a directory the role installs root-owned,
holding a copy of the repository's committed `.beads/config.yaml`.
"""

from __future__ import annotations

from pathlib import Path

import jinja2
import yaml

__all__: list[str] = []

# This module concerns work item livespec-dev-tooling-o6u7jm, an ordinary pull request.

_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _ROOT / "ansible" / "roles" / "incident_observer"
_WORKDIR = "/declared/merge-workdir"
_REFERENCE = "/var/lib/livespec-incident/reference"
_INSTALL = "Install the incident-merge runner's root-owned working directory and beads config"


def _unit() -> str:
    environment = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True)
    template = environment.from_string(
        (_ROLE / "templates" / "livespec-incident-merge@.service.j2").read_text()
    )
    return template.render(
        ansible_managed="Ansible managed",
        incident_observer_merge_app_path="/etc/livespec-incident/merge-app.json",
        incident_observer_reference_dir=_REFERENCE,
        incident_observer_state_dir="/var/lib/livespec-incident/receipts",
        incident_observer_venv="/opt/livespec-incident/venv",
        incident_observer_merge_authority_script="/declared/reader/incident_authority.py",
        incident_observer_merge_workdir=_WORKDIR,
    )


def _tasks() -> list[dict]:
    return yaml.safe_load((_ROLE / "tasks" / "converge.yml").read_text())


def _config_copy(*, tasks: list[dict]) -> list[dict]:
    return [
        task
        for task in tasks
        if "incident_observer_merge_workdir"
        in str(task.get("ansible.builtin.copy", {}).get("dest"))
        and str(task["ansible.builtin.copy"]["dest"]).endswith("/.beads/config.yaml")
    ]


def test_the_unit_starts_in_the_root_owned_workdir_and_the_role_installs_it_before_the_unit():
    unit_lines = _unit().splitlines()
    tasks = _tasks()
    names = [task.get("name", "") for task in tasks]
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text())
    copies = _config_copy(tasks=tasks)
    facts = [
        f"WorkingDirectory={_WORKDIR}" in unit_lines,
        f"WorkingDirectory={_REFERENCE}" not in unit_lines,
        str(defaults.get("incident_observer_merge_workdir", "")).startswith(
            "/opt/livespec-incident/"
        ),
        len(copies) == 1,
        copies[0]["ansible.builtin.copy"]["owner"] == "root" if copies else False,
        copies[0]["ansible.builtin.copy"]["mode"] == "0644" if copies else False,
        "/.beads/config.yaml" in str(copies[0]["ansible.builtin.copy"]["src"]) if copies else False,
        "role_path" in str(copies[0]["ansible.builtin.copy"]["src"]) if copies else False,
        _INSTALL in names
        and names.index(_INSTALL)
        < names.index("Install the incident-merge runner's templated oneshot unit"),
    ]
    assert all(facts)
