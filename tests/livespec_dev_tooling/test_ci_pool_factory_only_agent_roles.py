"""Which `ansible/ci-pool.yml` roles run on each `ci_pool` host — resolved, not assumed.

THE QUESTION THIS FILE ANSWERS (work-item livespec-dev-tooling-7we6po,
Definition of Done assertion 2). `hp-xubuntu` joins `ci_pool` as a FACTORY-ONLY
agent: it carries none of the pool's CI storage tiers and executes no CI job, so
four of the play's roles have nothing to do on it. `poweredge-xubuntu` and
`gmktec-xubuntu` must keep running everything they run today. Those are claims
about the PLAY's own gating, resolved from the two committed inputs the play
resolves them from — `ansible/inventory/legacy.yml` and each host's phase0
profile — and nothing else.

WHY A RESOLVER AND NOT AN `ansible-playbook` RUN. `ci-pool.yml` reaches a real
cluster: `node_taints` and `node_labels` delegate kubectl to the server,
`node_status_credential` mints a credential, `storage_layout` mounts volumes. A
test cannot run the play, and the fleet host guard rightly refuses an
`ansible-playbook` invocation against an uncommitted one. What CAN be resolved
off-host is the thing in question: the `when:` expression attached to each role
entry, evaluated against the facts the inventory and the profiles supply. So
this file reads the play's role list and its gates, reads the inventory's
`ci_pool` membership and each host's `cluster_role`, reads each host's committed
profile, and resolves the three answers.

A `roles:`-level `when:` IS "no task of that role runs": Ansible applies it to
every task the role contributes, including the tasks of any `include_tasks` they
reach, so a false gate means no task of that role executes and no handler it
would notify fires. The maintainer's 2026-10-13 ruling chose `when:` gates in
the ONE play over a second play, because the runner-pool node rebuild recipe in
`SPECIFICATION/non-functional-requirements.md` requires exactly one procedure
taking a pool node from powered-on hardware to a pool member — and names the
committed `ansible/ci-pool.yml` as its node-provisioning stage. This file is the
proof that mechanism asks for.

THE RESOLVER'S VOCABULARY IS DELIBERATELY TINY, AND ONE TEST KEEPS IT HONEST.
Neither Ansible nor Jinja is importable in this suite (`ansible-lint` and
`ansible-playbook` are resolved through `uvx` against their own interpreter —
see the justfile — because ansible-core 2.21 requires a Python floor this
repository does not carry). So a gate may only be `<name> == '<literal>'`, and
`test_every_role_gate_stays_inside_the_vocabulary_this_test_can_resolve` fails
the moment the play grows a gate this file would resolve differently from
Ansible. A resolver that quietly disagreed with the play would be worse than no
resolver: it would report a converge that does not happen.

WHAT IS DERIVED AND WHAT IS STATED. The role list, every gate, the fact names
and the profile key each fact is read from are all READ out of the committed
play, so a play that gates differently fails here instead of being
re-described. The EXPECTED SETS are stated — `hp-xubuntu`'s four skips and four
required roles because the Definition of Done states them, and the other two
hosts' full lists because "every role it runs today" has to be written down
somewhere for a role silently dropped from them to fail.
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
_NODE_LABELS_DEFAULTS = _ANSIBLE / "roles" / "node_labels" / "defaults" / "main.yml"
_PROVISION = _REPO_ROOT / "ci-runner" / "k3s" / "provision-k3s.sh"

# The Definition of Done's own four-and-four, stated because it states them.
_HP = "hp-xubuntu"
_HP_MUST_NOT_RUN = frozenset(
    {
        "storage_layout",
        "container_hook",
        "sccache_binary",
        "cache_telemetry",
    }
)
_HP_MUST_RUN = frozenset(
    {
        "k3s_config",
        "agent_rejoin",
        "node_taints",
        # The factory-label reconcile the Definition of Done names. It is the
        # role, not a task inside another one, because the label has to be
        # reconciled on every ci_pool node and `node_taints` owns exactly one
        # taint key and nothing else.
        "node_labels",
    }
)

# Every role the two CI nodes run today, stated as a literal for the same reason
# `provision-k3s-exit-tests.sh` §A states the server's plan as one: its whole job
# is to fail if a future edit drops a role from a node that needs it. Ordered as
# the play orders them, which is `install-node.sh`'s retired STEP_IDS order.
_POWEREDGE_ROLES = (
    "k3s_config",
    "agent_node_password",
    "node_sysctl",
    "storage_layout",
    "host_thermal",
    "host_tools_ci",
    "fpart",
    "apparmor_profile",
    "node_status_credential",
    "node_extended_resource",
    "node_taints",
    "node_labels",
    "wedged_runner",
    "runner_pod_lifecycle",
    "arc_log_archive",
    "secret_reinjection",
    "sccache_binary",
    "cache_telemetry",
    "container_hook",
    "ci_converge_unit",
    "datastore_tmpfs",
    "storage_sweep",
)
_GMKTEC_ROLES = (
    "k3s_config",
    "agent_rejoin",
    "node_sysctl",
    "storage_layout",
    "host_tools_ci",
    "fpart",
    "apparmor_profile",
    "node_status_credential",
    "node_extended_resource",
    "node_taints",
    "node_labels",
    "wedged_runner",
    "runner_pod_lifecycle",
    "arc_log_archive",
    "sccache_binary",
    "cache_telemetry",
    "container_hook",
    "storage_sweep",
)

# The label both carriers must spell identically: the install command at join
# time and the role that reconciles it on every apply. Two spellings is two
# facts the day one of them is edited, which is how a retired taint came back on
# gmktec (livespec-dev-tooling-yapwva).
_FACTORY_LABEL = "ci-runner.io/factory=true"

# A `roles:` entry and its optional gate. Matched as text because no YAML library
# is importable in this suite — `[dependency-groups].dev` carries none,
# deliberately: the package is dependency-free.
_ROLE_ENTRY = re.compile(
    r"^    - role: (?P<role>\w+)$(?P<body>(?:\n(?:      .*|))*)",
    re.MULTILINE,
)
_WHEN_LINE = re.compile(r"^      when: (?P<expression>.+)$", re.MULTILINE)
# The only shape a gate may take, so this resolver cannot disagree with Jinja.
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
_INVENTORY_HOST = re.compile(
    r"^            (?P<host>[\w-]+):$(?P<body>(?:\n(?:              .*|))*)",
    re.MULTILINE,
)
_CI_POOL_BLOCK = re.compile(
    r"^        ci_pool:\n          hosts:\n(?P<body>(?:.*\n)*?)^        \S", re.MULTILINE
)
_CLUSTER_ROLE = re.compile(r"^              cluster_role: (?P<role>\w+)$", re.MULTILINE)


# --- reading the committed play ---------------------------------------------


def _play_text() -> str:
    """The committed `ci-pool.yml`, as Ansible receives it."""
    return _PLAY.read_text(encoding="utf-8")


def _role_entries() -> list[tuple[str, str | None]]:
    """Every `roles:` entry of the play, as `(role, gate-or-None)` in play order."""
    entries = [
        (match["role"], (gate["expression"].strip() if gate else None))
        for match in _ROLE_ENTRY.finditer(_play_text())
        for gate in [_WHEN_LINE.search(match["body"])]
    ]
    assert entries, (
        f"{_PLAY.name} must declare its roles as `    - role: <name>` entries; this reader "
        f"cannot resolve a play whose roles it cannot find, and an unseen role is a converge "
        f"nothing here checks"
    )
    return entries


def _profile_facts() -> dict[str, tuple[str, str]]:
    """Each play-level fact read from a profile, as `fact -> (profile key, default)`."""
    return {
        match["fact"]: (match["key"], match["fallback"])
        for match in _PROFILE_FACT.finditer(_play_text())
    }


# --- reading the committed inventory and profiles ---------------------------


def _ci_pool_hosts() -> dict[str, str]:
    """Every `ci_pool` host and its declared `cluster_role`, from the inventory."""
    block = _CI_POOL_BLOCK.search(_INVENTORY.read_text(encoding="utf-8"))
    assert block is not None, (
        f"{_INVENTORY.name} must declare a `ci_pool` group with a `hosts:` mapping — it is "
        f"what `ci-pool.yml` targets, and a play with no hosts converges nothing"
    )
    hosts: dict[str, str] = {}
    for match in _INVENTORY_HOST.finditer(block["body"]):
        role = _CLUSTER_ROLE.search(match["body"])
        assert role is not None, (
            f"{_INVENTORY.name}: ci_pool host {match['host']} must declare a `cluster_role` — "
            f"it is what selects the server-only and agent-only roles, and a host without one "
            f"reaches every `cluster_role ==` gate with an undefined variable"
        )
        hosts[match["host"]] = role["role"]
    assert _HP in hosts, (
        f"{_INVENTORY.name} must list {_HP} in `ci_pool`: it joins the pool as an agent while "
        f"STAYING in `sandbox_hosts`, which is what keeps ansible/fabro-hosts.yml reaching it"
    )
    return hosts


def _host_facts(*, host: str, cluster_role: str) -> dict[str, str]:
    """Every fact a gate may read, for one host, from the inventory and its profile."""
    profile = _PROFILES / f"{host}.env"
    assert profile.is_file(), (
        f"{profile.relative_to(_REPO_ROOT)} must be committed: the play reads each ci_pool "
        f"host's posture out of its own phase0 profile, so a host without one cannot be gated"
    )
    text = profile.read_text(encoding="utf-8")
    facts = {"cluster_role": cluster_role}
    for fact, (key, default) in _profile_facts().items():
        found = re.findall(rf"^{re.escape(key)}=(.*)$", text, re.MULTILINE)
        facts[fact] = found[0] if found else default
    return facts


# --- the resolver -----------------------------------------------------------


def _resolved_roles(*, facts: dict[str, str]) -> tuple[str, ...]:
    """The roles the play runs on a host with `facts`, in play order."""
    resolved: list[str] = []
    for role, gate in _role_entries():
        if gate is None:
            resolved.append(role)
            continue
        parsed = _GATE.fullmatch(gate)
        assert parsed is not None, f"unresolvable gate {gate!r} (see the vocabulary test)"
        if facts[parsed["fact"]] == parsed["literal"]:
            resolved.append(role)
    return tuple(resolved)


def _roles_by_host() -> dict[str, tuple[str, ...]]:
    """Every `ci_pool` host's resolved role list."""
    return {
        host: _resolved_roles(facts=_host_facts(host=host, cluster_role=cluster_role))
        for host, cluster_role in sorted(_ci_pool_hosts().items())
    }


