"""The factory reach check as a CONVERGE ARTIFACT: installed, consent-gated, scoped.

WHY THIS FILE EXISTS (work-item livespec-dev-tooling-jvnqwv, Definition of Done
assertion 1; livespec plan `factory-worker-nodes-gitops`, epic `livespec-sqvj7p`).
`ci-runner/k3s/phase2/factory/verify-factory-reach.sh` landed with no sanctioned
run path: nothing installed it on the control-plane node, and a run would have
needed the root-only admin kubeconfig. Freeze ruling R70 (2026-10-16) rejected
running an exported tree under `sudo` by hand — that is what the GitOps
discipline forbids — and required the check to become a converge artifact like
every other proof on this plan. Three properties carry that, and this file
resolves all three from the committed play and role:

1. `ansible/ci-pool.yml` INSTALLS the four shipped files on the control-plane
   node, into the converge's own installed tree.
2. It RUNS the check only when the run-now variable is passed on one apply —
   the `ci_converge_unit_run_now` consent pattern, and for the same reason: a
   routine apply must never submit Jobs into the live `factory` namespace.
3. The run authenticates as the `factory` namespace's `sandbox-launcher`
   ServiceAccount and NEVER as the admin kubeconfig. That credential grants
   create/get/list/watch/delete on batch jobs and pods and get on pods/log in
   one namespace; the admin kubeconfig grants the cluster.

A FOURTH PROPERTY JOINED THEM (work-item livespec-dev-tooling-5iep7h, freeze
ruling R78 of 2026-10-16): the ENDPOINTS one run probes are suppliable on the
run-now apply. The committed
`ci-runner/k3s/phase2/factory/factory-reach-endpoints.env` names the telemetry
receiver at the dispatcher's EPHEMERAL per-dispatch port, recorded on
2026-10-13 — the file's own comment says so — so an apply against that value
proves nothing about a receiver that exists NOW. The override variable is what
lets the host-captured leg name the receiver of a dispatch live at that moment,
and it is forwarded as the renderer's OWN `--endpoint NAME=HOST:PORT` arguments
rather than as a second mechanism beside them.

WHY A STATIC RESOLVER AND NOT AN `ansible-playbook` RUN. The same reason
`test_ci_pool_factory_only_agent_roles.py` records: this play reaches a real
cluster, neither Ansible nor Jinja is importable in this suite (ansible-core is
resolved through `uvx` against its own interpreter), and the fleet host guard
rightly refuses an `ansible-playbook` invocation here. What CAN be resolved
off-host is what the play and the role COMMIT to — the role entry and its gate,
the install list, the consent gate on the run block, and the credential the run
task's `environment:` names. The live apply is the Definition of Done's
host-captured leg, which belongs to the control node.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_PLAY = _ANSIBLE / "ci-pool.yml"
_ROLE = _ANSIBLE / "roles" / "factory_reach_check"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"
_FACTORY_DIR = _REPO_ROOT / "ci-runner" / "k3s" / "phase2" / "factory"
_PROFILES = _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles"

_ROLE_NAME = "factory_reach_check"

# The artifact set the check needs on a node to run at all: the renderer, the
# probe it embeds verbatim, the endpoints it probes and the image it renders.
# Named here rather than globbed out of the factory directory, which also holds
# the namespace and RBAC manifests the boot converge applies — `ci_converge_unit`
# owns those two, one owner per file.
_SHIPPED = (
    "verify-factory-reach.sh",
    "factory-reach-probe.sh",
    "factory-reach-endpoints.env",
    "factory-reach-image.env",
)

# The converge's installed tree, and the subdirectory the boot converge already
# resolves its factory manifests from. Installing beside them is what makes the
# installed layout MIRROR the repository layout, which is what lets the script's
# `SCRIPT_DIR`-relative resolution of the probe and both configuration files
# work identically in each.
_LIB_DIR = "/usr/local/lib/ci-runner-k3s"
_INSTALL_DIR = f"{_LIB_DIR}/factory"

# The scoped credential `reconstruct/converge-ci-stack.sh` step 10e renders on
# the control-plane node at every boot, and the admin credential this run must
# never reach for. Both spelled here rather than read back out of the role: the
# whole assertion is WHICH of the two the run authenticates as, and a reader
# that took the answer from the role under test would agree with either.
_SCOPED_KUBECONFIG = "/etc/ci-runner/factory.kubeconfig"
_ADMIN_KUBECONFIG = "/etc/rancher/k3s/k3s.yaml"

# The consent variable and its mandatory default. `false` is load-bearing: the
# default apply must INSTALL and not run, because the run submits Jobs that take
# a `factory` ResourceQuota slot on a node sharing its box with the CI pool.
_RUN_NOW = "factory_reach_check_run_now"

# The nodes the Definition of Done's host-captured leg names. The default run
# covers every `ci_pool` node whose profile sets FACTORY_NODE=true, which is all
# three today — the server included, since poweredge takes factory pods too.
_HOST_CAPTURED_NODES = ("hp-xubuntu", "gmktec-xubuntu")

# A `roles:` entry and its optional gate, matched as text because no YAML
# library is importable in this suite (the package is deliberately
# dependency-free). The same two patterns
# `test_ci_pool_factory_only_agent_roles.py` reads the play with.
_ROLE_ENTRY = re.compile(
    r"^    - role: (?P<role>\w+)$(?P<body>(?:\n(?:      .*|))*)",
    re.MULTILINE,
)
_WHEN_LINE = re.compile(r"^      when: (?P<expression>.+)$", re.MULTILINE)

# The run-time endpoint override (livespec-dev-tooling-5iep7h, ruling R78): the
# variable an apply supplies, the argument list the role translates it into, and
# the committed pattern every entry must match. Named here rather than read back
# out of the role, for the reason this file's header records about the
# credential: a reader that took the names from the role under test would agree
# with any rename, and these three are the operator-facing surface.
_ENDPOINTS_VAR = "factory_reach_check_endpoints"
_ENDPOINT_ARGV_VAR = "factory_reach_check_endpoint_argv"
_ENDPOINT_PATTERN_VAR = "factory_reach_check_endpoint_pattern"

# The module key of the ONE task in this role that executes anything, which is
# the boundary "before any Job is submitted" names. Everything ahead of it in
# the file runs on the controller and submits nothing.
_RUN_MODULE = "ansible.builtin.command"

# The committed configuration the renderer falls back to, which is what "the
# variable is absent" has to resolve to. It is also a member of the installed
# artifact set above, so one file is both the default probe set and a shipped
# file — asserted from both ends.
_ENDPOINTS_FILE = "factory-reach-endpoints.env"

# The role's pattern as the defaults commit it, so the cases below exercise the
# COMMITTED regex rather than a copy of it. Single-quoted in YAML because the
# shape carries a backslash class (`\S`), which a double-quoted scalar would
# eat.
_PATTERN_LINE = re.compile(rf"^{_ENDPOINT_PATTERN_VAR}: '(?P<pattern>.+)'$", re.MULTILINE)

# One well-formed entry — the shape the host-captured leg passes — and the
# malformed spellings an operator actually types. Each must be refused on the
# CONTROLLER, before a Job exists: the renderer would refuse them too, but only
# after being invoked once per covered node, and three identical exit-2 runs
# read like a cluster fault rather than like the `-e` that is wrong.
_WELL_FORMED_ENTRY = "telemetry-receiver=100.89.189.118:35129"
_MALFORMED_ENTRIES = (
    "telemetry-receiver",
    "telemetry-receiver=100.89.189.118",
    "telemetry-receiver=100.89.189.118:",
    "telemetry-receiver=100.89.189.118:port",
    "telemetry-receiver=:35129",
    "Telemetry-Receiver=100.89.189.118:35129",
    "telemetry receiver=100.89.189.118:35129",
    "100.89.189.118:35129",
)


def _play_text() -> str:
    """The committed `ci-pool.yml`, as Ansible receives it."""
    return _PLAY.read_text(encoding="utf-8")


def _role_order() -> list[str]:
    """Every `roles:` entry of the play, in play order."""
    return [match["role"] for match in _ROLE_ENTRY.finditer(_play_text())]


def _role_gates() -> dict[str, str | None]:
    """Every `roles:` entry of the play, as `role -> gate-or-None`.

    A mapping rather than a per-role search, so a role the play does not
    declare at all is answered by the membership assertion that NAMES it
    instead of by a lookup arm nothing ever reaches.
    """
    return {
        match["role"]: (gate["expression"].strip() if gate else None)
        for match in _ROLE_ENTRY.finditer(_play_text())
        for gate in [_WHEN_LINE.search(match["body"])]
    }


def _tasks_text() -> str:
    """The committed role's task file."""
    assert _ROLE_TASKS.is_file(), (
        f"{_ROLE_TASKS.relative_to(_REPO_ROOT)} must be committed: R70 requires the reach "
        f"check to be a converge artifact, and an artifact no play installs is one the node "
        f"can only get by an operator exporting a tree and running it under sudo — which is "
        f"the thing the GitOps discipline forbids and the ruling rejected"
    )
    return _ROLE_TASKS.read_text(encoding="utf-8")


