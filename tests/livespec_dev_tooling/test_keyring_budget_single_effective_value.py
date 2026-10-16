"""One effective `kernel.keys.*` budget on a host that is in BOTH `ci_pool` and `sandbox_hosts`.

THE DEFECT THIS FILE FENCES (work-item livespec-dev-tooling-5lqito). `hp-xubuntu`
joined `ci_pool` on 2026-10-14 (livespec-dev-tooling-7we6po) while staying in
`sandbox_hosts`, which it never leaves — so TWO roles now install the same two
kernel tunables on it. `node_sysctl`, reached by `ansible/ci-pool.yml`, ships
`/etc/sysctl.d/60-k3s-container-keyring.conf`; `keyring_quota`, reached by
`ansible/fabro-hosts.yml`, ships `/etc/sysctl.d/99-keyring-quota.conf`.

WHEN THE TWO DROP-INS DECLARE DIFFERENT NUMBERS THE HOST HAS NO SINGLE STATE,
and both halves of the disagreement are live at once. At boot, and under
`sysctl --system`, systemd-sysctl reads `/etc/sysctl.d/*.conf` in LEXICOGRAPHIC
order, so the last-sorting file wins. But each role's own apply step loads ONLY
ITS OWN file — `node_sysctl`'s handler runs `sysctl -p <its dest>` and
`keyring_quota` runs `sysctl --load <its dest>` — so between boots the live
value is whichever play ran LAST, and whichever role did not run last then
refuses its own post-apply check. That is what failed on 2026-10-16:
`kernel.keys.maxbytes is 1048576 after apply, expected 200000`, task 24 of
`just ansible-apply ansible/ci-pool.yml -l hp-xubuntu`.

AGREEMENT IS WHAT MAKES "THE EFFECTIVE VALUE" A SINGLE NUMBER AT ALL, which is
why this file asserts it rather than asserting a precedence rule. A precedence
rule would have to hold for the drop-in ORDER and for the apply ORDER, and the
second one is not an order at all — it is whichever operator ran whichever play
most recently. Two roles installing the same number have no order to get wrong.
The second half is the sizing: that one number has to be at least what each role
requires on its own — the k3s container keyring budget a kubelet's containers
need, and the per-caller 1Password cache entries `with-livespec-env.sh` holds.

The companion assertion — that `node_sysctl`'s post-apply check reads its budget
as a FLOOR rather than an equality, so a co-owner raising the ceiling further
does not fail the apply — lives in
`test_node_sysctl_post_apply_keyring_floor.py`. Neither suffices alone:
agreement without the floor leaves the role refusing any future co-owner, and
the floor without agreement lets a `sysctl -p` of one file silently LOWER the
host below what the wrapper cache needs while the role reports success.

WHY A RESOLVER AND NOT AN `ansible-playbook` RUN — the same reason
`test_ci_pool_factory_only_agent_roles.py` gives: `ci-pool.yml` reaches a real
cluster, and neither Ansible nor Jinja is importable in this suite (both are
resolved through `uvx` against their own interpreter). What CAN be resolved
off-host is what is in question here — the numbers the committed drop-ins
declare, the budgets the committed defaults require, and which hosts the two
plays converge each role on.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"
_NODE_SYSCTL = _ANSIBLE / "roles" / "node_sysctl"
_KEYRING_QUOTA = _ANSIBLE / "roles" / "keyring_quota"
# Every play that converges a keyring drop-in onto a legacy machine. Read as a
# pair because the conflict is BETWEEN them: one play's roles are invisible to
# the other, and the host they overlap on is the only place that shows.
_PLAYS = (_ANSIBLE / "ci-pool.yml", _ANSIBLE / "fabro-hosts.yml")

_NODE_SYSCTL_ROLE = "node_sysctl"
_KEYRING_QUOTA_ROLE = "keyring_quota"
# The two tunables both roles own, named because the Definition of Done names
# them. A key one role owns and the other does not is a new conflict, and
# `test_each_role_installs_exactly_the_budget_its_own_defaults_require` fails on
# it rather than resolving a set this file never checked.
_CONTESTED_KEYS = ("kernel.keys.maxbytes", "kernel.keys.maxkeys")

_PHASE2_DIR_RE = re.compile(
    r'^node_sysctl_phase2_dir: "\{\{ role_path \}\}/(?P<relative>[^"]+)"$', re.MULTILINE
)
_DROPIN_RE = re.compile(
    r"^  - src: (?P<src>\S+)\n    dest: (?P<dest>\S+)\n    keys:\n"
    r"(?P<keys>(?:      - key: \S+\n        value: \d+\n)+)",
    re.MULTILINE,
)
_DROPIN_KEY_RE = re.compile(
    r"^      - key: (?P<key>\S+)\n        value: (?P<value>\d+)$", re.MULTILINE
)
_QUOTA_SCALAR_RE = re.compile(r"^keyring_quota_(?P<name>\w+): (?P<value>\S+)$", re.MULTILINE)
_SYSCTL_LINE_RE = re.compile(r"^(?P<key>kernel\.keys\.\w+) = (?P<value>\d+)$", re.MULTILINE)
_PLAY_RE = re.compile(
    r"^- name: [^\n]+\n  hosts: (?P<group>\w+)\n(?P<body>(?:(?:  [^\n]*)?\n)*)", re.MULTILINE
)
_PLAY_ROLE_RE = re.compile(r"^    - role: (?P<role>\w+)$", re.MULTILINE)
_GROUP_RE = re.compile(
    r"^        (?P<group>\w+):\n          hosts:\n(?P<body>(?:(?:            [^\n]*)?\n)*)",
    re.MULTILINE,
)
_GROUP_HOST_RE = re.compile(r"^            (?P<host>[\w-]+):$", re.MULTILINE)


# --- reading the committed inventory and plays ------------------------------


def _group_hosts() -> dict[str, frozenset[str]]:
    """Every inventory group and the hosts it holds."""
    groups = {
        match["group"]: frozenset(host["host"] for host in _GROUP_HOST_RE.finditer(match["body"]))
        for match in _GROUP_RE.finditer(_INVENTORY.read_text(encoding="utf-8"))
    }
    assert {"ci_pool", "sandbox_hosts"} <= set(groups), (
        f"{_INVENTORY.name} must declare both `ci_pool` and `sandbox_hosts`: the conflict this "
        f"file fences exists only on a host that is in both, and a reader that cannot find the "
        f"groups would report agreement it never checked; got {sorted(groups)}"
    )
    return groups


def _roles_by_group() -> dict[str, frozenset[str]]:
    """Every target group of the two plays, and the roles that play converges on it."""
    found: dict[str, frozenset[str]] = {}
    for play in _PLAYS:
        for match in _PLAY_RE.finditer(play.read_text(encoding="utf-8")):
            found[match["group"]] = found.get(match["group"], frozenset()) | frozenset(
                entry["role"] for entry in _PLAY_ROLE_RE.finditer(match["body"])
            )
    assert found, (
        f"{', '.join(play.name for play in _PLAYS)} must declare their roles as "
        f"`    - role: <name>` entries under a `  hosts: <group>` play; a role this reader "
        f"cannot see is a converge it cannot compare"
    )
    return found


def _hosts_reached_by(*, role: str) -> frozenset[str]:
    """Every host the two plays converge `role` on."""
    serving = {group for group, roles in _roles_by_group().items() if role in roles}
    hosts = _group_hosts()
    return frozenset(host for group in serving for host in hosts[group])


# --- reading each role's installed drop-in and its own requirement ----------


def _declared_in(*, conf: Path) -> dict[str, int]:
    """Every `kernel.keys.*` assignment a shipped drop-in makes."""
    return {
        match["key"]: int(match["value"])
        for match in _SYSCTL_LINE_RE.finditer(conf.read_text(encoding="utf-8"))
    }


def _node_sysctl_record() -> tuple[str, Path, dict[str, int]]:
    """node_sysctl's keyring drop-in: its dest, its shipped file, and the budget it asserts."""
    text = (_NODE_SYSCTL / "defaults" / "main.yml").read_text(encoding="utf-8")
    phase2 = _PHASE2_DIR_RE.search(text)
    assert phase2 is not None, (
        f"{_NODE_SYSCTL.name}/defaults/main.yml must declare `node_sysctl_phase2_dir` relative "
        f"to `role_path`: it is where the shipped drop-ins live, and a reader that cannot "
        f"resolve it cannot read the numbers the role installs"
    )
    records = [
        (
            match["dest"],
            match["src"],
            {key["key"]: int(key["value"]) for key in _DROPIN_KEY_RE.finditer(match["keys"])},
        )
        for match in _DROPIN_RE.finditer(text)
    ]
    keyring = [record for record in records if set(record[2]) & set(_CONTESTED_KEYS)]
    assert len(keyring) == 1, (
        f"exactly one of node_sysctl's drop-ins must own {list(_CONTESTED_KEYS)}; got "
        f"{[record[0] for record in keyring]}. Two drop-ins of the SAME role declaring one key "
        f"is the identical defect this file fences, one scope in"
    )
    dest, src, budget = keyring[0]
    return dest, (_NODE_SYSCTL / phase2["relative"] / src).resolve(), budget


