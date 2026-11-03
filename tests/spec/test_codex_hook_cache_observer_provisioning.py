"""The dev host provisions the Driver hook-cache observer under systemd.

The Driver owns the observer and ships its user-unit definition.  This test
guards the separate host-provisioning responsibility: copy that released
definition into the Codex operator's user-unit directory, enable lingering,
and start the unit through the user manager.  A hand-installed unit would not
appear in Ansible's drift report and would disappear when the user manager
stops at logout.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []


_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _ROOT / "ansible" / "roles" / "codex_config"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_UNIT = "livespec-codex-hook-cache-observer.service"
_DRIVER_UNIT = "{{ ansible_env.HOME }}/.local/share/livespec-driver-codex/dev-tooling/" f"{_UNIT}"
_INSTALLED_UNIT = "{{ ansible_env.HOME }}/.config/systemd/user/" + _UNIT


def test_codex_config_provisions_a_lingering_user_observer_from_the_driver_release() -> None:
    """A reboot starts the observer without a Codex or Claude login session."""
    defaults = _DEFAULTS.read_text(encoding="utf-8")
    tasks = _TASKS.read_text(encoding="utf-8")

    assert _DRIVER_UNIT in defaults, (
        "the source must be the Driver's released service definition, not a "
        "second locally-maintained unit"
    )
    assert _INSTALLED_UNIT in defaults, (
        "the systemd user manager only discovers a provisioned user unit in "
        "the operator's user-unit directory"
    )
    assert "remote_src: true" in tasks and "codex_config_observer_unit_source" in tasks, (
        "the role must copy the released Driver unit rather than duplicate its " "ExecStart command"
    )
    assert 'argv: [loginctl, enable-linger, "{{ codex_config_user }}"]' in tasks, (
        "lingering must be enabled for the Codex operator, otherwise a reboot "
        "leaves no user manager to start the observer"
    )
    assert (
        "scope: user" in tasks and "daemon_reload: true" in tasks
    ), "the copied unit must be reloaded through the operator's user manager"
    assert (
        "enabled: true" in tasks and "state: started" in tasks
    ), "the observer must be both enabled for reboot and started on the first apply"
    assert "systemctl, --user, is-active" in tasks, (
        "the converge must verify the installed observer is active rather than "
        "trusting a successful start request"
    )