def _defaults_text() -> str:
    """The committed role's defaults."""
    assert _ROLE_DEFAULTS.is_file(), (
        f"{_ROLE_DEFAULTS.relative_to(_REPO_ROOT)} must be committed: the installed paths, "
        f"the credential and the consent variable are POOL FACTS a host may redirect, and a "
        f"value spelled inline in a task is one no host can redirect and no test can read"
    )
    return _ROLE_DEFAULTS.read_text(encoding="utf-8")


def _committed_endpoint_pattern() -> re.Pattern[str]:
    """The role's committed entry-shape pattern, compiled as Ansible's `match` applies it.

    `re.match` and not `re.fullmatch`, because the `match` TEST the role's
    `reject('match', ...)` uses anchors at the START only — so the committed
    pattern has to carry its own `$`, and a reader that anchored the end itself
    would pass a pattern that admits trailing junk.
    """
    found = _PATTERN_LINE.search(_defaults_text())
    assert found is not None, (
        f"the role's defaults must commit `{_ENDPOINT_PATTERN_VAR}: '<regex>'` as a "
        f"single-quoted scalar: the shape every override entry must match is a POOL FACT a "
        f"reader has to be able to exercise, and a pattern spelled inline in the assert's "
        f"`that:` is one no test can reach;\ndefaults={_defaults_text()!r}"
    )
    return re.compile(found["pattern"])


