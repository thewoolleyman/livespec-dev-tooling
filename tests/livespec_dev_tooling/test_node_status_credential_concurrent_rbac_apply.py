"""Two agents' per-node RBAC applies must never reach the server at the same time.

WHAT THIS COSTS WHEN IT IS WRONG (work-item livespec-dev-tooling-r5gdzj,
measured 2026-10-14 on gate run 20261014T023745Z-2075403). The
`node_status_credential` role's task "Apply the per-node RBAC on the server"
runs ONCE PER AGENT, delegated to the control-plane node, and every per-node
render carries the SHARED `ci-runner-node-status` Namespace — the one object in
that manifest that is identical for every agent. The first
`just ansible-apply ansible/ci-pool.yml` with TWO agents in `ci_pool` ran
gmktec-xubuntu's and hp-xubuntu's applies concurrently, and hp's died with:

    Error from server (Conflict): error when applying patch:
    ... Operation cannot be fulfilled on namespaces "ci-runner-node-status":
    the object has been modified; please apply your changes to the latest
    version and try again

`kubectl apply` reads the live object and patches it, so two applies that race
on one object are two patches derived from one `resourceVersion`, and the loser
is refused. hp's whole play stopped 42 tasks in. With one agent the race could
not occur, which is why the role carried this for as long as the pool had one
agent — and why an unattended full-pool converge was nondeterministic from the
moment the second agent joined.

WHY THE TASK IS RUN RATHER THAN READ. The claim is about ansible's SCHEDULING —
whether two hosts' delegated copies of one task can be in flight at the same
instant — and no reading of a task file establishes it. So the committed task is
lifted verbatim out of the role, at the nesting the role declares it in, and
EXECUTED through the same pinned `ansible-core` `just ansible-apply` runs,
against two local agent hosts delegating to one local stand-in server. Lifted
rather than restated, exactly as `test_node_status_credential_one_renderer.py`
lifts the role's renderer invocation: a test carrying its own copy of the task
would keep passing over a role that had dropped the serialization.

HOW OVERLAP IS MEASURED. The stand-in `kubectl` claims a lock directory with
`mkdir` — atomic, so the claim cannot be lost — holds it for a couple of
seconds, and records `enter`/`leave` into one shared log. A second apply that
arrives while the first holds the lock records `overlap` and the log's
enter/leave markers stop alternating. So "they did not overlap" is read off the
order two real processes wrote, not off a model of ansible's forks.

AND THE DETECTOR HAS A CONTROL ARM. The same lifted task with its serialization
keyword stripped MUST be convicted — otherwise a green verdict here would mean
nothing more than that this fixture never managed to run the two applies
together.

Work-item: livespec-dev-tooling-r5gdzj. Plan: livespec `factory-worker-nodes-gitops`
(epic livespec-sqvj7p). The obligation that a pool node be rebuildable from bare
metal by one committed procedure — of which `ansible/ci-pool.yml` is the
node-provisioning stage, re-runnable against a node already in its declared
state — lives in this repository's
`SPECIFICATION/non-functional-requirements.md`.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

import pytest

__all__: list[str] = []

# INTEGRATION TIER, declared statically and honestly: every assertion below is
# read off a real run of the committed task through the pinned `ansible-core`,
# with real stand-in executables on PATH. The marker is never used to select or
# deselect — no recipe or workflow passes `-m`.
pytestmark = pytest.mark.integration

_REPO_ROOT = Path(__file__).resolve().parents[2]
_JUSTFILE = _REPO_ROOT / "justfile"
_ROLE_TASKS = _REPO_ROOT / "ansible" / "roles" / "node_status_credential" / "tasks" / "main.yml"
_RBAC_TEMPLATE = (
    _REPO_ROOT
    / "ci-runner"
    / "k3s"
    / "phase2"
    / "node-status-credential"
    / "node-status-patch-rbac.yaml"
)
_INVENTORY = _REPO_ROOT / "ansible" / "inventory" / "legacy.yml"

# The committed task this module is about, named by the role's own prose name —
# the string an operator reads in the play's output.
_APPLY_TASK = "Apply the per-node RBAC on the server"

# The ansible keyword that serializes a task across hosts, and the role's own
# spelling of it. Stripped by the control arm, so the detector is held to
# convicting the task this one keyword away from the committed one.
_SERIALIZATION = "throttle: 1"

# The two agent hosts and the one server, named for this test rather than for
# real pool nodes so no output of this suite can be mistaken for a record of a
# fleet machine having been reached. TWO agents is the whole point: with one,
# the race the role carried could not occur.
_SERVER = "rbac-apply-server"
_AGENTS = ("rbac-apply-agent-one", "rbac-apply-agent-two")

# The node names the two agents' renders are composed from. Distinct, because
# every object in the manifest except the Namespace is per-node, and the
# Namespace being the one shared object is the premise of the race.
_NODE_NAMES = ("rbac-apply-node-one", "rbac-apply-node-two")

# The template's placeholder and the shared Namespace it does NOT substitute.
_PLACEHOLDER = "NODE_NAME_PLACEHOLDER"
_SHARED_NAMESPACE = "ci-runner-node-status"

# THE WHOLE GRANT, written out rather than sampled, and deliberately a SECOND
# copy of it — the same discipline
# `ci-runner/k3s/phase2/node-status-credential/provision-node-status-credential-exit-tests.sh`
# §B takes with the same rule set. One rule: `get` and `patch` on `nodes/status`,
# restricted by `resourceNames` to the one node the render names. NOT `nodes`
# (whose `spec` could untaint the node), NOT `list`/`watch` (not restrictable by
# `resourceNames` at all, so either would silently widen this to every node in
# the cluster), NOT `delete`. Held against the bytes the stand-in server
# RECEIVED, so a widened verb, an added resource or a dropped `resourceNames` is
# convicted exactly where it would otherwise have reached a cluster.
_GRANT = """  - apiGroups:
      - ""
    resources:
      - nodes/status
    resourceNames:
      - {node}
    verbs:
      - get
      - patch"""

# The four per-node objects the role must still apply, beside that Namespace.
_PER_NODE_KINDS = ("ServiceAccount", "Secret", "ClusterRole", "ClusterRoleBinding")

# How long each simulated server-side apply holds the cluster. Long enough that
# two applies dispatched together by a five-fork controller genuinely overlap —
# which the control arm measures rather than assumes — and short enough that the
# serialized arm costs the suite four seconds.
_HOLD_SECONDS = 2

# Bounded: a cold `uvx` resolves and caches ansible-core before the first play
# runs. A hung play must fail this test rather than the suite's whole budget.
_PLAYBOOK_TIMEOUT_SECONDS = 600

_ANSIBLE_CORE_PIN = re.compile(r"ansible-core==[0-9][0-9A-Za-z.]*")

# Task openings are matched at the role's OWN indentation: every task in this
# role lives inside one agent-gated `block:`, so a column-zero reader would find
# exactly one task and prove nothing about the delegated apply.
_TASK_OPENING = re.compile(r"^    - name: .+$", re.MULTILINE)
_TASK_PREFIX = "    - name: "

# The stand-in `sudo`: it drops its option flags and its `-u <user>` and execs
# the rest. The committed task carries `become: true` because the admin
# kubeconfig it reads is root-owned on the real server; this suite runs as
# whoever invoked pytest. So become is SATISFIED rather than switched off, which
# keeps the executed task shape the operator's.
_SUDO_STAND_IN = """#!/bin/sh
while [ $# -gt 0 ]; do
  case "$1" in
    -u) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
