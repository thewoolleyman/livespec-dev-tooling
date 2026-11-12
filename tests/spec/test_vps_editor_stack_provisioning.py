"""The VPS editor stack remains provisioned while its hold is in force.

The former ``vps-info`` installers left the editor stack outside the dev-host
drift report.  This test holds the committed ownership boundary: both service
units and their configuration payloads are supplied by one role, that role is
part of the dev-host play, and one role variable controls whether either unit
may be enabled or started.
"""

from __future__ import annotations

from pathlib import Path

__all__: list[str] = []


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_ROLE_NAME = "vps_editor_stack"
_ROLE = _REPOSITORY_ROOT / "ansible" / "roles" / _ROLE_NAME
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_TASKS = _ROLE / "tasks" / "main.yml"
_PLAY = _REPOSITORY_ROOT / "ansible" / "dev-host.yml"
_ENABLED_VARIABLE = "vps_editor_stack_enabled"
_PAYLOADS = (
    "templates/code-serve-web.service.j2",
    "templates/code-pwa-proxy.service.j2",
    "templates/nginx.conf.j2",
    "files/sw.js",
)


def test_the_dev_host_provisions_the_held_editor_stack_from_one_role() -> None:
    """The role owns both units and payloads while one false default holds them."""
    assert _DEFAULTS.is_file(), "the VPS editor-stack role must declare defaults"
    assert _TASKS.is_file(), "the VPS editor-stack role must converge its payloads"
    assert all(
        (_ROLE / payload).is_file() for payload in _PAYLOADS
    ), "the role must ship both units, nginx configuration, and service-worker payload"

    defaults = _DEFAULTS.read_text(encoding="utf-8")
    tasks = _TASKS.read_text(encoding="utf-8")
    play = _PLAY.read_text(encoding="utf-8")

    assert f"{_ENABLED_VARIABLE}: false" in defaults
    assert f"role: {_ROLE_NAME}" in play
    assert f"tags: [{_ROLE_NAME}]" in play
    assert "code-serve-web.service" in tasks
    assert "code-pwa-proxy.service" in tasks
    assert tasks.count(f"enabled: '{{{{ {_ENABLED_VARIABLE} }}}}'") == 2
    assert tasks.count(f"state: \"{{{{ 'started' if {_ENABLED_VARIABLE} else 'stopped' }}}}\"") == 2