def _run_task_text() -> str:
    """The role's run task, from its module key to the credential it names.

    Sliced rather than parsed because no YAML library is importable here. The
    slice is what lets "the override reaches the RENDERER'S argv" be asserted
    as something other than "the variable is mentioned somewhere in the file".

    Anchored on the MODULE KEY and not on the script's filename: the role names
    that script in prose too, and an index over prose would make the ordering
    assertion below a fact about where a comment sits. `_RUN_MODULE` is the one
    task in this role that executes anything, which is exactly the boundary
    "before anything is submitted" is about.
    """
    tasks = _tasks_text()
    start = tasks.index(_RUN_MODULE)
    return tasks[start : tasks.index("KUBECONFIG", start)]


def _factory_nodes_from_profiles() -> set[str]:
    """Every pool node whose committed profile declares `FACTORY_NODE=true`."""
    return {
        profile.stem
        for profile in sorted(_PROFILES.glob("*.env"))
        if re.search(r"^FACTORY_NODE=true$", profile.read_text(encoding="utf-8"), re.MULTILINE)
    }


# --- the Definition of Done's first assertion: the install -------------------


def test_the_play_reaches_the_role_on_the_control_plane_node_only() -> None:
    """`ci-pool.yml` runs the role, gated to the server, right after the converge.

    Gated on `cluster_role` and NOT on `FACTORY_NODE`: the three files are
    installed on the node that RUNS the check, and the check reaches every
    covered node from there through the API server. An agent gets nothing from
    a copy of a renderer it has no credential to submit with.

    Ordered after `ci_converge_unit` because that role is what renders the
    scoped credential's source and installs the rest of the tree, so ONE apply
    carrying both run-now switches converges and then proves, in that order.
    """
    order = _role_order()
    assert _ROLE_NAME in order, (
        f"{_PLAY.name} must declare `- role: {_ROLE_NAME}`; the play's role list is "
        f"{order}. A proof no committed play installs is not a converge artifact"
    )
    assert _role_gates().get(_ROLE_NAME) == "cluster_role == 'server'", (
        f"the `{_ROLE_NAME}` entry must be gated `cluster_role == 'server'`; got "
        f"{_role_gates().get(_ROLE_NAME)!r}. The control-plane node is the one that holds a "
        f"credential to submit with, and the one the run-now apply can be driven from"
    )
    assert order.index(_ROLE_NAME) > order.index("ci_converge_unit"), (
        f"`{_ROLE_NAME}` must follow `ci_converge_unit` in the play's order; got {order}. "
        f"The converge renders the scoped credential this run authenticates with, so one "
        f"apply passing both run-now switches has to converge BEFORE it proves"
    )


