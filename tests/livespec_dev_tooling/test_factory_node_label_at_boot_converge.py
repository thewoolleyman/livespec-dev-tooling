"""The FACTORY label is reconciled at BOOT, not only on a `ci-pool.yml` apply.

THE DEFECT THIS FILE EXISTS FOR (work-item `livespec-dev-tooling-izlx4g`). k3s
applies `--node-label` at node REGISTRATION only, and the k3s datastore on
`poweredge-xubuntu` is a tmpfs (`phase2/datastore-tmpfs/`), so every Node object
is RE-CREATED when its node re-registers after a control-plane reboot, carrying
only what that node's own kubelet was started with. Measured live 2026-10-16:
the reboot went in at ~16:55Z, the boot converge reported `Result=success` at
16:57Z, and once all three nodes were Ready
`kubectl get nodes -L ci-runner.io/factory` showed the label on `hp-xubuntu`
ALONE. `gmktec-xubuntu` and `poweredge-xubuntu` had re-registered without it,
because their label was set AFTERWARDS by `ansible/roles/node_labels`, which
reconciles only on an apply. Until an operator ran one, the
kubernetes-sandbox-backend plugin's `ci-runner.io/factory=true` selector matched
one node of three. Nothing errored — a selector that matches fewer nodes than it
should simply schedules less.

WHY THE SCRIPT IS RUN RATHER THAN READ. The claim is a claim about CONTROL FLOW:
read every committed profile, wait for a node that has not re-registered yet,
assert the label on exactly the nodes their profiles declare, and take it off the
ones they do not. Reading a shell script cannot establish that. So the shipped
`reconstruct/converge-factory-node-labels.sh` runs with `kubectl` and `sleep`
faked on a scratch PATH: no cluster is reached and every path it writes stays
inside `tmp_path`. It is the technique
`test_node_status_credential_pull_on_rejection.py` uses for the churn-slot patch
script.

The cluster-side half is asserted by reading the two committed files that put it
on the boot path — the boot converge that calls the script, and the
`ci_converge_unit` role that installs the script and every pool profile onto a
host with no checkout. A reconcile the boot converge never reaches, or one whose
profiles are not on the host, is exactly the apply-only mechanism this item
replaces.

Plan: livespec `factory-worker-nodes-gitops`, epic `livespec-sqvj7p`.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ANSIBLE = _REPO_ROOT / "ansible"
_INVENTORY = _ANSIBLE / "inventory" / "legacy.yml"
_PHASE2 = _REPO_ROOT / "ci-runner" / "k3s" / "phase2"
_PROFILES = _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal" / "profiles"
_RECONSTRUCT = _PHASE2 / "reconstruct"
_BOOT_CONVERGE = _RECONSTRUCT / "converge-ci-stack.sh"
_LABEL_CONVERGE = _RECONSTRUCT / "converge-factory-node-labels.sh"
_ROLE = _ANSIBLE / "roles" / "ci_converge_unit"
_ROLE_DEFAULTS = _ROLE / "defaults" / "main.yml"
_ROLE_TASKS = _ROLE / "tasks" / "main.yml"

# The label, spelled as the two parts kubectl needs separately: `key=value` to
# set and a bare `key-` to remove. The same pair
# `ansible/roles/node_labels/defaults/main.yml` composes, and the same pair
# `ci-runner/k3s/provision-k3s.sh` registers at join time.
_LABEL_KEY = "ci-runner.io/factory"
_LABEL_VALUE = "true"
_LABEL = f"{_LABEL_KEY}={_LABEL_VALUE}"
# The directory the script reads on the HOST, where `ci_converge_unit` installs
# the pool's profiles. A subdirectory and not the flat lib dir on purpose:
# `node_extended_resource` already installs THIS node's own profile as
# `<lib-dir>/<node>.env`, and one file may have one owner.
_INSTALLED_PROFILES_SUBDIR = "profiles"

# The inventory readers, the same shape
# `test_ci_pool_factory_only_agent_roles.py` uses: `ci_pool` membership is a
# fact of the committed inventory, and this suite cannot import Ansible (the
# repository's Python floor is below ansible-core's).
_CI_POOL_BLOCK = re.compile(
    r"^        ci_pool:\n          hosts:\n(?P<body>(?:.*\n)*?)^        \S", re.MULTILINE
)
_INVENTORY_HOST = re.compile(r"^            (?P<host>[\w-]+):$", re.MULTILINE)

# `kubectl`, faked. Logs its argv, then answers the three reads the converge
# makes from environment-supplied state: the per-node registration probe, the
# label SELECTOR (the question the label exists to answer), and the `-L` verify
# column. `label` always succeeds — what this suite scripts is which labels are
# asked for, not whether the API server accepts them.
#
# LATE_NODE/LATE_PROBES script a node that has not re-registered yet: its first
# LATE_PROBES probes answer kubectl's exact NotFound, and it is registered after
# that. That is the live post-reboot shape — the control plane comes back first
# and its agents re-register behind it.
_KUBECTL_SHIM = """\
printf 'kubectl %s\\n' "$*" >> "$ARGV_LOG"
if [ "$1" = "label" ]; then exit 0; fi
if [ "$1" = "get" ] && [ "$2" = "node" ]; then
  node="$3"
  if [ -n "${LATE_NODE:-}" ] && [ "$node" = "$LATE_NODE" ]; then
    printf 'x' >> "$LATE_PROBE_LOG"
    seen="$(wc -c < "$LATE_PROBE_LOG" | tr -d ' ')"
    if [ "$seen" -le "${LATE_PROBES:-0}" ]; then
      printf 'Error from server (NotFound): nodes "%s" not found\\n' "$node" >&2
      exit 1
    fi
  fi
  case " ${REGISTERED:-} " in
    *" $node "*) printf 'node/%s\\n' "$node"; exit 0 ;;
  esac
  printf 'Error from server (NotFound): nodes "%s" not found\\n' "$node" >&2
  exit 1
