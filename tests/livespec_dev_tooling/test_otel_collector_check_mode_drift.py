"""The collector role reports a rebuilt node's drift under ``--check``.

The runner-pool node telemetry and rebuild-recipe requirements meet at a newly
rebuilt node: its account, download directory, binary, configuration, and unit
are absent, so drift must describe the pending convergence rather than fail
while trying to consume a directory a preceding check-mode task only simulated.
These tests inspect the role structure because the repository test suite does
not run Ansible; the work item's local-playbook proof exercises the runtime.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_BINARY_TASKS = _REPOSITORY_ROOT / "ansible" / "roles" / "otel_collector" / "tasks" / "binary.yml"
_INSTALL_NEEDED = "otel_collector_binary_install_needed"


def _task_blocks(*, body: str) -> list[str]:
    """Return each task's executable lines, excluding explanatory comments."""
    return [
        "\n".join(
            line for line in f"- name: {chunk}".splitlines() if not line.lstrip().startswith("#")
        )
        for chunk in body.split("\n- name: ")[1:]
    ]


def _one_task(*, blocks: list[str], carrying: str) -> str:
    """Return the single task that carries one distinguishing executable line."""
    matching = [block for block in blocks if carrying in block]
    assert len(matching) == 1, f"expected one task carrying {carrying!r}; got {len(matching)}"
    return matching[0]


def test_check_mode_reports_a_missing_binary_without_consuming_simulated_state() -> None:
    """A rebuilt managed-install host reports its account, directory, and binary change."""
    blocks = _task_blocks(body=_BINARY_TASKS.read_text(encoding="utf-8"))
    withheld = [
        block
        for block in blocks
        if any(
            module in block
            for module in (
                "ansible.builtin.get_url:",
                "ansible.builtin.unarchive:",
                'dest: "{{ otel_collector_binary }}"',
            )
        )
    ]
    assert len(withheld) == 3
    for task in withheld:
        assert f"when: {_INSTALL_NEEDED} | bool and not ansible_check_mode" in task

    directory = _one_task(blocks=blocks, carrying="state: directory")
    assert f"when: {_INSTALL_NEEDED} | bool" in directory
    assert "not ansible_check_mode" not in directory

    account = _one_task(blocks=blocks, carrying="ansible.builtin.user:")
    assert "when:" not in account

    report = _one_task(blocks=blocks, carrying="changed_when: true")
    assert "ansible.builtin.debug:" in report
    assert f"when: {_INSTALL_NEEDED} | bool and ansible_check_mode" in report
    assert "{{ otel_collector_binary }}" in report