exec "$@"
"""

# The stand-in `kubectl`, which is the whole measurement.
#
# THE LOCAL HALF TAKES NO LOCK. `kubectl apply --dry-run=client` reaches no
# cluster — it is the role's validate-and-default step, so a malformed render is
# refused before any object is sent — and it passes the rendered manifest down
# the pipe unchanged, which is what the second `kubectl` then applies.
#
# THE SERVER-SIDE HALF IS THE CONTENDED ONE. It claims a lock DIRECTORY with
# `mkdir`, which is atomic: the loser cannot mistake a half-made claim for a
# free cluster. A loser records `overlap` and does NOT release a lock it never
# held. Both halves append `enter`/`leave` to one shared log, so the ordering is
# read off what two real processes wrote.
#
# IT CAPTURES WHAT IT WAS SENT, one file per invocation, which is how the grant
# assertions below read the bytes the server received rather than a re-render of
# them. And it EXITS NON-ZERO on an invocation it was not written for rather
# than returning a plausible empty string: a task that had moved to
# `--server-side` apply must break this test and be re-examined, not quietly
# satisfy it.
_KUBECTL_STAND_IN = """#!/bin/sh
case "$*" in
  *'--dry-run=client'*)
    cat
    exit 0 ;;
  'apply -f -')
    if mkdir "${RBAC_APPLY_LOCK}" 2>/dev/null; then
      holder=yes
    else
      holder=no
      printf 'overlap\\n' >> "${RBAC_APPLY_LOG}"
    fi
    cat > "${RBAC_APPLY_CAPTURES}/manifest.$$"
    printf 'enter %s\\n' "$$" >> "${RBAC_APPLY_LOG}"
    sleep "${RBAC_APPLY_HOLD_SECONDS}"
    printf 'leave %s\\n' "$$" >> "${RBAC_APPLY_LOG}"
    if [ "${holder}" = yes ]; then
      rmdir "${RBAC_APPLY_LOCK}"
    fi
    printf 'namespace/%s configured\\n' "${RBAC_APPLY_NAMESPACE}"
    exit 0 ;;
