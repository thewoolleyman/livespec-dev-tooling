"""The Samba source's server string and share comment name this machine, rendered.

A machine is bound ONLY through the inventory's host groups and host variables
(livespec-dev-tooling-prdxxe). `arq_smb_source`'s `smb.conf.j2` carried `vps` as
a literal in two places an SMB client reads back: the global `server string` and
the share's `comment`. Both are rendered from `inventory_hostname` instead, so
the one converged host keeps the exact text it serves today and a second host
identifies itself rather than claiming to be the first.

THESE TWO ARE DIFFERENT FROM THE REST OF THE FILE, which is why they are the ones
named. `interfaces`, `hosts allow` and the tailnet address are already variables;
the share NAME (`vps-root`) and the file and unit names keep their `vps-` prefix,
because those are the paths the vps-info installers created and are references to
a path rather than to a machine — the distinction prdxxe drew. A `server string`
is neither: it is this machine describing itself to a client.

Work-item: livespec-dev-tooling-mavj5i. Plan: livespec-orchestrator-beads-fabro
`petri-factory-on-gmktec`.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SMB_CONF = _REPO_ROOT / "ansible" / "roles" / "arq_smb_source" / "templates" / "smb.conf.j2"
_HOST_VARS = _REPO_ROOT / "ansible" / "inventory" / "host_vars"

# The two settings, with the prose each keeps around the rendered name. Spelled
# whole rather than as a placeholder match, because what must not change is the
# TEXT the live host serves: an SMB client reads the server string back, and a
# reworded one is a visible change on a host this slice promised not to touch.
_SERVER_STRING = "   server string = {{ inventory_hostname }} Arq backup source"
_SHARE_COMMENT = "   comment = {{ inventory_hostname }} root-state snapshot for Arq backup"


def _inventory_hosts() -> frozenset[str]:
    """Every machine the fleet inventory binds, read from its own `host_vars` stems."""
    stems = frozenset(path.stem for path in _HOST_VARS.glob("*.yml"))
    assert stems, "ansible/inventory/host_vars must bind at least one machine"
    return stems


def _smb_conf() -> str:
    assert _SMB_CONF.is_file(), "the arq_smb_source role must ship its smb.conf template"
    return _SMB_CONF.read_text(encoding="utf-8")


def test_the_server_string_is_rendered_from_this_machines_inventory_name() -> None:
    """What an SMB client sees when it asks the server who it is."""
    assert _SERVER_STRING in _smb_conf().splitlines()


def test_the_share_comment_is_rendered_from_this_machines_inventory_name() -> None:
    """The second place the name was literal, and the one easiest to leave behind.

    Asserted separately from the server string because the two sit 26 lines apart
    in different sections, which is exactly how one of a pair gets fixed alone.
    """
    assert _SHARE_COMMENT in _smb_conf().splitlines()


def test_no_value_line_of_the_samba_template_names_a_machine() -> None:
    """Comments stay — they are provenance — and no rendered value names a machine.

    Line 3's header comment records what the file IS and is skipped for that
    reason; `#` and `;` comment lines in a rendered ini are the same provenance
    the maintainer ruled stays.
    """
    hosts = _inventory_hosts()
    hits = [
        f"{number}:{host}"
        for number, raw in enumerate(_smb_conf().splitlines(), start=1)
        if not raw.lstrip().startswith(("#", ";"))
        for host in sorted(hosts)
        if re.search(rf"(?<![\w.-]){re.escape(host)}(?![\w-])", raw)
    ]

    assert hits == []
