"""The dev-host play disables only proactive memory compaction.

The dev host has ample free memory yet can spend a full core in an episodic
``kcompactd0`` proactive-compaction pass.  The persistent setting belongs to
the dev-host play so a reboot cannot restore the kernel default.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PLAYBOOK = _REPO_ROOT / "ansible" / "dev-host.yml"
_ROLE = _REPO_ROOT / "ansible" / "roles" / "dev_host_compaction"
_DROPIN_NAME = "99-dev-host-compaction.conf"
_DROPIN_PATH = f"/etc/sysctl.d/{_DROPIN_NAME}"


def test_dev_host_play_installs_and_verifies_the_proactive_compaction_setting() -> None:
    """The play owns a persistent zero setting and proves it reached the kernel."""
    play = _PLAYBOOK.read_text(encoding="utf-8")
    task_path = _ROLE / "tasks" / "main.yml"
    dropin_path = _ROLE / "files" / _DROPIN_NAME

    assert "- role: dev_host_compaction" in play
    assert task_path.is_file()
    assert dropin_path.is_file()

    tasks = task_path.read_text(encoding="utf-8")
    dropin = dropin_path.read_text(encoding="utf-8")

    assert f"dest: {_DROPIN_PATH}" in tasks
    assert "sysctl -n vm.compaction_proactiveness" in tasks
    assert "vm.compaction_proactiveness = 0" in dropin
    assert "== '0'" in tasks