fi
if [ "$1" = "get" ] && [ "$2" = "nodes" ]; then
  case " $* " in
    *" -l "*) for n in ${LABELLED:-}; do printf 'node/%s\\n' "$n"; done ;;
  esac
  exit 0
fi
exit 0
"""
# `sleep`: logged and shortened, so the bounded registration wait costs almost
# no wall clock. What the wait DECIDES is under test; its duration is not.
_SLEEP_SHIM = 'printf \'sleep %s\\n\' "$*" >> "$ARGV_LOG"\nexec /bin/sleep 0.05\n'


def _ci_pool_hosts() -> tuple[str, ...]:
    """Every `ci_pool` host, from the committed inventory."""
    block = _CI_POOL_BLOCK.search(_INVENTORY.read_text(encoding="utf-8"))
    assert block is not None, (
        f"{_INVENTORY.name} must declare a `ci_pool` group with a `hosts:` mapping — it is the "
        "group whose nodes carry the factory posture, and a group this reader cannot find is a "
        "set of nodes nothing here checks"
    )
    hosts = tuple(match["host"] for match in _INVENTORY_HOST.finditer(block["body"]))
    assert hosts, f"{_INVENTORY.name} declares a `ci_pool` group with no hosts"
    return hosts


def _profile_value(*, host: str, key: str) -> str:
    """One scalar out of a committed profile, read as every role reads it.

    `regex_findall(...) | first`, which is the expression
    `ansible/roles/node_labels`, `node_taints` and `k3s_config` all use on this
    same directory: the FIRST occurrence, never the last, so this reader and the
    roles cannot disagree about what a profile said.
    """
    profile = _PROFILES / f"{host}.env"
    assert profile.is_file(), (
        f"{profile.relative_to(_REPO_ROOT)} must be committed: every ci_pool node's posture is a "
        "fact of its own phase0 profile, so a node without one has no declared factory posture"
    )
    found = re.findall(
        rf"^{re.escape(key)}=(.*)$", profile.read_text(encoding="utf-8"), re.MULTILINE
    )
    return found[0].strip() if found else ""


def _declared_factory_nodes() -> tuple[str, ...]:
    """Every `ci_pool` node whose committed profile declares `FACTORY_NODE=true`.

    Derived from the inventory and the profiles rather than written down here:
    the Definition of Done is a claim about "each ci_pool node whose profile
    sets FACTORY_NODE=true", so a node added to the pool as a factory node has
    to arrive in this set with no edit to this file.
    """
    nodes = tuple(
        host for host in _ci_pool_hosts() if _profile_value(host=host, key="FACTORY_NODE") == "true"
    )
    assert nodes, (
        "no ci_pool node's committed profile declares FACTORY_NODE=true, so every assertion "
        "below would pass over an empty set — the vacuous green this item's whole point is to "
        "make impossible"
    )
    return nodes


def _shim(*, bin_dir: Path, name: str, body: str) -> None:
    """One executable on the scratch PATH, standing in for a host tool."""
    path = bin_dir / name
    _ = path.write_text(f"#!/usr/bin/env bash\n{body}", encoding="utf-8")
    path.chmod(0o755)


def _run_converge(
    *,
    tmp_path: Path,
    profiles_dir: Path,
    registered: tuple[str, ...],
    labelled: tuple[str, ...] = (),
    late_node: str = "",
    late_probes: int = 0,
    wait_seconds: int = 3,
) -> tuple[int, str, list[str]]:
    """Run the shipped label converge against a faked cluster; return code, output, argv."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "argv.log"
    kubeconfig = tmp_path / "kubeconfig"
    _ = kubeconfig.write_text("apiVersion: v1\nkind: Config\n", encoding="utf-8")
    _shim(bin_dir=bin_dir, name="kubectl", body=_KUBECTL_SHIM)
    _shim(bin_dir=bin_dir, name="sleep", body=_SLEEP_SHIM)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(
        {
            "ARGV_LOG": str(log),
            "LATE_PROBE_LOG": str(tmp_path / "late-probes"),
            "REGISTERED": " ".join(registered),
            "LABELLED": " ".join(labelled),
            "LATE_NODE": late_node,
            "LATE_PROBES": str(late_probes),
            "KUBECONFIG": str(kubeconfig),
            "CI_FACTORY_LABEL_PROFILES_DIR": str(profiles_dir),
            # Bounded short: the wait's duration is not under test, and the one
            # case that reaches the deadline must not hold the suite for the
            # live default of two minutes.
            "CI_FACTORY_LABEL_WAIT_SECONDS": str(wait_seconds),
            "CI_FACTORY_LABEL_POLL_SECONDS": "1",
        }
    )
    completed = subprocess.run(
        ["bash", str(_LABEL_CONVERGE)],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    invoked = log.read_text(encoding="utf-8").splitlines() if log.is_file() else []
    return completed.returncode, completed.stdout + completed.stderr, invoked


def _labels_set(*, invoked: list[str]) -> tuple[str, ...]:
    """Every node the run ASSERTED the factory label on, in call order."""
    return tuple(
        match["node"]
        for line in invoked
        for match in [
            re.fullmatch(rf"kubectl label --overwrite node (?P<node>\S+) {re.escape(_LABEL)}", line)
        ]
        if match is not None
    )


def _labels_removed(*, invoked: list[str]) -> tuple[str, ...]:
    """Every node the run REMOVED the factory label from, in call order."""
    return tuple(
        match["node"]
        for line in invoked
        for match in [
            re.fullmatch(rf"kubectl label node (?P<node>\S+) {re.escape(_LABEL_KEY)}-", line)
        ]
        if match is not None
    )


def _scratch_profiles(*, tmp_path: Path, declared: dict[str, str]) -> Path:
    """A profiles directory in the committed shape, for the control arms.

    Written in the committed profiles' own `KEY=value` shape rather than copied
    and edited, because what these arms vary is a POSTURE the committed profiles
    deliberately do not hold: every pool node is a factory node today, so the
    retirement and the typo have no committed instance to read.
    """
    directory = tmp_path / "profiles"
    directory.mkdir()
    for node, factory in declared.items():
        body = f"NODE_NAME={node}\nCLUSTER_ROLE=agent\n"
        if factory:
            body += f"FACTORY_NODE={factory}\n"
        _ = (directory / f"{node}.env").write_text(body, encoding="utf-8")
    return directory


def test_bash_is_available_to_run_the_shipped_converge() -> None:
    """The lens this suite reads the script through, named rather than assumed."""
    assert shutil.which("bash") is not None


def test_every_declared_factory_node_is_labelled_by_the_boot_path_converge(
    *, tmp_path: Path
) -> None:
    """The Definition of Done, run: every `FACTORY_NODE=true` pool node, labelled.

    Against the REAL committed profiles — the ones the `ci_converge_unit` role
    installs onto the host — with every node registered, which is the state the
    live reboot reached at 16:57Z while two of the three nodes carried no label.
    The asserted set is EQUALITY, not containment: a converge that labelled a
    node its profile does not declare would be a mechanism deciding the factory
    posture for itself.
    """
    assert _LABEL_CONVERGE.is_file(), (
        f"{_LABEL_CONVERGE.relative_to(_REPO_ROOT)} does not exist, so the factory label is "
        "reconciled only by a `ci-pool.yml` apply and is lost on every control-plane reboot"
    )
    declared = _declared_factory_nodes()

    code, output, invoked = _run_converge(
        tmp_path=tmp_path, profiles_dir=_PROFILES, registered=declared
    )

    assert code == 0, f"the converge failed against a fully registered pool:\n{output}"
    assert sorted(_labels_set(invoked=invoked)) == sorted(declared), (
        "the boot-path converge must assert the factory label on EXACTLY the ci_pool nodes whose "
        f"committed profile declares FACTORY_NODE=true ({sorted(declared)}); it labelled "
        f"{sorted(_labels_set(invoked=invoked))}"
    )
    assert not _labels_removed(invoked=invoked), (
        "the converge removed the factory label from a node whose profile declares it — the one "
        "mutation that would make a reboot WORSE than the defect it repairs"
    )


def test_a_node_that_has_not_re_registered_yet_is_waited_for_and_then_labelled(
    *, tmp_path: Path
) -> None:
    """The live post-reboot shape: the control plane is back, its agents are not yet.

    The boot converge runs on the server the moment k3s is up, and an agent
    re-registers against the re-created datastore some seconds later. A
    reconcile that read "not registered" as "nothing to do" would reproduce the
    defect for exactly the nodes that lost the label — the agents — so the wait
    is the load-bearing half, and this arm is the only one that proves it.
    """
    declared = _declared_factory_nodes()
    late = declared[-1]

    code, output, invoked = _run_converge(
        tmp_path=tmp_path,
        profiles_dir=_PROFILES,
        registered=declared,
        late_node=late,
        late_probes=2,
    )

    assert code == 0, f"a late re-registration must not fail the converge:\n{output}"
    assert sorted(_labels_set(invoked=invoked)) == sorted(declared), (
        f"{late} re-registered two probes after the converge asked for it and was NOT labelled; "
        f"labelled {sorted(_labels_set(invoked=invoked))} of {sorted(declared)}"
    )
    assert any(line.startswith("sleep ") for line in invoked), (
        "the converge never slept, so its registration wait is not a wait — it would race every "
        "agent that re-registers behind the control plane"
    )


def test_a_node_that_never_registers_is_reported_and_fails_the_step(*, tmp_path: Path) -> None:
    """The control arm: an absent node is a WARN and a non-zero exit, never a silent pass.

    The caller in `converge-ci-stack.sh` turns that non-zero into a WARN and
    carries on building the cluster stack, which is the right trade — a missing
    factory label costs factory dispatch, not CI — but the step itself must say
    so, because the whole cost of this defect was that nothing said anything.
    """
    declared = _declared_factory_nodes()
    present = declared[:-1]
    absent = declared[-1]

    code, output, invoked = _run_converge(
        tmp_path=tmp_path, profiles_dir=_PROFILES, registered=present, wait_seconds=2
    )

    assert code != 0, f"an unreconciled factory node must fail the step:\n{output}"
    assert absent in output, f"the output never names the node it could not label:\n{output}"
    assert absent not in _labels_set(invoked=invoked), (
        f"the converge labelled {absent}, which never registered — a label applied to a Node "
        "object that does not exist is an error the converge must not have reached"
    )
    assert sorted(_labels_set(invoked=invoked)) == sorted(present), (
        "one unregistered node must not cost the others their label; labelled "
        f"{sorted(_labels_set(invoked=invoked))} of {sorted(present)}"
    )


def test_a_profile_that_retires_the_factory_posture_has_the_label_removed(
    *, tmp_path: Path
) -> None:
    """The removal half, and why it is not optional.

    `ci-runner/k3s/provision-k3s.sh` puts `--node-label ci-runner.io/factory=true`
    into a factory node's install command, so a node retired from the pool by a
    profile edit carries the label AGAIN at its next registration. A converge
    that only ever added would make that edit un-takeable: the operator would
    remove the label, the next reboot would put it back, and the selector would
    keep scheduling onto a node nobody declared.
    """
    profiles = _scratch_profiles(
        tmp_path=tmp_path, declared={"keeps-it": "true", "retired": "false"}
    )

    code, output, invoked = _run_converge(
        tmp_path=tmp_path,
        profiles_dir=profiles,
        registered=("keeps-it", "retired"),
        labelled=("keeps-it", "retired"),
    )

    assert code == 0, f"the converge failed on a retired node:\n{output}"
    assert _labels_removed(invoked=invoked) == ("retired",), (
        "the converge must take the factory label OFF a node whose profile declares "
        f"FACTORY_NODE=false; it removed {_labels_removed(invoked=invoked)}"
    )
    assert _labels_set(invoked=invoked) == ("keeps-it",), (
        f"the converge asserted the label on {_labels_set(invoked=invoked)}; only the node whose "
        "profile declares it may be labelled"
    )


def test_a_profile_whose_factory_node_is_neither_true_nor_false_is_skipped_not_unlabelled(
    *, tmp_path: Path
) -> None:
    """The enum guard, as `ansible/roles/node_labels` asserts it and for its reason.

    This script does not go through `phase0-bare-metal/profile.sh` — it reads
    the one line it needs — so the enum is re-asserted here rather than assumed.
    Without it a typo reads as "not true" and silently REMOVES a live factory
    label, which is a worse outcome than the defect: the selector would lose a
    node that was working.
    """
    profiles = _scratch_profiles(tmp_path=tmp_path, declared={"typo": "ture", "sound": "true"})

    code, output, invoked = _run_converge(
        tmp_path=tmp_path,
        profiles_dir=profiles,
        registered=("typo", "sound"),
        labelled=("typo", "sound"),
    )

    assert code != 0, f"a profile this converge cannot read must not report success:\n{output}"
    assert "typo" not in _labels_removed(invoked=invoked), (
        "the converge removed a live factory label because the profile's FACTORY_NODE was a "
        "typo; an unreadable posture is a refusal, never a retirement"
    )
    assert _labels_set(invoked=invoked) == ("sound",), (
        f"one unreadable profile must not cost a sound one its label; labelled "
        f"{_labels_set(invoked=invoked)}"
    )


def test_a_profile_with_no_factory_node_key_is_the_parsers_own_default(*, tmp_path: Path) -> None:
    """A profile predating the key is a no-op, not an error.

    `phase0-bare-metal/profile.sh` defaults `FACTORY_NODE` to `false`, and
    `ansible/roles/node_labels` reads the same default, so a profile written
    before the key existed declares no factory posture. It must neither be
    labelled nor refused — and if it somehow carries the label, the declared
    `false` takes it off, exactly as a written `FACTORY_NODE=false` would.
    """
    profiles = _scratch_profiles(tmp_path=tmp_path, declared={"predates-the-key": ""})

    code, output, invoked = _run_converge(
        tmp_path=tmp_path,
        profiles_dir=profiles,
        registered=("predates-the-key",),
        labelled=("predates-the-key",),
    )

    assert code == 0, f"a profile with no FACTORY_NODE key must not fail the step:\n{output}"
    assert not _labels_set(invoked=invoked)
    assert _labels_removed(invoked=invoked) == ("predates-the-key",)


def test_the_boot_converge_runs_the_label_reconcile_as_a_numbered_step() -> None:
    """The mechanism is on the BOOT path, which is the whole Definition of Done.

    A reconcile that exists and is reached by nothing is the apply-only
    mechanism this item replaces. It is asserted to be a NUMBERED step so the
    boot journal names it like every other one rather than hiding it inside
    another, and to be ordered after the cluster stack — it depends on nothing
    above it and nothing above depends on it, so its bounded registration wait
    must never sit in front of Kueue, ARC and the scale sets.
    """
    body = _BOOT_CONVERGE.read_text(encoding="utf-8")
    # Resolved from the converge's OWN script directory, which is what makes one
    # script work from the installed tree and from a checkout — the same
    # resolution `render-sa-kubeconfig.sh` gets.
    assignment = re.search(
        rf'(?m)^(?P<var>[A-Z_]+)="\$\{{SCRIPT_DIR\}}/{re.escape(_LABEL_CONVERGE.name)}"$', body
    )
    assert assignment is not None, (
        f"reconstruct/converge-ci-stack.sh must resolve {_LABEL_CONVERGE.name} beside itself; "
        "without it the factory label is reconciled by no boot-time mechanism and is lost at "
        "every control-plane reboot"
    )
    step = re.search(r'(?m)^log "(?P<step>10f\.[^"]*)"$', body)
    assert step is not None, (
        "the factory-label reconcile must be a NUMBERED converge step (10f), so a boot that "
        "could not label a node says which step failed"
    )
    # Step 10f's own block: from its log line to the next step's.
    tail = body[step.end() :]
    following = re.search(r'(?m)^log "', tail)
    block = tail[: following.start()] if following is not None else tail
    assert f'"${{{assignment["var"]}}}"' in block, (
        f"step 10f must INVOKE {_LABEL_CONVERGE.name}; a converge that resolves its path and "
        "never runs it is the apply-only mechanism this item replaces"
    )
    factory_namespace_at = body.find('kubectl apply -f "${FACTORY_DIR}"')
    assert -1 < factory_namespace_at < step.start(), (
        "the label reconcile must come after the factory namespace step: its bounded wait for a "
        "re-registering agent must not be ordered in front of anything the pool needs"
    )


def test_the_ci_converge_unit_role_installs_the_script_and_every_pool_profile() -> None:
    """The host has no checkout, so the boot converge can only run what the role installed.

    Both halves are asserted, because either one alone leaves the step
    warning instead of reconciling: the script itself, and the committed
    profiles it reads the declared posture out of. The profiles go into a
    SUBDIRECTORY — `node_extended_resource` already owns `<lib-dir>/<node>.env`
    for this node's own copy, and one file may have one owner.
    """
    defaults = _ROLE_DEFAULTS.read_text(encoding="utf-8")
    tasks = _ROLE_TASKS.read_text(encoding="utf-8")
    sources = set(re.findall(r"^\s*- src:\s*(\S+)\s*$", defaults, re.MULTILINE))
    relative = _LABEL_CONVERGE.relative_to(_PHASE2).as_posix()
    assert relative in sources, (
        f"the ci_converge_unit role does not install {relative} onto the host, so the boot "
        "converge would find no reconcile to run and the factory label would be lost at every "
        "reboot — silently, exactly as it was on 2026-10-16"
    )
    directories = set(re.findall(r"^\s*- (\S+)\s*$", defaults, re.MULTILINE))
    assert _INSTALLED_PROFILES_SUBDIR in directories, (
        f"the role must create the installed `{_INSTALLED_PROFILES_SUBDIR}` directory in "
        "ci_converge_unit_directories; --check cannot see past a missing parent, so a drift read "
        "would pass and the apply fail"
    )
    assert "groups['ci_pool']" in defaults or "groups['ci_pool']" in tasks, (
        "the role must install EVERY ci_pool node's profile, resolved from the inventory group — "
        "a hand-written roster of node names is the second source of truth that "
        "livespec-dev-tooling-prdxxe forbids, and a pool node missing from it is a node the boot "
        "reconcile cannot see"
    )
    assert _INSTALLED_PROFILES_SUBDIR in tasks, (
        "the role declares the installed profiles directory but copies nothing into it, so the "
        "boot reconcile reads an empty directory and labels nothing"
    )