def test_the_role_installs_every_shipped_file_into_the_converges_installed_tree() -> None:
    """All four shipped files, named with a mode, into `<lib>/factory`.

    The three the Definition of Done names plus the image pin they are useless
    without: the renderer resolves the probe and both configuration files
    relative to its OWN directory, so a partial install is a check that refuses
    at its first resolution.
    """
    tasks = _tasks_text()
    defaults = _defaults_text()
    assert _INSTALL_DIR in defaults or _LIB_DIR in defaults, (
        f"the role must install into the converge's own tree ({_INSTALL_DIR}); its defaults "
        f"name neither {_INSTALL_DIR!r} nor {_LIB_DIR!r}.\ndefaults={defaults!r}"
    )
    for name in _SHIPPED:
        assert (_FACTORY_DIR / name).is_file(), (
            f"{(_FACTORY_DIR / name).relative_to(_REPO_ROOT)} must be committed — the role "
            f"installs the repository's copy, so a file the repository lacks is a file no "
            f"node can get"
        )
        assert name in defaults, (
            f"the role must name `{name}` in its installed file set, so the install travels "
            f"with no edit to a task body;\ndefaults={defaults!r}"
        )
    assert "ansible.builtin.copy" in tasks, (
        f"the role must COPY the shipped files out of this repository rather than render or "
        f"fetch them — the repository stays the source of truth and this role is the refresh "
        f"step, exactly as `ci_converge_unit` is for the rest of the tree;\ntasks={tasks!r}"
    )
    assert "state: directory" in tasks, (
        f"the role must create its install directory itself: `--check` cannot see past a "
        f"missing parent, so an unguarded copy reports a would-be change and fails only on "
        f"a real apply;\ntasks={tasks!r}"
    )


# --- the Definition of Done's first assertion: the consent gate --------------


