"""The `vxlan_tunnel_tso` role turns tso off on flannel.1 only where the NIC is affected.

poweredge-xubuntu's bnx2x NIC emits malformed frames when it segments
VXLAN-encapsulated TCP in hardware (plan homelab-k8s-worker-nodes, epic
livespec-dev-tooling-ko26ez). The role's contract, asserted here on its committed
text: it gates on the NIC DRIVER rather than a hostname, it persists through a
udev rule because flannel recreates the interface at every k3s start, it never
changes a physical NIC feature (that reloads a bnx2x port), and `ci-pool.yml`
reaches it ungated.
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE = _REPO_ROOT / "ansible" / "roles" / "vxlan_tunnel_tso"
_TASKS = (_ROLE / "tasks" / "main.yml").read_text(encoding="utf-8")
_DEFAULTS = (_ROLE / "defaults" / "main.yml").read_text(encoding="utf-8")
_PLAY = (_REPO_ROOT / "ansible" / "ci-pool.yml").read_text(encoding="utf-8")


def test_the_role_gates_on_the_nic_driver_and_names_bnx2x() -> None:
    assert re.search(r"^vxlan_tunnel_tso_affected_drivers:\n  - bnx2x$", _DEFAULTS, re.MULTILINE)
    assert "in vxlan_tunnel_tso_affected_drivers" in _TASKS
    assert "inventory_hostname" not in _TASKS


def test_the_udev_rule_reapplies_tso_off_when_the_interface_is_added() -> None:
    assert '{{ vxlan_tunnel_tso_udev_match }}, RUN+="{{ vxlan_tunnel_tso_udev_run }}"' in _TASKS
    assert (
        'vxlan_tunnel_tso_udev_match: \'ACTION=="add", SUBSYSTEM=="net", '
        'KERNEL=="{{ vxlan_tunnel_tso_interface }}"\'' in _DEFAULTS
    )
    assert (
        'vxlan_tunnel_tso_udev_run: "{{ vxlan_tunnel_tso_ethtool }} -K '
        '{{ vxlan_tunnel_tso_interface }} tso off"' in _DEFAULTS
    )
    assert re.search(r"^vxlan_tunnel_tso_interface: flannel\.1$", _DEFAULTS, re.MULTILINE)


def test_the_role_never_changes_a_physical_nic_feature() -> None:
    # Every `-K` (set) call names the VXLAN interface variable, never a fact-derived NIC.
    for match in re.finditer(r"- -K\n\s+- \"(?P<target>[^\"]+)\"", _TASKS):
        assert match.group("target") == "{{ vxlan_tunnel_tso_interface }}"
    assert "tx-udp_tnl-segmentation off" not in _TASKS


def test_the_drift_report_shows_a_pending_change() -> None:
    probe = _TASKS.split("- name: Probe the live tso state of the VXLAN interface")[1]
    probe = probe.split("\n- name:")[0]
    assert "check_mode: false" in probe
    assert "ansible_check_mode" in probe


def test_ci_pool_reaches_the_role_ungated() -> None:
    entry = re.search(
        r"^    - role: vxlan_tunnel_tso\n      tags: \[vxlan_tunnel_tso\]\n(?P<next>.*)$",
        _PLAY,
        re.MULTILINE,
    )
    assert entry is not None
    assert not entry.group("next").startswith("      when:")
