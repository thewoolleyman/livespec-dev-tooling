"""The `tailscale_serve` role publishes declared loopback services and nothing else.

Measured 2026-10-18: gmktec-xubuntu's Fabro server answered on 127.0.0.1:32276 and not
at its tailnet URL, because tailscale-admin documents the mapping only as a command run
by hand, which the fleet host guard refuses to an agent. The role is the committed path.
"""

from __future__ import annotations

from pathlib import Path

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
