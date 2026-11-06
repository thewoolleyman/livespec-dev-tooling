"""The incident_observer role never claims a callback path it did not publish.

livespec-dev-tooling-w7n3ad. On vps (2026-11-06) the role's funnel publish
reported a change on two applies in a row while the node's funnel status never
carried the path: the tailnet policy does not grant the node the `funnel`
attribute, and `tailscale funnel --bg --yes` exits 0 there having published
nothing. A second apply therefore never reported "no change", and the run
output said the path was being published when it was not.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-w7n3ad
_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "incident_observer"
_GRANT_READ = "Read whether the tailnet grants this node the funnel attribute"
_GRANT_FACT = "Name the funnel grant and the callback path's current disposition"
_SAY = "Name the public callback path's disposition in the run output"
_PUBLISH = "Publish only the callback path through a path-scoped funnel"
_READ_BACK = "Read the funnel configuration back after publishing"
_REFUSE = "Refuse a publish that left the callback path unpublished"
_PUBLISHED = "incident_observer_funnel_publish is changed and not ansible_check_mode"


def _tasks() -> list[dict[str, Any]]:
    loaded = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    assert isinstance(loaded, list)
    return loaded


def _position(*, tasks: list[dict[str, Any]], name: str) -> int:
    positions = [index for index, task in enumerate(tasks) if task.get("name") == name]
    assert len(positions) == 1, f"exactly one task must be named `{name}`"
    return positions[0]


def test_the_grant_is_read_from_the_nodes_own_capability_map_before_publishing() -> None:
    tasks = _tasks()
    read = tasks[_position(tasks=tasks, name=_GRANT_READ)]
    fact = tasks[_position(tasks=tasks, name=_GRANT_FACT)]

    assert read["ansible.builtin.command"]["argv"] == [
        "tailscale",
        "status",
        "--json",
        "--peers=false",
    ]
    assert read["changed_when"] is False
    assert read["check_mode"] is False
    granted = fact["ansible.builtin.set_fact"]["incident_observer_funnel_granted"]
    assert "'funnel' in" in granted
    assert "Self.CapMap" in granted
    assert _position(tasks=tasks, name=_GRANT_READ) < _position(tasks=tasks, name=_GRANT_FACT)
    assert _position(tasks=tasks, name=_GRANT_FACT) < _position(tasks=tasks, name=_PUBLISH)


def test_an_ungranted_node_publishes_nothing_and_the_run_output_names_whose_step_it_is() -> None:
    tasks = _tasks()
    publish = tasks[_position(tasks=tasks, name=_PUBLISH)]
    say = tasks[_position(tasks=tasks, name=_SAY)]

    assert publish["when"] == (
        "incident_observer_funnel_granted and not incident_observer_funnel_served"
    )
    notice = say["vars"]["incident_observer_funnel_ungranted_notice"]
    assert "incident_observer_funnel_ungranted_notice" in say["ansible.builtin.debug"]["msg"]
    assert "cannot be published" in notice
    assert "tailnet-admin step" in notice
    assert _position(tasks=tasks, name=_SAY) < _position(tasks=tasks, name=_PUBLISH)


def test_a_publish_is_believed_only_after_the_funnel_status_carries_the_path() -> None:
    tasks = _tasks()
    read_back = tasks[_position(tasks=tasks, name=_READ_BACK)]
    refuse = tasks[_position(tasks=tasks, name=_REFUSE)]

    assert read_back["ansible.builtin.command"]["argv"] == ["tailscale", "funnel", "status"]
    assert read_back["changed_when"] is False
    assert read_back["when"] == _PUBLISHED
    assert refuse["when"] == _PUBLISHED
    conditions = refuse["ansible.builtin.assert"]["that"]
    assert all("incident_observer_funnel_after.stdout" in condition for condition in conditions)
    assert any("(Funnel on)" in condition for condition in conditions)
    assert any("incident_observer_funnel_path" in condition for condition in conditions)
    assert _position(tasks=tasks, name=_PUBLISH) < _position(tasks=tasks, name=_READ_BACK)
    assert _position(tasks=tasks, name=_READ_BACK) < _position(tasks=tasks, name=_REFUSE)