esac
printf 'stand-in kubectl: unexpected invocation: %s\\n' "$*" >&2
exit 1
"""


@dataclass(frozen=True, kw_only=True)
class _Run:
    """One completed run of the lifted task: its exit code, its output, its evidence."""

    returncode: int
    output: str
    log: list[str]
    manifests: tuple[str, ...]


def _ansible_core_pin() -> str:
    """The `ansible-core==<version>` pin the `ansible-apply` recipe resolves.

    Read out of the justfile rather than restated here, so this test cannot
    drift onto an ansible whose scheduling semantics nothing has measured.
    """
    recipe = re.search(
        r"^ansible-apply \*args:\n(?P<body>(?:    .*\n)+)",
        _JUSTFILE.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    assert recipe is not None, (
        f"{_JUSTFILE} must carry an `ansible-apply *args:` recipe — it is the one "
        f"sanctioned way this converge runs, and a test that cannot find it is "
        f"measuring some other ansible"
    )
    pin = _ANSIBLE_CORE_PIN.search(recipe["body"])
    assert pin is not None, (
        "the `ansible-apply` recipe must pin ansible-core exactly, so the "
        "scheduling this test measures is the scheduling the operator gets"
    )
    return pin[0]


def _committed_apply_task() -> str:
    """The role's delegated RBAC-apply task, lifted verbatim at its own indentation."""
    text = _ROLE_TASKS.read_text(encoding="utf-8")
    openings = [match.start() for match in _TASK_OPENING.finditer(text)]
    assert openings, (
        f"{_ROLE_TASKS} must declare its tasks as `- name:` entries indented into "
        f"the agent block; a task this reader cannot find is one this test has "
        f"stopped measuring"
    )
    lifted = [
        text[start:stop]
        for start, stop in pairwise([*openings, len(text)])
        if text[start:stop].split("\n", 1)[0][len(_TASK_PREFIX) :].strip() == _APPLY_TASK
    ]
    assert len(lifted) == 1, (
        f"{_ROLE_TASKS} must carry exactly one task named {_APPLY_TASK!r} — it is "
        f"the delegated, shared-object apply this test runs; found {len(lifted)}"
    )
    return lifted[0]


def _play(*, task: str) -> str:
    """A one-task play carrying `task` at the nesting the role declares it in.

    The agent-gated `block:` is reproduced rather than flattened away, because
    `throttle` is a task keyword whose behaviour inside a block is exactly what
    the role depends on: a play that lifted the task out of its block would
    measure a shape the role does not have.
    """
    nested = "\n".join(f"    {line}" if line.strip() else line for line in task.splitlines())
    return (
        "---\n"
        "- name: The role's delegated per-node RBAC apply, as the role declares it\n"
        f"  hosts: {','.join(_AGENTS)}\n"
        "  gather_facts: false\n"
        "  tasks:\n"
        "    - name: Mint and deliver this agent's node-status credential\n"
        "      block:\n"
        f"{nested}\n"
    )


def _inventory(*, root: Path) -> Path:
    """Two agents and one server, all local, each agent carrying its own node name.

    The node name rides as an INVENTORY var because it is per-host and because
    `--extra-vars` would beat it; everything the fixture must bound for every
    host rides as `--extra-vars` instead.
    """
    hosts = "".join(
        f"        {agent}:\n"
        f"          ansible_connection: local\n"
        f"          node_status_credential_node: {node}\n"
        for agent, node in zip(_AGENTS, _NODE_NAMES, strict=True)
    )
    inventory = root / "inventory.yml"
    inventory.write_text(
        "all:\n"
        "  children:\n"
        "    ci_pool:\n"
        "      hosts:\n"
        f"        {_SERVER}:\n"
        "          ansible_connection: local\n"
        f"{hosts}",
        encoding="utf-8",
    )
    return inventory