def _keyring_quota_record() -> tuple[str, Path, dict[str, int]]:
    """keyring_quota's drop-in: its dest, its shipped file, and the ceilings it asserts."""
    text = (_KEYRING_QUOTA / "defaults" / "main.yml").read_text(encoding="utf-8")
    scalars = {match["name"]: match["value"] for match in _QUOTA_SCALAR_RE.finditer(text)}
    assert {"sysctl_dir", "conf_name", "maxbytes", "maxkeys"} <= set(scalars), (
        f"{_KEYRING_QUOTA.name}/defaults/main.yml must declare `keyring_quota_sysctl_dir`, "
        f"`keyring_quota_conf_name`, `keyring_quota_maxbytes` and `keyring_quota_maxkeys` — "
        f"the role's dest and the ceilings it asserts; got {sorted(scalars)}"
    )
    budget = {f"kernel.keys.{name}": int(scalars[name]) for name in ("maxbytes", "maxkeys")}
    return (
        f"{scalars['sysctl_dir']}/{scalars['conf_name']}",
        _KEYRING_QUOTA / "files" / scalars["conf_name"],
        budget,
    )


def _records() -> dict[str, tuple[str, Path, dict[str, int]]]:
    """Both roles' drop-in records, keyed by role."""
    return {
        _NODE_SYSCTL_ROLE: _node_sysctl_record(),
        _KEYRING_QUOTA_ROLE: _keyring_quota_record(),
    }