# --- the control on the resolver --------------------------------------------


def test_every_role_gate_stays_inside_the_vocabulary_this_test_can_resolve() -> None:
    """No filter, no `and`, no `is defined` — a gate is one fact against one literal.

    Without this the resolver below is free to drift from Ansible, and a drifted
    resolver reports a converge that does not happen, which is worse than
    reporting nothing.
    """
    facts = _profile_facts()
    assert facts, (
        f"{_PLAY.name} must read each host's posture from its committed profile as a "
        f"play-level `vars:` fact, with the same `regex_findall | first | default()` chain "
        f"every role in this tree reads a profile with. A gate keyed on anything else is a "
        f"second source for a fact the profile owns"
    )
    resolvable = {"cluster_role", *facts}
    for role, gate in _role_entries():
        if gate is None:
            continue
        parsed = _GATE.fullmatch(gate)
        assert parsed is not None, (
            f"the `when:` on role {role} is {gate!r}, which this resolver cannot evaluate "
            f"faithfully. A gate must be `<fact> == '<literal>'`: neither Ansible nor Jinja "
            f"is importable in this suite, so a richer expression would be resolved WRONG "
            f"here and right on the host"
        )
        assert parsed["fact"] in resolvable, (
            f"the `when:` on role {role} reads {parsed['fact']!r}, which is neither "
            f"`cluster_role` from the inventory nor a play-level fact read from the profile "
            f"({sorted(facts)}). A gate on anything else is a fact this file cannot resolve "
            f"and the rebuild recipe cannot trace to a profile"
        )


