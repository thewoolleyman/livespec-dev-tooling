"""The VPS collector must be installed from committed source, not its checkout."""

from __future__ import annotations

from pathlib import Path

_REPOSITORY_ROOT = Path(__file__).parents[2]
_ROLE_TASKS = _REPOSITORY_ROOT / "ansible/roles/otel_collector/tasks/main.yml"
_ROLE_DEFAULTS = _REPOSITORY_ROOT / "ansible/roles/otel_collector/defaults/main.yml"
_ANSIBLE_README = _REPOSITORY_ROOT / "ansible/README.md"


def test_role_compares_the_merged_collector_config_into_etc_in_check_mode() -> None:
    """A controller-side lookup lets check mode report the real config drift."""
    assert _ROLE_TASKS.is_file()

    tasks = _ROLE_TASKS.read_text(encoding="utf-8")

    assert "ansible.builtin.copy" in tasks
    assert "lookup('ansible.builtin.url', otel_collector_config_url" in tasks
    assert "ansible.builtin.get_url" not in tasks
    assert 'dest: "{{ otel_collector_config_path }}"' in tasks
    assert "/data/projects/otel-collector" not in tasks


def test_role_manages_every_collector_exporter_environment_value() -> None:
    """The systemd EnvironmentFile includes the collector's endpoint override."""
    defaults = _ROLE_DEFAULTS.read_text(encoding="utf-8")

    assert "HONEYCOMB_API_ENDPOINT" in defaults


def test_ansible_readme_names_the_vps_collector_drift_and_apply_path() -> None:
    """Operators need the committed role's exact control-node invocation."""
    readme = _ANSIBLE_README.read_text(encoding="utf-8")

    assert "otel_collector" in readme
    assert "just ansible-drift ansible/dev-host.yml --tags otel_collector" in readme
    assert "just ansible-apply ansible/dev-host.yml --tags otel_collector" in readme
    assert "HONEYCOMB_API_ENDPOINT" in readme
