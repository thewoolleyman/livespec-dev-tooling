"""Consumer-tier proof for the worker queue reconciler's committed off-switch.

The `worker_queue_reconciler` role (livespec-dev-tooling-u45iv6) arms a 30-second
timer on the k3s server. Its independent second look found no committed way
back: a revert plus re-apply would have left the timer running. The role now has
a `worker_queue_reconciler_state` switch whose `absent` value is that way back.
These tests read the committed role, because the live apply is a host action.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_ROLE = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "worker_queue_reconciler"


def _blocks() -> dict[str, list[dict[str, object]]]:
    tasks = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    return {
        str(task["when"]): task["block"] for task in tasks if "block" in task and "when" in task
    }


def test_the_role_installs_by_default_and_only_two_states_are_accepted() -> None:
    defaults = yaml.safe_load((_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["worker_queue_reconciler_state"] == "present"
    tasks = yaml.safe_load((_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8"))
    guard = tasks[0]["ansible.builtin.assert"]["that"]
    assert guard == "worker_queue_reconciler_state in ['present', 'absent']"


def test_present_installs_and_arms_the_timer_and_absent_is_a_separate_block() -> None:
    blocks = _blocks()
    assert set(blocks) == {
        "worker_queue_reconciler_state == 'present'",
        "worker_queue_reconciler_state == 'absent'",
    }
    present = yaml.safe_dump(blocks["worker_queue_reconciler_state == 'present'"])
    assert "enabled: true" in present
    assert "state: started" in present


def test_absent_stops_and_disables_both_units_removes_them_and_reloads_systemd() -> None:
    absent = _blocks()["worker_queue_reconciler_state == 'absent'"]
    stop = absent[0]["ansible.builtin.systemd_service"]
    assert stop["enabled"] is False
    assert stop["state"] == "stopped"
    assert absent[0]["loop"] == [
        "{{ worker_queue_reconciler_timer }}",
        "{{ worker_queue_reconciler_service }}",
    ]
    remove = absent[1]
    assert remove["ansible.builtin.file"]["state"] == "absent"
    assert remove["notify"] == "Reload systemd for the worker queue reconciler"
    assert absent[2]["ansible.builtin.meta"] == "flush_handlers"


def test_absent_touches_nothing_but_the_two_units() -> None:
    text = yaml.safe_dump(_blocks()["worker_queue_reconciler_state == 'absent'"])
    assert "kubectl" not in text
    assert "converge-worker-queues" not in text
    assert "worker-lane-readiness" not in text
