"""`ansible/ci-pool.yml` must create the factory workspace root on the FACTORY nodes.

THE QUESTION THIS FILE ANSWERS (work-item livespec-dev-tooling-due2h6,
Definition of Done assertion 1). The kubernetes-sandbox-backend plugin takes ONE
`workspace_root`, so every node that can take a factory pod must offer a
directory at the SAME absolute path. That path is `/srv/factory-workspaces`, it
is `root:root` mode `0755` — the sandbox image's `Config.User` is empty, so its
pods run as root until the plugin's pod spec says otherwise (backend plan's
2026-10-16 correction) — and the set of nodes that must carry it is "the ci_pool
hosts whose committed phase0 profile sets `FACTORY_NODE=true`", which today is
all three and is NOT the same question as `cluster_role` or
`CI_NODE_FACILITIES`.

WHY A RESOLVER AND NOT AN `ansible-playbook` RUN, and why this file carries its
own small one rather than importing the sibling's. `ci-pool.yml` reaches a real
cluster (`node_taints` and `node_labels` delegate kubectl to the server,
`node_status_credential` mints a credential, `storage_layout` mounts volumes), so
a test cannot run the play; what CAN be resolved off-host is the `when:` gate
attached to the role entry, evaluated against the facts the inventory and the
profiles supply. `test_ci_pool_factory_only_agent_roles.py` resolves the same
play for the `CI_NODE_FACILITIES` axis, and its readers are private to it —
pyright strict and the `private_calls` check both refuse a cross-module private
import — so the few lines of reading are repeated here rather than reached for.
That file keeps the shared control: no gate in the play may take a shape either
resolver would evaluate differently from Jinja.

WHAT IS DERIVED AND WHAT IS STATED. The role's path, owner, group and mode are
READ out of the role's own `defaults/main.yml` and the task that applies them is
held to referencing those variables rather than re-spelling the literals, so the
role has one source for each value. The EXPECTED path, owner, group and mode are
stated, because the Definition of Done states them. The HOST SET is derived
twice over: from the inventory's `ci_pool` membership and from each host's
committed profile, so a fourth node added to the pool with `FACTORY_NODE=true`
is covered by construction, and a node whose profile declares `false` resolves
to not running the role — the control arm that makes "exactly" mean anything.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_PLAY = _ANSIBLE / "ci-pool.yml"
_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"
_PROFILES = _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles"
_ROLE = _ANSIBLE / "roles" / "factory_workspace_root"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"
_ROLE_CAPACITY = _ROLE / "CAPACITY.md"

_ROLE_NAME = "factory_workspace_root"

# The Definition of Done's own four values. The path is the one the sandbox
# plugin is configured with, so it is a cross-repository agreement rather than a
# local preference; the ownership and mode are what a root-running pod needs.
_EXPECTED = {
    "factory_workspace_root_path": "/srv/factory-workspaces",
    "factory_workspace_root_owner": "root",
    "factory_workspace_root_group": "root",
    "factory_workspace_root_mode": "0755",
}
# The profile key the gate must be keyed on, and the default a profile written
# before the key existed resolves to. `false` is the phase0 parser's own default
# (`ci-runner/k3s/phase0-bare-metal/profile.sh`), so a host that says nothing
# gets no workspace root rather than an error.
_PROFILE_KEY = "FACTORY_NODE"
_PROFILE_DEFAULT = "false"

# A `roles:` entry and its optional gate, matched as text because no YAML library
# is importable in this suite — `[dependency-groups].dev` carries none,
# deliberately: the package is dependency-free.
_ROLE_ENTRY = re.compile(
    r"^    - role: (?P<role>\w+)$(?P<body>(?:\n(?:      .*|))*)",
    re.MULTILINE,
)
_WHEN_LINE = re.compile(r"^      when: (?P<expression>.+)$", re.MULTILINE)
_GATE = re.compile(r"^(?P<fact>[a-z_]+) == '(?P<literal>[\w-]+)'$")
# A play-level var whose value is the profile's own `^KEY=value$` line, read with
# the same `regex_findall | first | default(...)` chain every role in this tree
# reads a profile with.
_PROFILE_FACT = re.compile(
    r"^    (?P<fact>[a-z_]+): >-\n"
    r"\s*\{\{ lookup\('ansible\.builtin\.file', \w+\)\n"
    r"\s*\| regex_findall\('\^(?P<key>[A-Z_]+)=\(\.\*\)\$', multiline=True\)"
    r" \| first \| default\('(?P<fallback>\w*)'\) \}\}$",
    re.MULTILINE,
)
_CI_POOL_BLOCK = re.compile(
    r"^        ci_pool:\n          hosts:\n(?P<body>(?:.*\n)*?)^        \S", re.MULTILINE
)
_INVENTORY_HOST = re.compile(r"^            (?P<host>[\w-]+):$", re.MULTILINE)
# The one `defaults/main.yml` line shape this reader accepts: `key: value`, the
# value optionally quoted (`mode` MUST be quoted — an unquoted 0755 is YAML's
# octal-looking INTEGER 755 and `file` would apply mode 0o1363).
_DEFAULT_LINE = re.compile(r"^(?P<key>[a-z_]+): (?P<value>.+)$", re.MULTILINE)


def _play_text() -> str:
    """The committed `ci-pool.yml`, as Ansible receives it."""
    return _PLAY.read_text(encoding="utf-8")


def _role_gates() -> dict[str, str | None]:
    """Every `roles:` entry of the play, as `role -> gate-or-None`.

    Read for the WHOLE play rather than for the one role in question, so the
    ungated entries are resolved by the same expression as the gated ones — a
    reader that only ever took the gated arm would be a reader whose other arm
    nothing had run.
    """
    gates = {
        match["role"]: (found["expression"].strip() if found else None)
        for match in _ROLE_ENTRY.finditer(_play_text())
        for found in [_WHEN_LINE.search(match["body"])]
    }
    assert gates, (
        f"{_PLAY.name} must declare its roles as `    - role: <name>` entries; this reader "
        f"cannot resolve a play whose roles it cannot find, and an unseen role is a converge "
        f"nothing here checks"
    )
    return gates


def _profile_facts() -> dict[str, tuple[str, str]]:
    """Each play-level fact read from a profile, as `fact -> (profile key, default)`."""
    return {
        match["fact"]: (match["key"], match["fallback"])
        for match in _PROFILE_FACT.finditer(_play_text())
    }


def _ci_pool_hosts() -> tuple[str, ...]:
    """Every `ci_pool` host the play targets, from the committed inventory."""
    block = _CI_POOL_BLOCK.search(_INVENTORY.read_text(encoding="utf-8"))
    assert block is not None, (
        f"{_INVENTORY.name} must declare a `ci_pool` group with a `hosts:` mapping — it is "
        f"what `ci-pool.yml` targets, and a play with no hosts converges nothing"
    )
    hosts = tuple(match["host"] for match in _INVENTORY_HOST.finditer(block["body"]))
    assert hosts, f"{_INVENTORY.name}: the `ci_pool` group must list at least one host"
    return hosts


def _declared_factory_node(*, host: str) -> str:
    """One host's `FACTORY_NODE`, read from its committed profile as the play reads it."""
    profile = _PROFILES / f"{host}.env"
    assert profile.is_file(), (
        f"{profile.relative_to(_REPO_ROOT)} must be committed: the play reads each ci_pool "
        f"host's posture out of its own phase0 profile, so a host without one cannot be gated"
    )
    found = re.findall(
        rf"^{re.escape(_PROFILE_KEY)}=(.*)$", profile.read_text(encoding="utf-8"), re.MULTILINE
    )
    return found[0] if found else _PROFILE_DEFAULT


