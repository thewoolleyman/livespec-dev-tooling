"""The VPS collector must be installed from committed source, not its checkout."""

from __future__ import annotations

from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).parents[2]
_ROLE_TASKS = _REPOSITORY_ROOT / "ansible/roles/otel_collector/tasks/main.yml"


def test_role_downloads_the_merged_collector_config_into_etc() -> None:
    """A committed converge copies the source config, never a VPS checkout path."""
    assert _ROLE_TASKS.is_file()

    tasks = _ROLE_TASKS.read_text(encoding="utf-8")

    assert "ansible.builtin.get_url" in tasks
    assert "raw.githubusercontent.com/thewoolleyman/otel-collector/main/config.yaml" in tasks
    assert 'dest: "{{ otel_collector_config_path }}"' in tasks
    assert "/data/projects/otel-collector" not in tasks