def test_the_posture_fact_the_gates_read_comes_from_the_profile_key_that_owns_it() -> None:
    """The play's own profile read, and the key it reads — asserted, not assumed."""
    facts = _profile_facts()
    assert facts == {"ci_pool_ci_node_facilities": ("CI_NODE_FACILITIES", "full")}, (
        f"the play must read exactly one posture fact, `ci_pool_ci_node_facilities`, from the "
        f"profile's CI_NODE_FACILITIES, defaulting to the parser's own default `full` so a "
        f"profile written before the key existed resolves to what it already is; got {facts}"
    )


# --- the Definition of Done's second assertion ------------------------------


def test_hp_runs_no_task_of_the_four_roles_a_factory_only_agent_has_nothing_for() -> None:
    """The tiers it does not carry, and the job-execution facilities it never uses.

    `storage_layout` mounts and binds the three LABEL-keyed tiers; `container_hook`
    extracts the fleet-patched ARC container hook and its externals;
    `sccache_binary` and `cache_telemetry` install the two binaries
    `arc/hook-pod-template.yaml` mounts read-only into every JOB container. hp
    declares no tier and runs no job, so all four would converge a facility with
    nothing on the other end of it.
    """
    resolved = set(_roles_by_host()[_HP])
    leaked = sorted(_HP_MUST_NOT_RUN & resolved)
    assert not leaked, (
        f"{_HP} must run no task of {sorted(_HP_MUST_NOT_RUN)}; the play still runs {leaked} "
        f"on it. A role gated on nothing runs everywhere, and a tier role on a node with no "
        f"tier refuses the apply at its first label resolution"
    )