def test_the_check_runs_only_when_the_run_now_variable_is_passed() -> None:
    """Install by default; run on ONE apply, and never under `--check`.

    The `ci_converge_unit_run_now` pattern, for the same reason: the run submits
    a Job into the live `factory` namespace, taking a ResourceQuota slot on a
    node that shares its box with the CI pool. A drift report has no dry form of
    submitting a Job, so the gate names `ansible_check_mode` too.
    """
    defaults = _defaults_text()
    tasks = _tasks_text()
    assert f"{_RUN_NOW}: false" in defaults, (
        f"`{_RUN_NOW}` must default to `false` in the role's defaults, so a ROUTINE apply "
        f"installs and does not run;\ndefaults={defaults!r}"
    )
    assert f"{_RUN_NOW} | bool" in tasks, (
        f"the run must be gated on `{_RUN_NOW} | bool` — the consent pattern "
        f"`ci_converge_unit` already uses;\ntasks={tasks!r}"
    )
    assert "not ansible_check_mode" in tasks, (
        f"and on `not ansible_check_mode`: there is no dry form of submitting a Job, so a "
        f"drift report must show these tasks skipped whatever the switch says;\n"
        f"tasks={tasks!r}"
    )
    gate_index = tasks.index(f"{_RUN_NOW} | bool")
    run_index = tasks.index("verify-factory-reach.sh")
    assert gate_index < run_index, (
        f"the consent gate must come BEFORE the task that runs the check, so the run is "
        f"inside the gated block rather than beside it;\ntasks={tasks!r}"
    )


# --- the Definition of Done's first assertion: the scoped credential ---------


def test_the_run_authenticates_as_sandbox_launcher_and_never_as_cluster_admin() -> None:
    """`KUBECONFIG` is the factory namespace's scoped credential, full stop.

    The grant reaches jobs and pods in ONE namespace. The admin kubeconfig on
    the same node reaches the cluster, and it is root-readable, so an apply
    running as root would pick it up by default — which is why the credential is
    named in the run task's `environment:` rather than left to whatever root's
    environment happens to hold.
    """
    tasks = _tasks_text()
    defaults = _defaults_text()
    assert f"factory_reach_check_kubeconfig: {_SCOPED_KUBECONFIG}" in defaults, (
        f"the role's defaults must name the scoped credential as "
        f"`factory_reach_check_kubeconfig: {_SCOPED_KUBECONFIG}` — the file converge step "
        f"10e renders on this node at every boot;\ndefaults={defaults!r}"
    )
    assert 'KUBECONFIG: "{{ factory_reach_check_kubeconfig }}"' in tasks, (
        f"the run task must set `KUBECONFIG` from that variable in its own `environment:`, "
        f"so the credential is a property of the TASK and not of whatever root's shell "
        f"carries;\ntasks={tasks!r}"
    )
    for path in (_ROLE_TASKS, _ROLE_DEFAULTS):
        body = path.read_text(encoding="utf-8")
        assert _ADMIN_KUBECONFIG not in body, (
            f"{path.relative_to(_REPO_ROOT)} must NOT name the admin kubeconfig "
            f"{_ADMIN_KUBECONFIG}. R70 rejected the admin-credential run: this check must "
            f"prove what the sandbox backend's own identity can do, and a proof taken as "
            f"cluster admin proves the reach of a credential no factory pod holds;\n"
            f"{body!r}"
        )


def test_the_run_refuses_rather_than_falling_back_when_the_credential_is_absent() -> None:
    """A missing scoped credential stops the run; it never degrades to admin.

    The control-plane node's k3s datastore is a tmpfs, so the ServiceAccount and
    its token Secret are recreated at every boot and the rendered file can
    genuinely be absent. Absent, the honest move is to refuse and name the
    converge that renders it — the fallback the role must never grow is the one
    the ruling rejected.
    """
    tasks = _tasks_text()
    assert "ansible.builtin.stat" in tasks and "factory_reach_check_credential" in tasks, (
        f"the role must READ whether the scoped credential is in place, registering the "
        f"result, before it runs anything;\ntasks={tasks!r}"
    )
    assert "factory_reach_check_credential.stat.exists" in tasks, (
        f"and ASSERT on that read, so an absent credential refuses rather than reaching the "
        f"command and failing as an authentication error that reads like a cluster "
        f"problem;\ntasks={tasks!r}"
    )


# --- the run-time endpoint override (livespec-dev-tooling-5iep7h, R78) -------