def _effective(*, installed: dict[str, dict[str, int]], key: str) -> int:
    """`key`'s value after systemd-sysctl has read every drop-in in `installed`.

    `/etc/sysctl.d/*.conf` is read in LEXICOGRAPHIC order and the last writer
    wins. Every drop-in reaching this resolver declares every contested key —
    the test below asserts that premise before resolving — so the last-sorting
    dest is the winner for all of them.
    """
    return installed[max(installed)][key]


# --- the Definition of Done's first assertion -------------------------------


def test_the_two_roles_that_meet_on_one_host_install_one_keyring_budget() -> None:
    """Agreement first, then the sizing — the ordering dependence and the budget.

    With two numbers there is no "effective value" to speak of: the live one is
    whichever of the two plays ran last, and the other play's post-apply check
    then refuses. With one number there is no order to get wrong, and the
    remaining question is whether that number is big enough for both owners.
    """
    shared = _hosts_reached_by(role=_NODE_SYSCTL_ROLE) & _hosts_reached_by(role=_KEYRING_QUOTA_ROLE)
    assert shared, (
        f"no host is reached by both {_NODE_SYSCTL_ROLE} and {_KEYRING_QUOTA_ROLE}, so this "
        f"file is fencing nothing. hp-xubuntu is in `ci_pool` AND `sandbox_hosts` and never "
        f"leaves the latter; if that stopped being true, say so here deliberately rather than "
        f"letting the agreement go unchecked"
    )
    records = _records()
    installed = {dest: _declared_in(conf=conf) for dest, conf, _ in records.values()}
    assert len(installed) == len(records), (
        f"each role must install its keyring budget at its OWN path, or one silently overwrites "
        f"the other's file; got {sorted(installed)}"
    )
    for dest, declared in sorted(installed.items()):
        assert set(_CONTESTED_KEYS) <= set(declared), (
            f"{dest} must declare every key both roles own ({list(_CONTESTED_KEYS)}): a drop-in "
            f"that declares only some of them leaves the rest to whatever the other file says, "
            f"which is a second state by omission; got {sorted(declared)}"
        )
    for key in _CONTESTED_KEYS:
        values = {dest: declared[key] for dest, declared in sorted(installed.items())}
        assert len(set(values.values())) == 1, (
            f"the drop-ins disagree about {key}: {values}. The live value is then whichever of "
            f"ansible/ci-pool.yml and ansible/fabro-hosts.yml ran last on a host carrying both "
            f"({sorted(shared)}), because each role's apply loads only its own file — and the "
            f"other role's post-apply check refuses it. Converge them on one number"
        )
        effective = _effective(installed=installed, key=key)
        for role, (_dest, _conf, budget) in sorted(records.items()):
            assert effective >= budget[key], (
                f"the effective {key} is {effective}, below the {budget[key]} role {role} "
                f"requires. The shared number has to satisfy BOTH owners: the k3s container "
                f"keyring budget a kubelet's containers need, and the per-caller 1Password "
                f"cache entries with-livespec-env.sh holds"
            )


def test_each_role_installs_exactly_the_budget_its_own_defaults_require() -> None:
    """Each role still ships its own exact number — the drop-in may not drift from the role.

    `node_sysctl` reading its budget as a floor must not become a licence for its
    shipped drop-in to declare something other than what the role asserts. Both
    roles already guard this at apply time, controller-side; asserting it here
    means a drift fails in the suite rather than on the host.
    """
    records = _records()
    assert [sorted(budget) for _dest, _conf, budget in records.values()] == [
        sorted(_CONTESTED_KEYS)
    ] * len(records), (
        f"both roles must assert exactly {list(_CONTESTED_KEYS)} — no more and no fewer. A key "
        f"one role owns and the other does not is a new conflict this file would resolve as "
        f"agreement; got "
        f"{ {role: sorted(budget) for role, (_d, _c, budget) in records.items()} }"
    )
    for role, (_dest, conf, budget) in sorted(records.items()):
        declared = _declared_in(conf=conf)
        assert {key: declared[key] for key in sorted(budget)} == budget, (
            f"role {role} asserts {budget} and its shipped {conf.name} declares {declared}. The "
            f"file carries the measurements the numbers come from; reconcile them rather than "
            f"letting the asserted ceiling and the installed one drift apart"
        )