def _role_defaults() -> dict[str, str]:
    """The role's `defaults/main.yml`, as `key -> value` with any quoting stripped."""
    assert _ROLE_DEFAULTS.is_file(), (
        f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)} must be committed: the workspace root's "
        f"path is an agreement with the kubernetes-sandbox-backend plugin's single "
        f"`workspace_root`, so it belongs in defaults where a reader and a host can both "
        f"resolve it — never spelled inline in a task"
    )
    return {
        match["key"]: match["value"].strip().strip("\"'")
        for match in _DEFAULT_LINE.finditer(_ROLE_DEFAULTS.read_text(encoding="utf-8"))
    }


def _resolved_hosts() -> tuple[str, ...]:
    """The `ci_pool` hosts the play runs `factory_workspace_root` on, in inventory order."""
    gate = _role_gates().get(_ROLE_NAME)
    assert gate is not None, (
        f"{_PLAY.name} must run role `{_ROLE_NAME}` under a `when:` gate: an ungated role runs "
        f"on every ci_pool host, which would create the workspace root on a node that is not a "
        f"factory node and make the FACTORY_NODE key decoration"
    )
    parsed = _GATE.fullmatch(gate)
    assert parsed is not None, (
        f"the `when:` on role `{_ROLE_NAME}` is {gate!r}, which this resolver cannot evaluate "
        f"faithfully. A gate must be `<fact> == '<literal>'`: neither Ansible nor Jinja is "
        f"importable in this suite, so a richer expression would be resolved WRONG here and "
        f"right on the host"
    )
    facts = _profile_facts()
    assert facts.get(parsed["fact"]) == (_PROFILE_KEY, _PROFILE_DEFAULT), (
        f"the gate on role `{_ROLE_NAME}` reads {parsed['fact']!r}, which the play must declare "
        f"as a play-level fact read from the profile's {_PROFILE_KEY} with the parser's own "
        f"default {_PROFILE_DEFAULT!r}; the play declares {facts}"
    )
    return tuple(
        host for host in _ci_pool_hosts() if _declared_factory_node(host=host) == parsed["literal"]
    )