def test_hp_runs_the_four_roles_that_make_a_closed_node_closed_and_visible() -> None:
    """What a factory-only agent still needs, and why each one.

    `k3s_config` renders the taint the node STARTS with, which is what survives a
    control-plane reboot; `agent_rejoin` installs the watchdog that re-registers
    it; `node_taints` reconciles the LIVE taint to the profile; `node_labels`
    reconciles the factory label, which `--node-label` applies at registration
    only and so cannot keep by itself.
    """
    resolved = set(_roles_by_host()[_HP])
    missing = sorted(_HP_MUST_RUN - resolved)
    assert not missing, (
        f"{_HP} must run {sorted(_HP_MUST_RUN)}; the play does not reach {missing} on it. "
        f"Closed is a POSITIVE statement this node has to keep making — a node that merely "
        f"stopped advertising would be indistinguishable from one that had drifted"
    )


def test_the_two_ci_nodes_still_run_every_role_they_run_today() -> None:
    """The regression arm: gating hp must change nothing about poweredge or gmktec.

    Asserted as an ORDERED EQUALITY rather than a membership test, because the
    play's role order IS the retired `install-node.sh` step plan and the header of
    `ci-pool.yml` states three orderings that are load-bearing on their own —
    credential before capacity before taint among them.
    """
    resolved = _roles_by_host()
    for host, expected in (
        ("poweredge-xubuntu", _POWEREDGE_ROLES),
        ("gmktec-xubuntu", _GMKTEC_ROLES),
    ):
        assert resolved[host] == expected, (
            f"{host} must still run every role it runs today, in the play's order.\n"
            f"expected: {expected}\n"
            f"resolved: {resolved[host]}"
        )


def test_the_factory_label_is_spelled_once_per_carrier_and_the_two_agree() -> None:
    """The join-time carrier and the converge-time carrier must never disagree.

    `provision-k3s.sh` registers the label at JOIN; `node_labels` reconciles it on
    every APPLY. Two spellings is two facts the day one of them is edited — which
    is exactly how a retired taint came back on gmktec after a reboot
    (livespec-dev-tooling-yapwva).
    """
    assert _NODE_LABELS_DEFAULTS.is_file(), (
        f"{_NODE_LABELS_DEFAULTS.relative_to(_REPO_ROOT)} must be committed: the factory "
        f"label's converge-time carrier is a role of its own, because `--node-label` applies "
        f"at REGISTRATION only and a label nothing reconciles goes stale exactly as a taint "
        f"did on gmktec"
    )
    defaults = _NODE_LABELS_DEFAULTS.read_text(encoding="utf-8")
    key, _, value = _FACTORY_LABEL.partition("=")
    assert f"node_labels_factory_key: {key}" in defaults, (
        f"the role must hold the factory label's KEY in defaults/main.yml as "
        f"`node_labels_factory_key: {key}` — a key spelled inline in a task is one no host "
        f"can redirect and no test can read;\ndefaults={defaults!r}"
    )
    # QUOTED, and the quoting is load-bearing rather than stylistic: a bare
    # `true` is a YAML BOOLEAN, so `{{ key }}={{ value }}` would render
    # `ci-runner.io/factory=True` — a label the install command's `=true` does
    # not match and the sandbox backend's selector would miss.
    assert f'node_labels_factory_value: "{value}"' in defaults, (
        f'and its VALUE as `node_labels_factory_value: "{value}"` — QUOTED, so Jinja renders '
        f"the string the install command registers and not YAML's boolean `True`;\n"
        f"defaults={defaults!r}"
    )
    assert _PROVISION.read_text(encoding="utf-8").count(_FACTORY_LABEL) == 1, (
        f"and provision-k3s.sh must spell {_FACTORY_LABEL!r} exactly once, as the constant "
        f"both role's install commands read"
    )