def _run_lifted_task(*, root: Path, task: str) -> _Run:
    """Run `task` over both agents and return its exit code and its evidence.

    `ANSIBLE_FORKS` is SET rather than inherited: a one-fork controller would
    serialize every task for a reason that has nothing to do with the role, and
    the control arm would then pass for a role that had dropped its
    serialization entirely.
    """
    bin_dir = root / "bin"
    bin_dir.mkdir()
    for name, body in (("sudo", _SUDO_STAND_IN), ("kubectl", _KUBECTL_STAND_IN)):
        stand_in = bin_dir / name
        stand_in.write_text(body, encoding="utf-8")
        stand_in.chmod(0o755)
    captures = root / "captures"
    captures.mkdir()
    log = root / "apply.log"
    log.write_text("", encoding="utf-8")
    playbook = root / "apply.yml"
    playbook.write_text(_play(task=task), encoding="utf-8")

    env = {
        key: value
        for key, value in os.environ.items()
        if key != "COVERAGE_PROCESS_START" and not key.startswith("COV_CORE_")
    }
    env.update(
        {
            "PATH": f"{bin_dir}{os.pathsep}{env['PATH']}",
            "RBAC_APPLY_LOCK": str(root / "lock"),
            "RBAC_APPLY_LOG": str(log),
            "RBAC_APPLY_CAPTURES": str(captures),
            "RBAC_APPLY_HOLD_SECONDS": str(_HOLD_SECONDS),
            "RBAC_APPLY_NAMESPACE": _SHARED_NAMESPACE,
            "ANSIBLE_FORKS": "5",
            "ANSIBLE_NOCOWS": "1",
            "ANSIBLE_RETRY_FILES_ENABLED": "False",
            "ANSIBLE_HOST_KEY_CHECKING": "False",
            "ANSIBLE_INTERPRETER_PYTHON": "auto_silent",
        }
    )
    completed = subprocess.run(
        [
            "uvx",
            "--from",
            _ansible_core_pin(),
            "ansible-playbook",
            "-i",
            str(_inventory(root=root)),
            "-e",
            f"node_status_credential_rbac_template={_RBAC_TEMPLATE}",
            "-e",
            f"node_status_credential_server_host={_SERVER}",
            "-e",
            f"node_status_credential_admin_kubeconfig={root / 'admin.kubeconfig'}",
            str(playbook),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=_PLAYBOOK_TIMEOUT_SECONDS,
        check=False,
    )
    return _Run(
        returncode=completed.returncode,
        output=completed.stdout + completed.stderr,
        log=log.read_text(encoding="utf-8").split(),
        manifests=tuple(path.read_text(encoding="utf-8") for path in sorted(captures.iterdir())),
    )


@pytest.fixture(scope="module")
def serialized(*, tmp_path_factory: pytest.TempPathFactory) -> _Run:
    """One run of the COMMITTED task, shared by every assertion made about it."""
    return _run_lifted_task(
        root=tmp_path_factory.mktemp("serialized"), task=_committed_apply_task()
    )


def _markers(*, run: _Run) -> list[str]:
    """The `enter` / `leave` words of the shared log, in the order they were written."""
    return [word for word in run.log if word in ("enter", "leave", "overlap")]


def _documents(*, manifest: str) -> list[str]:
    """One rendered manifest split into its YAML documents."""
    return [
        document
        for document in re.split(r"^---$", manifest, flags=re.MULTILINE)
        if document.strip()
    ]


def _kinds(*, manifest: str) -> list[str]:
    """Each document's top-level `kind`, which is the only one at column zero."""
    return [
        found["kind"]
        for document in _documents(manifest=manifest)
        if (found := re.search(r"^kind: (?P<kind>\S+)$", document, re.MULTILINE)) is not None
    ]


def _document_of_kind(*, manifest: str, kind: str) -> str:
    """The one document of `kind` in a rendered manifest."""
    matching = [
        document
        for document in _documents(manifest=manifest)
        if re.search(rf"^kind: {kind}$", document, re.MULTILINE) is not None
    ]
    assert (
        len(matching) == 1
    ), f"a rendered manifest must carry exactly one {kind}; found {len(matching)}"
    return matching[0]


def test_two_agents_rbac_applies_never_overlap_on_the_server(*, serialized: _Run) -> None:
    """The Definition of Done's first assertion, measured on a real run.

    Both agents' delegated applies reach the stand-in server, and they reach it
    ONE AT A TIME: nothing recorded `overlap`, and the log's `enter`/`leave`
    markers strictly alternate — which is a property of the order two real
    processes wrote, not of this test's idea of ansible's forks. An overlapping
    pair is the measured Conflict: two patches of the shared
    `ci-runner-node-status` Namespace derived from one `resourceVersion`, of
    which the server refuses the loser.
    """
    assert (
        serialized.returncode == 0
    ), f"the committed apply must succeed for both agents:\n{serialized.output}"
    assert len(serialized.manifests) == len(_AGENTS), (
        f"each agent must send its own render to the server; "
        f"{len(serialized.manifests)} of {len(_AGENTS)} arrived:\n{serialized.output}"
    )
    assert _markers(run=serialized) == ["enter", "leave"] * len(_AGENTS), (
        f"the two agents' server-side applies overlapped, so an apply reaching "
        f"two or more agents can be refused on the shared "
        f"{_SHARED_NAMESPACE} Namespace: {serialized.log}"
    )


def test_the_same_apply_without_its_serialization_does_overlap(*, tmp_path: Path) -> None:
    """The control arm, without which a green verdict above would mean nothing.

    The committed task MUST carry the serialization keyword — stripping it has
    to change something — and the task one keyword away from the committed one
    MUST be convicted by this fixture. An arm that could not produce an overlap
    would report "they did not overlap" about a fixture that never managed to
    run the two applies together.
    """
    committed = _committed_apply_task().splitlines()
    kept = [line for line in committed if line.strip() != _SERIALIZATION]

    assert kept != committed, (
        f"{_ROLE_TASKS}'s {_APPLY_TASK!r} task must carry `{_SERIALIZATION}`: it "
        f"applies the SHARED {_SHARED_NAMESPACE} Namespace once per agent, and "
        f"two agents' applies of one object race on its resourceVersion"
    )

    run = _run_lifted_task(root=tmp_path, task="\n".join([*kept, ""]))

    assert "overlap" in _markers(run=run), (
        f"this fixture could not make two unserialized applies overlap, so it "
        f"cannot convict one that does; the role's serialization is therefore "
        f"unmeasured: {run.log}\n{run.output}"
    )


def test_each_agent_still_gets_its_own_grant_and_one_shared_namespace(*, serialized: _Run) -> None:
    """The Definition of Done's second assertion, read off the bytes the server got.

    Serializing the apply must not change WHAT is applied. Each agent's render
    still carries its own ServiceAccount, token Secret, ClusterRole and
    ClusterRoleBinding, named for that agent's node and substituted (no
    placeholder survives); and the grant is still the one rule the template
    declares — `get` and `patch` on `nodes/status`, restricted by
    `resourceNames` to that one node, and nothing else.

    The Namespace is asserted to be the SHARED one in BOTH renders, because that
    is the premise of the race rather than an incidental detail: it is the one
    object two agents' applies contend on.
    """
    assert len(serialized.manifests) == len(_AGENTS)
    for manifest in serialized.manifests:
        node = next(name for name in _NODE_NAMES if name in manifest)
        other = next(name for name in _NODE_NAMES if name != node)

        assert _PLACEHOLDER not in manifest
        assert other not in manifest
        assert _kinds(manifest=manifest) == ["Namespace", *_PER_NODE_KINDS]
        assert f"name: {_SHARED_NAMESPACE}" in _document_of_kind(
            manifest=manifest, kind="Namespace"
        )
        for kind in _PER_NODE_KINDS:
            assert node in _document_of_kind(manifest=manifest, kind=kind)

        rules = _document_of_kind(manifest=manifest, kind="ClusterRole").split("rules:\n", 1)[1]
        assert rules.strip("\n") == _GRANT.format(node=node)


def test_the_committed_pool_reaches_the_two_agents_that_made_this_race_live() -> None:
    """Why the serialization is load-bearing rather than defensive.

    The race needs two or more agents applied in one play. The committed
    `ci_pool` has exactly that — it is what made a bug the role had carried
    since it was written reachable on the first full-pool converge — so this is
    read from the inventory rather than asserted as a count: an inventory that
    dropped back to one agent would make the serialization untested by the run
    above, and nothing would say so.
    """
    pool = _INVENTORY.read_text(encoding="utf-8").split("        ci_pool:\n", 1)[1]
    agents = re.findall(
        r"^ {12}(?P<host>[\w.-]+):\n(?: {14}.*\n)*? {14}cluster_role: agent$",
        pool,
        re.MULTILINE,
    )

    assert len(agents) >= 2, (
        f"the committed ci_pool must name the two or more agents whose concurrent "
        f"applies this serialization exists for; it names {agents}"
    )
