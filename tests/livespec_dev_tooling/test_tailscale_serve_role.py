"""The `tailscale_serve` role publishes declared loopback services and nothing else.

Measured 2026-10-18: gmktec-xubuntu's Fabro server answered on 127.0.0.1:32276 and not
at its tailnet URL, because tailscale-admin documents the mapping only as a command run
by hand, which the fleet host guard refuses to an agent. The role is the committed path.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_ROLE = _ANSIBLE / "roles" / "tailscale_serve"
_TASKS = _ROLE / "tasks" / "main.yml"
_DEFAULTS = _ROLE / "defaults" / "main.yml"
_PLAYBOOK = _ANSIBLE / "fabro-hosts.yml"
_GMKTEC = _ANSIBLE / "inventory" / "host_vars" / "gmktec-xubuntu.yml"
_HP = _ANSIBLE / "inventory" / "host_vars" / "hp-xubuntu.yml"


def test_the_role_declares_no_mapping_by_default() -> None:
    assert "tailscale_serve_mappings: []" in _DEFAULTS.read_text(
        encoding="utf-8"
    ), "an undeclared host must be left exactly as it is, so the default is the empty list"


def test_the_role_only_ever_adds_a_mapping() -> None:
    tasks = _TASKS.read_text(encoding="utf-8")
    assert "- --bg" in tasks, "a published mapping must persist in tailscaled's own state"
    assert "off" not in [
        line.strip().lstrip("- ").strip('"') for line in tasks.splitlines()
    ], "the role must never turn a mapping off; hand-made mappings on hp and vps depend on it"
    assert (
        "('proxy ' ~ item.backend)" in tasks
    ), "a mapping already served to the declared backend must not be re-applied"


def test_the_factory_play_runs_the_role_and_only_gmktec_declares_a_mapping() -> None:
    assert "- role: tailscale_serve" in _PLAYBOOK.read_text(encoding="utf-8")
    gmktec = _GMKTEC.read_text(encoding="utf-8")
    assert "tailscale_serve_mappings:" in gmktec
    assert "https_port: 32276" in gmktec
    assert "backend: http://127.0.0.1:32276" in gmktec
    assert "tailscale_serve_mappings" not in _HP.read_text(
        encoding="utf-8"
    ), "hp-xubuntu's mappings were made by hand and must be left as they are"


def test_vps_retires_its_parked_fabro_fronts_and_the_dev_host_play_applies_the_role() -> None:
    """jxw2ve declared vps like gmktec (F3-F6); gxepwl parks both instances and retires their fronts."""
    playbook = _PLAYBOOK.read_text(encoding="utf-8")
    dev_play = playbook[playbook.index("- name: Fabro services on the dev host") :]
    assert "- role: tailscale_serve" in dev_play, "the dev-host play must apply the role to vps"
    vps = yaml.safe_load((_ANSIBLE / "inventory" / "host_vars" / "vps.yml").read_text("utf-8"))
    mappings = {m["https_port"]: m["backend"] for m in vps["tailscale_serve_mappings"]}
    for port in (32276, 32277):
        assert port not in mappings, f"vps's parked Fabro front {port} must not be published"
        assert port in vps["tailscale_serve_retired_ports"], f"vps must retire {port}"
    assert {i["service_state"] for i in vps["fabro_server_instances"]} == {"stopped"}
    assert vps["fabro_server_manage_settings"] is True
    for instance in vps["fabro_server_instances"]:
        assert instance["otel_dropin"] in {"present", "absent"}, instance["unit_name"]
        assert "GITHUB_APP_PRIVATE_KEY" in [s["name"] for s in instance["vault_secrets"]]