def test_the_role_forwards_each_endpoint_override_entry_as_an_endpoint_argument() -> None:
    """One `--endpoint NAME=HOST:PORT` per entry; the committed file when there are none.

    THE RENDERER'S OWN OVERRIDE SURFACE, not a second one beside it. The script
    already accepts `--endpoint` and already lets a repeated NAME replace a
    committed entry's target, so forwarding is all this role owes — and the
    committed `factory-reach-endpoints.env` it installs stays the default,
    because the empty variable produces no argument at all and the renderer
    resolves that file relative to its own directory.

    Why the override exists: the committed `telemetry-receiver` port is the
    dispatcher's EPHEMERAL per-dispatch port recorded on 2026-10-13, so a
    run-now apply against it proves nothing about a receiver that exists now.
    R78 requires the live receiver to be suppliable at run time.
    """
    defaults = _defaults_text()
    tasks = _tasks_text()
    assert f"{_ENDPOINTS_VAR}: []" in defaults, (
        f"`{_ENDPOINTS_VAR}` must default to the EMPTY list, which is what makes the "
        f"committed {_ENDPOINTS_FILE} the default probe set and the variable an override;\n"
        f"defaults={defaults!r}"
    )
    assert _ENDPOINTS_FILE in defaults, (
        f"and that same {_ENDPOINTS_FILE} must stay a member of the installed artifact set: "
        f"the default it falls back to is a file the role has to put on the node;\n"
        f"defaults={defaults!r}"
    )
    assert f"{_ENDPOINT_ARGV_VAR}: []" in tasks, (
        f"the role must start each host from NO override arguments: an accumulator that "
        f"defaulted at its point of use would carry a previous play's entries into this "
        f"run, and forwarding an endpoint nobody passed is the defect the committed-default "
        f"half of this assertion forbids;\ntasks={tasks!r}"
    )
    assert f"{_ENDPOINT_ARGV_VAR} + ['--endpoint', item]" in tasks, (
        f"each entry must become the PAIR `--endpoint <entry>` — the renderer's own flag "
        f"and its value — rather than a joined string or a `--endpoints` file the role "
        f"writes;\ntasks={tasks!r}"
    )
    assert f'loop: "{{{{ {_ENDPOINTS_VAR} }}}}"' in tasks, (
        f"EACH entry, which means a loop over `{_ENDPOINTS_VAR}` itself: a step that read "
        f"only its first element would silently probe one endpoint of a set the operator "
        f"passed several of;\ntasks={tasks!r}"
    )
    assert _ENDPOINT_ARGV_VAR in _run_task_text(), (
        f"and the translated arguments must reach the RENDERER'S argv, in the task that "
        f"runs verify-factory-reach.sh — a fact built and never passed is an override the "
        f"apply reports as applied and never applies;\nrun task={_run_task_text()!r}"
    )
    assert "--endpoints" not in tasks, (
        f"the role must never pass `--endpoints FILE`: redirecting the whole file would "
        f"take the committed default out of the run, and the Definition of Done asks for "
        f"per-ENTRY override with that file as the default;\ntasks={tasks!r}"
    )


