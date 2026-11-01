"""The btop-loop role is bound by inventory, not by a role default.

The role ships a tool that the other legacy-host provisioners also ship.  A
kernel-hostname default in this role therefore turned a role-level setting into
a binding for one particular machine.  The inventory owns that binding: this
role requires the host variable before its first host-changing task, and its
operator guidance names provisioner locations without naming a machine.

Work-item: livespec-dev-tooling-tqaoio.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "btop_loop"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_EXPECTED_HOSTNAME = "btop_loop_expected_hostname"


def _task_block(*, task_name: str) -> str:
    """Return one named task's YAML, without accidentally reading its neighbour."""
    tasks = _TASKS.read_text(encoding="utf-8")
    marker = f"- name: {task_name}\n"
    assert marker in tasks, f"btop_loop must declare the {task_name!r} task"
    return tasks.split(marker, 1)[1].split("\n- name: ", 1)[0]


def test_the_expected_hostname_has_no_role_default() -> None:
    """Only inventory host variables may bind btop_loop to a kernel hostname."""
    defaults = _DEFAULTS.read_text(encoding="utf-8")

    assert f"{_EXPECTED_HOSTNAME}:" not in defaults


def test_a_missing_inventory_hostname_fails_before_the_role_changes_a_host() -> None:
    """The first role task refuses an omitted host variable by its exact name."""
    required = _task_block(task_name="Assert the inventory declares btop_loop_expected_hostname")
    tasks = _TASKS.read_text(encoding="utf-8")

    assert f"{_EXPECTED_HOSTNAME} is defined" in required
    assert _EXPECTED_HOSTNAME in required
    assert tasks.index(required) < tasks.index("- name: Find btop on the target's PATH")


def test_service_location_guidance_names_no_machine_hostname() -> None:
    """A failure explains provisioning ownership without binding another host."""
    host_assertion = _task_block(
        task_name="Assert this host is the one btop-loop is provisioned for"
    )

    assert "served by their provisioners' host-tool trees" in host_assertion
    for hostname in ("hp-xubuntu", "poweredge-xubuntu", "gmktec-xubuntu"):
        assert hostname not in host_assertion