def test_the_role_creates_the_workspace_root_with_the_ownership_and_mode_a_root_pod_needs() -> None:
    """One directory, `root:root`, mode `0755`, declared once and applied by reference.

    The sandbox image's `Config.User` is empty, so a factory pod runs as root
    until the plugin's pod spec says otherwise; `root:root 0755` is therefore
    writable by the pod and readable by everything else on the node. The four
    values live in `defaults/main.yml` and the task carries `{{ … }}` references
    to them, so the role has exactly one source for each and a host or a reader
    can resolve them without parsing a task body.
    """
    defaults = _role_defaults()
    for key, expected in _EXPECTED.items():
        assert defaults.get(key) == expected, (
            f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)} must declare `{key}: {expected}`; it "
            f"declares {defaults.get(key)!r}. The path is the plugin's single `workspace_root` "
            f"and the ownership and mode are what a root-running pod needs"
        )
    assert defaults["factory_workspace_root_mode"] == "0755", "mode must be the string 0755"
    mode_line = f'factory_workspace_root_mode: "{_EXPECTED["factory_workspace_root_mode"]}"'
    assert mode_line in _ROLE_DEFAULTS.read_text(encoding="utf-8"), (
        f"and the mode must be QUOTED as `{mode_line}` — an unquoted 0755 is YAML's "
        f"octal-looking INTEGER 755, which `ansible.builtin.file` applies as mode 0o1363"
    )
    assert _ROLE_TASKS.is_file(), (
        f"{_ROLE_TASKS.relative_to(_REPO_ROOT)} must be committed: the role has to actually "
        f"create the directory, and defaults alone converge nothing"
    )
    tasks = _ROLE_TASKS.read_text(encoding="utf-8")
    assert "state: directory" in tasks, (
        f"{_ROLE_TASKS.relative_to(_REPO_ROOT)} must create the workspace root with "
        f"`ansible.builtin.file` + `state: directory`"
    )
    for key in _EXPECTED:
        assert f"{{{{ {key} }}}}" in tasks, (
            f"the create task must reference `{{{{ {key} }}}}` rather than re-spelling its "
            f"literal: two spellings is two facts the day one of them is edited, which is how a "
            f"retired taint came back on gmktec (livespec-dev-tooling-yapwva)"
        )


def test_the_role_refuses_a_workspace_root_that_is_not_on_a_persistent_filesystem() -> None:
    """Non-tmpfs is a REQUIREMENT, so the role measures it rather than assuming it.

    A workspace root on a volatile filesystem loses a factory run's workspace at
    the next boot with nothing erroring — the silent-at-reboot shape this pool
    has already paid for (`ci-runner/k3s/phase2/factory/factory-namespace.yaml`
    records the Namespace half). The role resolves the mount serving the path
    from the play's gathered `ansible_mounts` and refuses a volatile fstype, so
    "persistent" is a measurement on the host and not a claim in a comment.
    """
    defaults = _role_defaults()
    tasks = _ROLE_TASKS.read_text(encoding="utf-8") if _ROLE_TASKS.is_file() else ""
    volatile = defaults.get("factory_workspace_root_volatile_fstypes", "")
    for fstype in ("tmpfs", "ramfs"):
        assert fstype in volatile, (
            f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)} must declare "
            f"`factory_workspace_root_volatile_fstypes` naming at least tmpfs and ramfs — the "
            f"two filesystems that would make the workspace root vanish at a reboot; it "
            f"declares {volatile!r}"
        )
    assert "ansible_mounts" in tasks, (
        f"{_ROLE_TASKS.relative_to(_REPO_ROOT)} must resolve the mount serving the workspace "
        f"root from the play's gathered `ansible_mounts`, which is readable under `--check` "
        f"too — a `findmnt` command would be SKIPPED by the drift report and would exit "
        f"non-zero on a host where the directory does not exist yet"
    )
    assert "factory_workspace_root_volatile_fstypes" in tasks, (
        "and it must assert the resolved fstype against that list, so a volatile filesystem "
        "is a loud refusal rather than a workspace root that silently empties at boot"
    )
    assert "factory_workspace_root_lineage" in defaults, (
        f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)} must declare "
        f"`factory_workspace_root_lineage` — the path's own ancestry, which is what makes "
        f"'the mount serving this path' resolvable from `ansible_mounts` by exact membership "
        f"rather than by a substring match that `/factory-workspaces` would satisfy"
    )