def test_the_role_refuses_a_malformed_endpoint_override_before_submitting_any_job() -> None:
    """The committed shape, exercised; and the refusal sits BEFORE the run task.

    Validated on the CONTROLLER rather than left to the renderer. The renderer
    does refuse a malformed `--endpoint` with exit 2 and submits nothing — but
    only after being invoked once per covered node, and an apply printing three
    identical configuration errors reads like a cluster fault rather than like
    the one `-e` that is wrong.
    """
    tasks = _tasks_text()
    pattern = _committed_endpoint_pattern()
    assert pattern.match(_WELL_FORMED_ENTRY) is not None, (
        f"the committed pattern {pattern.pattern!r} must ADMIT `{_WELL_FORMED_ENTRY}`: a "
        f"shape check that rejects the entry the host-captured leg passes refuses every "
        f"run instead of the malformed ones"
    )
    for malformed in _MALFORMED_ENTRIES:
        assert pattern.match(malformed) is None, (
            f"the committed pattern {pattern.pattern!r} must REFUSE `{malformed}`: the "
            f"renderer requires NAME=HOST:PORT with a lowercase `[a-z0-9-]` name and a "
            f"numeric port, and an entry it would reject must never reach it"
        )
    assert f"{_ENDPOINTS_VAR} | reject('match', {_ENDPOINT_PATTERN_VAR})" in tasks, (
        f"the role must ASSERT that no entry fails that pattern — `reject('match', ...)` "
        f"over `{_ENDPOINTS_VAR}`, so the refusal names the shape rather than a count;\n"
        f"tasks={tasks!r}"
    )
    assert tasks.index(_ENDPOINT_PATTERN_VAR) < tasks.index(_RUN_MODULE), (
        f"and that assert must come BEFORE `{_RUN_MODULE}`, the one task in this role that "
        f"executes anything: NOTHING may be submitted on a malformed override, and a "
        f"validation after the run is a Job already in the live factory namespace;\n"
        f"tasks={tasks!r}"
    )


# --- the covered node set, and the verdict the apply surfaces ----------------


def test_the_default_run_covers_every_factory_node_and_the_variable_can_narrow_it() -> None:
    """The node set is the profiles' `FACTORY_NODE=true`, or the names passed in.

    Read from each node's own committed profile with the same `lookup` +
    `regex_findall | first | default()` chain every role in this tree reads a
    profile with, so the covered set is the same fact `node_labels` renders the
    factory label from rather than a second list to keep in step.
    """
    tasks = _tasks_text()
    defaults = _defaults_text()
    assert "factory_reach_check_nodes: []" in defaults, (
        f"`factory_reach_check_nodes` must default to the EMPTY list, which is what makes "
        f"the profile-derived set the default and the variable a narrowing override;\n"
        f"defaults={defaults!r}"
    )
    assert "FACTORY_NODE=(.*)$" in tasks, (
        f"the role must read each node's posture from its committed profile's FACTORY_NODE "
        f"key, with this tree's standard `regex_findall | first | default()` chain;\n"
        f"tasks={tasks!r}"
    )
    covered = _factory_nodes_from_profiles()
    for node in _HOST_CAPTURED_NODES:
        assert node in covered, (
            f"{node} must declare FACTORY_NODE=true in its committed profile — the "
            f"Definition of Done's host-captured leg reports the check's verdict for it, and "
            f"the default run covers exactly the profile-declared factory nodes; "
            f"covered={sorted(covered)}"
        )


def test_the_apply_surfaces_each_nodes_exit_code_and_the_named_endpoint() -> None:
    """Per-node verdict in the play output, and a non-zero one fails the apply.

    An apply that ran the check and reported only `failed=0` would hide exactly
    the measurement it was run to take. The report names the exit code and the
    probe's own verdict lines, so the operator reads WHICH endpoint refused
    rather than being told to go find the Job.
    """
    tasks = _tasks_text()
    assert (
        "ansible.builtin.debug" in tasks
    ), f"the role must REPORT each node's verdict in the play output;\ntasks={tasks!r}"
    assert ".rc" in tasks, (
        f"the report must name each run's EXIT CODE: it is the verdict, and the script's "
        f"three codes mean different things (reached / refused / misconfigured);\n"
        f"tasks={tasks!r}"
    )
    assert "UNREACHABLE" in tasks, (
        f"and the probe's own `UNREACHABLE <name> at <host>:<port>` line, which is where the "
        f"NAME of the endpoint that refused lives;\ntasks={tasks!r}"
    )
    assert "ansible.builtin.assert" in tasks and "failed_when: false" in tasks, (
        f"the command must not fail the play by itself (`failed_when: false`) — the verdict "
        f"is read and reported first — and an ASSERT must then refuse any non-zero run, so "
        f"a reported failure cannot be mistaken for a completed apply;\ntasks={tasks!r}"
    )
