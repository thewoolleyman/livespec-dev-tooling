"""`node_sysctl` raises every pool node's default socket receive buffer for flannel's netlink watch.

THE DEFECT THIS GUARDS (work-item bd-ib-v7h3az; prior art livespec-n5eudb). k3s
v1.36.2+k3s1 bundles flannel v0.28.4, whose vxlan backend subscribes to link
updates with the plain `netlink.LinkSubscribe` of vishvananda/netlink v1.3.1. That
call never sets `SO_RCVBUF`, so the kernel sizes the socket from
`net.core.rmem_default` (212992 bytes on these hosts). A burst of veth churn
overruns it, the receive fails with ENOBUFS, the update channel closes, and
flannel's single-value receive dereferences a zero `LinkUpdate`: k3s panics and the
cluster API is gone until systemd restarts it. That happened on poweredge-xubuntu on
2026-09-06 at churn-slot 64 and again on 2026-11-02 at churn-slot 32.

WHAT IS ASSERTED. The role installs a `/etc/sysctl.d/` drop-in declaring
`net.core.rmem_default = 4194304`; the role's own controller-side assert accepts
the shipped file (resolved here with the role's own regular expression, so the two
cannot disagree); the post-apply floor verification covers the new key, because it
loops over the same records; and the ci-pool play reaches the role on the k3s
SERVER node as well as on agents, since the server is where the panic takes the API
away. The value is stated, not derived, because the work-item states it.

Neither Ansible nor Jinja is importable in this suite (both resolve through `uvx`
against their own interpreter), so the records are read from the committed YAML
with a pattern that matches the role's two-level `keys:` layout exactly.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_NODE_SYSCTL = _REPO_ROOT / "ansible" / "roles" / "node_sysctl"
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_CI_POOL = _REPO_ROOT / "ansible" / "ci-pool.yml"

_KEY = "net.core.rmem_default"
_VALUE = 4194304
# The kernel default these hosts read before the change, and their rmem_max.
_OLD_DEFAULT = 212992
_HOST_RMEM_MAX = 4194304

_DROPIN_RE = re.compile(
    r"^  - src: (?P<src>\S+)\n    dest: (?P<dest>\S+)\n    keys:\n"
    r"(?P<keys>(?:      - key: \S+\n        value: \d+\n?)+)",
    re.MULTILINE,
)
_KEY_RE = re.compile(r"      - key: (?P<key>\S+)\n        value: (?P<value>\d+)")


def _dropins() -> list[tuple[str, str, dict[str, int]]]:
    text = (_NODE_SYSCTL / "defaults" / "main.yml").read_text(encoding="utf-8")
    records = [
        (
            match["src"],
            match["dest"],
            {key["key"]: int(key["value"]) for key in _KEY_RE.finditer(match["keys"])},
        )
        for match in _DROPIN_RE.finditer(text)
    ]
    assert len(records) >= 3, f"expected the role's drop-in records, parsed {records!r}"
    return records


def _netlink_record() -> tuple[str, str, dict[str, int]]:
    matching = [record for record in _dropins() if _KEY in record[2]]
    assert len(matching) == 1, f"exactly one node_sysctl drop-in must own {_KEY}: {matching!r}"
    return matching[0]


def test_the_role_installs_a_sysctl_drop_in_raising_the_default_receive_buffer() -> None:
    src, dest, keys = _netlink_record()
    assert keys == {_KEY: _VALUE}
    assert dest.startswith("/etc/sysctl.d/") and dest.endswith(".conf")
    assert Path(dest).name == Path(src).name
    assert (_PHASE2 / src).is_file(), f"the shipped drop-in {src} must exist under phase2/"


def test_the_shipped_drop_in_passes_the_roles_own_controller_side_assert() -> None:
    src, _dest, _keys = _netlink_record()
    shipped = (_PHASE2 / src).read_text(encoding="utf-8")
    # The role's first task, verbatim: '^\s*' ~ key|regex_escape ~ '\s*=\s*' ~ value ~ '\s*$'
    pattern = r"^\s*" + re.escape(_KEY) + r"\s*=\s*" + str(_VALUE) + r"\s*$"
    assert re.search(pattern, shipped, re.MULTILINE), shipped
    # Control arm: the same assert REFUSES the old kernel default.
    old = r"^\s*" + re.escape(_KEY) + r"\s*=\s*" + str(_OLD_DEFAULT) + r"\s*$"
    assert not re.search(old, shipped, re.MULTILINE)


def test_the_value_is_far_above_the_old_default_and_within_the_hosts_ceiling() -> None:
    _src, _dest, keys = _netlink_record()
    assert keys[_KEY] >= 16 * _OLD_DEFAULT
    assert keys[_KEY] <= _HOST_RMEM_MAX


def test_the_post_apply_floor_reads_back_every_declared_key_including_this_one() -> None:
    tasks = (_NODE_SYSCTL / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "loop: \"{{ node_sysctl_dropins | subelements('keys') }}\"" in tasks
    assert "ansible.builtin.command: sysctl -n {{ item.1.key }}" in tasks
    handlers = (_NODE_SYSCTL / "handlers" / "main.yml").read_text(encoding="utf-8")
    assert "sysctl -p {{ item.dest }}" in handlers


def test_the_ci_pool_play_reaches_the_role_on_the_server_node_too() -> None:
    play = _CI_POOL.read_text(encoding="utf-8")
    match = re.search(
        r"^    - role: node_sysctl\n(?P<body>(?:      [^\n]*\n)*)", play, re.MULTILINE
    )
    assert match, "ci-pool.yml must include the node_sysctl role"
    assert "when:" not in match["body"], match["body"]