def test_the_play_creates_the_workspace_root_on_exactly_the_factory_nodes() -> None:
    """The host set, resolved from the inventory and the profiles rather than stated.

    `cluster_role` answers "server or agent" and `CI_NODE_FACILITIES` answers
    "does this node execute CI jobs"; NEITHER answers "can this node take a
    factory pod". `poweredge-xubuntu` runs factory pods AND is untainted
    (maintainer ruling 2026-10-13), and `hp-xubuntu` takes factory pods while
    executing no CI job at all — so the workspace root's host set is the
    FACTORY_NODE axis and nothing else.
    """
    resolved = _resolved_hosts()
    expected = tuple(
        host for host in _ci_pool_hosts() if _declared_factory_node(host=host) == "true"
    )
    assert resolved == expected, (
        f"`{_ROLE_NAME}` must run on exactly the ci_pool hosts whose profile sets "
        f"{_PROFILE_KEY}=true.\nexpected: {expected}\nresolved: {resolved}"
    )
    assert set(expected) == {"poweredge-xubuntu", "gmktec-xubuntu", "hp-xubuntu"}, (
        f"and that set is all three pool nodes today — the untainted server included, which is "
        f"why the gate could not be spelled as `cluster_role == 'agent'` or as the tainted "
        f"ones; it resolved to {expected}"
    )


def test_a_pool_node_that_does_not_declare_itself_a_factory_node_gets_no_workspace_root() -> None:
    """The control arm: without it the test above would pass on an ungated role.

    Every committed profile declares `FACTORY_NODE=true` today, so "exactly the
    factory nodes" and "every pool node" resolve identically against the
    committed tree. This arm resolves the play's own gate against the other two
    answers a profile may give — `false`, and the absent key that falls back to
    the parser's default — and both must yield no workspace root.
    """
    gate = _role_gates().get(_ROLE_NAME)
    assert gate is not None, f"role `{_ROLE_NAME}` must carry a `when:` gate; see the resolver"
    parsed = _GATE.fullmatch(gate)
    assert parsed is not None, f"unresolvable gate {gate!r}"
    for declared in ("false", _PROFILE_DEFAULT):
        assert declared != parsed["literal"], (
            f"a profile declaring {_PROFILE_KEY}={declared} must not satisfy the gate on role "
            f"`{_ROLE_NAME}` ({gate!r}). A node that does not declare itself a factory node "
            f"must not be given a factory workspace root: the directory would be unreferenced "
            f"state on a host nothing schedules a factory pod to"
        )


def test_the_capacity_reasoning_is_recorded_beside_the_role() -> None:
    """Six concurrent pods is the quota's own ceiling, and the sizing must say so.

    The work-item requires the path to be sized for the six concurrent pods the
    `factory-runs` ResourceQuota admits and the reasoning recorded beside the
    role. The record is asserted to exist and to name both the quota that sets
    the ceiling and the node that binds it, because a capacity note that names
    neither is a number with no derivation — the defect
    `ci-runner/k3s/phase2/factory/DERIVATION.md` exists to prevent for the quota
    itself.
    """
    assert _ROLE_CAPACITY.is_file(), (
        f"{_ROLE_CAPACITY.relative_to(_REPO_ROOT)} must be committed: the work-item requires "
        f"the capacity reasoning to sit BESIDE the role, the way DERIVATION.md sits beside the "
        f"manifest whose numbers it derives"
    )
    capacity = _ROLE_CAPACITY.read_text(encoding="utf-8")
    for token in ("factory-runs", "/srv/factory-workspaces", "poweredge-xubuntu"):
        assert token in capacity, (
            f"{_ROLE_CAPACITY.relative_to(_REPO_ROOT)} must name {token!r}: the quota whose "
            f'`pods: "6"` is the ceiling, the path being sized, and the node whose free '
            f"space binds the budget"
        )
