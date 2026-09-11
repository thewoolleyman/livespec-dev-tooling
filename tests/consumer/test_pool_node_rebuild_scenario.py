"""Consumer-tier: the `SPECIFICATION/scenarios.md` scenario

    "a pool node is rebuilt from bare metal by the recipe and its profile"

WHAT A REBUILD REHEARSAL IS, OFF THE NODE. The scenario's subject is a node
powered on with empty storage, taken to a pool member executing a job. Nothing
here powers on a node. But every stage of the procedure is a committed,
executable artifact that carries a `--dry-run` mode in which every mutating
command is PRINTED and none is run, and every state it reads comes from
read-only probes (`lsblk`, `blkid`, `pvs`, `vgs`, `lvs`) that a test can answer.
So this file RUNS the committed stages — the real scripts, unmodified, on a
scratch `PATH` — against three worlds it composes, and asserts on the plans they
emit: an EMPTY node, a FINISHED node, and a finished node whose populated tier
has drifted. That is the rebuild rehearsed as far as a machine that is not the
node can rehearse it, which is strictly more than reading the scripts can say.

THE FAKE `PATH` AND WHAT EACH HALF OF IT IS FOR. The five probes above are
stubs that answer out of a world file, so the verdict never depends on the block
devices of the machine running the suite. Every MUTATING command the stage can
reach (`sgdisk`, `wipefs`, `partprobe`, the LVM trio, the `mkfs` family,
`apt-get`, `udevadm`) is a TRIPWIRE that appends to a file: a dry run that
executed anything leaves it non-empty, which is asserted directly rather than
assumed from the flag. Each child's environment is built from scratch and each
child is `bash`, never Python.

WHY THE PLAN IS HELD AGAINST THE PROFILE *AND* AGAINST THE COMMITTED CAPTURE.
The two answer different halves of the same Then. Against the PROFILE: every
volume group, logical volume and role-labelled filesystem the profile declares
must be reached by a planned command, which is "reaches the profile's declared
state with NO STEP PERFORMED BY HAND" said as an assertion — a declared tier
absent from the plan is a tier an operator has to create themselves on the one
day the recipe is exercised. Against the committed CAPTURE
(`profiles/<node>.expected-plan`): that file is the recorded outcome of a
rehearsal, and holding today's run against it byte for byte is what keeps the
record from becoming a claim — a step silently added, dropped or reworded between
two asserted rungs passes every structural check and fails this one.

THE RE-RUN CLAUSE IS TWO CLAUSES AND THEY PULL OPPOSITE WAYS. Against a node
already in its declared state the procedure must plan NOTHING; against a node
whose populated tier no longer matches it, the procedure must REFUSE, naming the
volume, rather than remaking it. A procedure with only the first property
silently reformats a populated cache tier on the day a label drifts; one with
only the second refuses every ordinary re-run. Both are asserted from real runs,
and the refusal is asserted to be target-SPECIFIC: consent to a different volume
does not unlock it, which is the property that makes the named remedy a safety
mechanism rather than decoration.

WHAT IS ASSERTED BY READING. Two clauses have no runnable half here. The node's
JOIN is credential-gated on a token file that exists only on the node, so what
is asserted is the refusal itself — the agent stage must refuse, naming the
profile and the file, rather than joining unauthenticated. And the non-gating
job addressed to the node alone is a workflow document, asserted as the two
properties that make the sentence true: it is addressed to ONE node, and no
event can route a merge through it.

CONTROL ARMS. Each reader takes text or a captured plan and is fed a
counter-example; each execution arm is paired with a run of the SAME stage under
the opposite condition, so a harness that simply never planned anything, or a
reader whose match quietly stopped working, cannot satisfy any of it.
"""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_BARE_METAL = _K3S / "phase0-bare-metal"
_PROFILES = _BARE_METAL / "profiles"
_STORAGE_LAYOUT = _BARE_METAL / "storage-layout.sh"
_PROVISION_K3S = _K3S / "provision-k3s.sh"
_PROOF_JOB = _K3S / "test-job" / "proof-job.yml"

_RUN_TIMEOUT_S = 120.0
# Every command the stage can issue that CHANGES the node. Each is a tripwire on
# the scratch PATH, so "the dry run executed nothing" is measured, not assumed.
_MUTATORS = (
    "sgdisk",
    "wipefs",
    "partprobe",
    "pvcreate",
    "vgcreate",
    "lvcreate",
    "mkfs.ext4",
    "mkfs.xfs",
    "mkfs.vfat",
    "mkswap",
    "udevadm",
    "apt-get",
)
# The filesystem maker each declared type is made with, which is the plan's own
# `fs_tool` mapping read from the other side: a declared tier is only reached
# when the maker its type implies names its label.
_MAKERS = {"ext4": "mkfs.ext4", "xfs": "mkfs.xfs", "vfat": "mkfs.vfat", "swap": "mkswap"}

# The nodes this tree commits a profile for: the proof job must address one of
# them and nothing broader, which is what "addressed to it alone" is here.
_COMMITTED_NODES = ("poweredge-xubuntu", "gmktec-xubuntu")

_PROFILE_ENTRY = re.compile(r"^(?P<key>[A-Z][A-Z0-9_]*)=(?P<value>.*)$", re.MULTILINE)
_PINNED_K3S = re.compile(r"INSTALL_K3S_VERSION='(?P<version>v\d+\.\d+\.\d+\+k3s\d+)'")
_INSTALL_EXEC = re.compile(r"INSTALL_K3S_EXEC='(?P<exec>[^']*)'")
_WORKFLOW_TRIGGER = re.compile(r"^on:\n(?P<body>(?:[ \t]+.*\n|\n)*)", re.MULTILINE)
_TRIGGER_NAME = re.compile(r"^\s{2,}(?P<name>[a-z_]+):", re.MULTILINE)
_RUNS_ON = re.compile(r"^\s*runs-on:\s*(?P<target>.+?)\s*$", re.MULTILINE)

# The probes, answering out of a world file rather than the host's block devices.
_PROBE_STUBS = {
    "lsblk": """\
#!/bin/sh
case "$*" in
  *PARTLABEL*) [ -f "$WORLD/partlabels" ] && cat "$WORLD/partlabels" ;;
  *PARTN*) [ -f "$WORLD/partns" ] && cat "$WORLD/partns" ;;
esac
exit 0
""",
    "blkid": """\
#!/bin/sh
key=; device=
while [ $# -gt 0 ]; do
  case "$1" in
    -s) key=$2; shift ;;
    -p|-o|value) ;;
    *) device=$1 ;;
  esac
  shift
done
[ -f "$WORLD/blkid" ] || exit 0
awk -F'\t' -v d="$device" -v k="$key" '$1==d && $2==k {print $3}' "$WORLD/blkid"
exit 0
""",
}
_LVM_PROBE = """\
#!/bin/sh
for argument; do :; done
grep -qxF "%(kind)s:$argument" "$WORLD/lvm" 2>/dev/null && echo "  $argument"
exit 0
"""
_TRIPWIRE_STUB = """\
#!/bin/sh
echo "$0 $*" >> "$TRIPWIRE"
exit 0
"""

# The counter-examples the control arms feed back through the readers: a k3s
# install that pins no version and carries no pool label, and a workflow any
# pull request routes to a whole class of runners.
_CONTROL_PLAN = "curl -sfL https://get.k3s.io | sh -s -"
_CONTROL_UNLABELLED_PLAN = (
    "curl -sfL https://get.k3s.io | INSTALL_K3S_VERSION='v1.36.2+k3s1' "
    "INSTALL_K3S_EXEC='server --disable traefik' sh -s -"
)
_CONTROL_WORKFLOW = """\
name: control
on:
  pull_request:
  workflow_dispatch: {}
jobs:
  build:
    runs-on: [self-hosted, poweredge-xubuntu-k3s]
  elsewhere:
    runs-on: ubuntu-latest
"""


@dataclass(frozen=True, kw_only=True)
class _Rehearsal:
    """What one dry run of a committed stage left behind."""

    code: int
    plan: list[str]
    notes: str
    refusal: str
    executed: list[str]


def _profile(*, name: str) -> dict[str, str]:
    """One committed per-node profile, parsed as the shared parser parses it."""
    text = (_PROFILES / f"{name}.env").read_text(encoding="utf-8")
    return {
        entry.group("key"): entry.group("value").strip() for entry in _PROFILE_ENTRY.finditer(text)
    }


def _captured_plan(*, name: str) -> list[str]:
    """The plan a rehearsal of that profile recorded, without its header prose."""
    text = (_PROFILES / f"{name}.expected-plan").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if line and not line.startswith("#")]


def _write_world(*, root: Path, world: dict[str, str]) -> Path:
    """Materialise the node state the probes will report."""
    directory = root / "world"
    directory.mkdir(parents=True, exist_ok=True)
    for name, body in world.items():
        (directory / name).write_text(body, encoding="utf-8")
    return directory


def _scratch_path(*, root: Path) -> Path:
    """The stub directory: read-only probes that answer, mutators that only record."""
    binaries = root / "bin"
    binaries.mkdir(parents=True, exist_ok=True)
    stubs = dict(_PROBE_STUBS)
    for kind, tool in (("pv", "pvs"), ("vg", "vgs"), ("lv", "lvs")):
        stubs[tool] = _LVM_PROBE % {"kind": kind}
    for tool in _MUTATORS:
        stubs[tool] = _TRIPWIRE_STUB
    for tool, body in stubs.items():
        stub = binaries / tool
        stub.write_text(body, encoding="utf-8")
        stub.chmod(0o755)
    return binaries


def _rehearse(
    *,
    root: Path,
    stage: Path,
    profile: str,
    world: dict[str, str] | None = None,
    consent: tuple[str, ...] = (),
) -> _Rehearsal:
    """Run one committed stage against a composed node state; report what it planned.

    The stage runs UNMODIFIED under `--dry-run`, so no mutating command is
    executed by construction; the tripwire count is what proves it rather than
    the flag. The child's environment is built from scratch and the child is
    `bash`, never Python, so nothing of the harness reaches it.
    """
    root.mkdir(parents=True, exist_ok=True)
    tripwire = root / "tripwire"
    tripwire.write_text("", encoding="utf-8")
    binaries = _scratch_path(root=root)
    done = subprocess.run(
        [
            "bash",
            str(stage),
            "--dry-run",
            *[f"--i-consent-to-destroy={target}" for target in consent],
            str(_PROFILES / f"{profile}.env"),
        ],
        capture_output=True,
        text=True,
        timeout=_RUN_TIMEOUT_S,
        check=False,
        env={
            "PATH": f"{binaries}{os.pathsep}/usr/bin{os.pathsep}/bin",
            "WORLD": str(_write_world(root=root, world=world or {})),
            "TRIPWIRE": str(tripwire),
        },
    )
    return _Rehearsal(
        code=done.returncode,
        plan=[line[2:] for line in done.stdout.splitlines() if line.startswith("+ ")],
        notes=done.stdout,
        refusal=done.stderr,
        executed=[line for line in tripwire.read_text(encoding="utf-8").splitlines() if line],
    )


def _unreached_declarations(*, profile: dict[str, str], plan: list[str]) -> list[str]:
    """Each thing the profile DECLARES that no planned command would create."""
    unreached: list[str] = []
    for group in profile["VOLUME_GROUPS"].split():
        name, _, device = group.partition(":")
        if not any(line.startswith(f"vgcreate {name} ") and device in line for line in plan):
            unreached.append(f"volume group {name} on {device}")
        if not any(line.startswith("pvcreate ") and device in line for line in plan):
            unreached.append(f"physical volume {device}")
    for record in profile["LOGICAL_VOLUMES"].split():
        group, volume, _, fstype, label = record.split(":")
        if not any(f"-n {volume} {group}" in line for line in plan if line.startswith("lvcreate ")):
            unreached.append(f"logical volume {group}/{volume}")
        maker, device = _MAKERS[fstype], f"/dev/{group}/{volume}"
        if not any(
            line.startswith(f"{maker} ") and label in line and device in line for line in plan
        ):
            unreached.append(f"{fstype} filesystem labelled {label} on {device}")
    return unreached


def _k3s_install_gaps(*, plan: str, role: str) -> list[str]:
    """Each way the k3s stage's plan would leave the node off the pool, or unpinned."""
    gaps: list[str] = []
    if _PINNED_K3S.search(plan) is None:
        gaps.append("the k3s install pins no version: the node comes up on whatever is current")
    declared = _INSTALL_EXEC.search(plan)
    if declared is None or not declared.group("exec").startswith(role):
        gaps.append(f"the install does not start k3s in the profile's {role} role")
    if declared is not None and "--node-label" not in declared.group("exec"):
        gaps.append("the node carries no pool role label, so nothing addresses it as a member")
    return gaps


def _gating_exposure(*, workflow: str, nodes: tuple[str, ...]) -> list[str]:
    """Each way the proof job would stop being one node's, or stop being non-gating."""
    triggers = _WORKFLOW_TRIGGER.search(workflow)
    named = sorted(_TRIGGER_NAME.findall(triggers.group("body"))) if triggers else []
    exposure = [f"routed by {event}" for event in named if event != "workflow_dispatch"]
    if not named:
        exposure.append("the workflow declares no trigger at all")
    for target in _RUNS_ON.findall(workflow):
        if target.startswith("["):
            exposure.append(f"addressed to a label set rather than one node: {target}")
        elif not any(node in target for node in nodes):
            exposure.append(f"addressed to no committed node: {target}")
    return exposure


def test_a_pool_node_is_rebuilt_from_bare_metal_by_the_recipe_and_its_profile(
    tmp_path: Path,
) -> None:
    """§"a pool node is rebuilt from bare metal by the recipe and its profile", clause by clause.

    ONE PROCEDURE, ONE PROFILE PER NODE, REHEARSED FROM EMPTY STORAGE: both
    committed profiles are run through the SAME stage, from a world in which the
    node's storage is empty, and each resulting plan is held against two things.
    Against its profile: every volume group, physical volume, logical volume and
    role-labelled filesystem declared must be reached by a planned command —
    which is what "with no step performed by hand" forbids the absence of.
    Against its committed capture: byte for byte, because the capture is the
    recorded outcome of a rehearsal and a record nothing re-derives is a claim.
    The two profiles differ in kind on purpose — one takes a whole device and
    builds a controller virtual disk, the other preserves the operating system
    its node already boots and takes only the free tail — so a procedure that
    had quietly become the first node's is convicted by the second.

    AND NOTHING RAN: every mutating command on the stage's PATH is a tripwire, so
    the dry run's "executed none" is measured rather than taken from the flag.

    RE-RUNNING CHANGES NOTHING: the same stage, the same profile, against a
    world reporting the finished node — zero planned commands, and the stage
    says so in as many words.

    AND REFUSES EVERY STEP THAT WOULD DESTROY POPULATED STORAGE: the same stage
    again, against the finished node with one tier's label drifted. Remaking that
    filesystem is exactly the step that would destroy a populated cache tier, so
    the run must REFUSE, name the volume, and offer consent for that volume;
    consent to a DIFFERENT volume must not unlock it, and consent to the right
    one must let the single remake through and nothing else.

    THE NODE JOINS THE POOL: the k3s stage's plan must pin its k3s version, start
    it in the role the profile declares, and label the node as a pool member.
    The agent's join is credential-gated — the token is on the node and in no
    tree — so what is asserted there is the refusal: it must name the profile and
    the file rather than joining unauthenticated.

    AND EXECUTES A NON-GATING JOB ADDRESSED TO IT ALONE: the committed proof job
    must be addressed to one node's scale set as a bare name, and no event may
    route a pull request to it, which is what makes "non-gating" structural
    rather than a promise.
    """
    empty = {"partns": "1\n2\n"}
    for name in _COMMITTED_NODES:
        rehearsed = _rehearse(
            root=tmp_path / f"empty-{name}", stage=_STORAGE_LAYOUT, profile=name, world=empty
        )
        unreached = _unreached_declarations(profile=_profile(name=name), plan=rehearsed.plan)
        assert rehearsed.code == 0 and not unreached, (
            f"{name}: a rebuild from empty storage must reach every tier the profile declares. "
            f"A declared volume or filesystem absent from the plan is one an operator has to "
            f"create by hand on the one day this recipe is exercised; unreached={unreached} "
            f"stderr={rehearsed.refusal!r}"
        )
        assert rehearsed.plan == _captured_plan(name=name), (
            f"{name}: the run must reproduce the rehearsal outcome committed beside the profile, "
            f"byte for byte. A step silently added, dropped or reworded between two asserted "
            f"rungs passes every structural check and only fails this one; planned="
            f"{rehearsed.plan}"
        )
        assert not rehearsed.executed, (
            f"{name}: a dry run must execute nothing — asserted from tripwires on every mutating "
            f"command rather than from the flag; executed={rehearsed.executed}"
        )

    finished = {
        "partlabels": "lvm\n",
        "partns": "1\n2\n3\n",
        "lvm": "pv:/dev/nvme0n1p3\nvg:nvmea\n"
        + "".join(f"lv:nvmea/{tier}\n" for tier in ("ci-cache", "ci-containerd", "ci-workvols")),
        "blkid": "".join(
            f"/dev/nvmea/{tier}\tTYPE\t{fstype}\n/dev/nvmea/{tier}\tLABEL\t{label}\n"
            for tier, fstype, label in (
                ("ci-cache", "ext4", "ci-cache"),
                ("ci-containerd", "ext4", "ci-containerd"),
                ("ci-workvols", "xfs", "ci-workvols"),
            )
        ),
    }
    again = _rehearse(
        root=tmp_path / "finished",
        stage=_STORAGE_LAYOUT,
        profile="gmktec-xubuntu",
        world=finished,
    )
    assert again.code == 0 and again.plan == [], (
        f"re-run against a node already in its profile's declared state, the procedure must plan "
        f"NOTHING; planned={again.plan}"
    )
    assert "already in the state" in again.notes, (
        f"and must say so, rather than reporting an empty plan it reached for another reason; "
        f"output={again.notes!r}"
    )

    drifted = dict(finished, blkid=str(finished["blkid"]).replace("\tci-workvols\n", "\tSTALE\n"))
    refused = _rehearse(
        root=tmp_path / "drifted",
        stage=_STORAGE_LAYOUT,
        profile="gmktec-xubuntu",
        world=drifted,
    )
    tier = "/dev/nvmea/ci-workvols"
    assert refused.code != 0 and tier in refused.refusal, (
        f"a populated tier whose label has drifted must be REFUSED, not remade: remaking it is "
        f"the step that destroys the node's populated storage. rc={refused.code} "
        f"stderr={refused.refusal!r}"
    )
    assert f"--i-consent-to-destroy={tier}" in refused.refusal, (
        f"and the refusal must name the volume in its remedy — an unnamed refusal is one an "
        f"operator satisfies by consenting to the wrong volume; stderr={refused.refusal!r}"
    )

    misdirected = _rehearse(
        root=tmp_path / "misdirected",
        stage=_STORAGE_LAYOUT,
        profile="gmktec-xubuntu",
        world=drifted,
        consent=("/dev/nvmea/ci-cache",),
    )
    assert misdirected.code != 0 and tier in misdirected.refusal, (
        f"consent is per TARGET: consenting to another volume must not unlock this one, or the "
        f"named remedy is decoration; rc={misdirected.code}"
    )
    granted = _rehearse(
        root=tmp_path / "granted",
        stage=_STORAGE_LAYOUT,
        profile="gmktec-xubuntu",
        world=drifted,
        consent=(tier,),
    )
    assert granted.code == 0 and granted.plan == [
        f"mkfs.xfs -q -m reflink=1 -L ci-workvols {tier}"
    ], (
        f"and consent to the right volume must let exactly that one step through — so the "
        f"refusals above cannot be satisfied by a stage that refuses everything; "
        f"planned={granted.plan}"
    )

    server = _rehearse(
        root=tmp_path / "k3s-server", stage=_PROVISION_K3S, profile="poweredge-xubuntu"
    )
    unpinned = _k3s_install_gaps(
        plan=server.notes, role=_profile(name="poweredge-xubuntu")["CLUSTER_ROLE"]
    )
    assert server.code == 0 and not unpinned, (
        f"the k3s stage must bring the node up on a PINNED k3s, in the role its profile declares, "
        f"carrying the label that makes it addressable as a pool member; gaps={unpinned}"
    )
    agent = _rehearse(root=tmp_path / "k3s-agent", stage=_PROVISION_K3S, profile="gmktec-xubuntu")
    token = _profile(name="gmktec-xubuntu")["CLUSTER_TOKEN_FILE"]
    assert agent.code != 0 and token in agent.refusal, (
        f"an agent's join is credential-gated: with the join token absent the stage must refuse, "
        f"naming the file, rather than joining the pool unauthenticated; "
        f"rc={agent.code} stderr={agent.refusal!r}"
    )

    exposure = _gating_exposure(
        workflow=_PROOF_JOB.read_text(encoding="utf-8"), nodes=_COMMITTED_NODES
    )
    assert not exposure, (
        f"the job that proves the rebuilt node executes work must be addressed to that node's "
        f"scale set alone and reachable only by manual dispatch — an event-routed proof job can "
        f"become a required check, which is the gating this scenario's job must never do; "
        f"exposure={exposure}"
    )

    _assert_every_reader_still_convicts()


def _assert_every_reader_still_convicts() -> None:
    """Feed each reader a counter-example, so a match that stopped working is caught."""
    assert _unreached_declarations(
        profile=_profile(name="gmktec-xubuntu"), plan=[_CONTROL_PLAN]
    ) == [
        "volume group nvmea on /dev/nvme0n1p3",
        "physical volume /dev/nvme0n1p3",
        "logical volume nvmea/ci-cache",
        "ext4 filesystem labelled ci-cache on /dev/nvmea/ci-cache",
        "logical volume nvmea/ci-containerd",
        "ext4 filesystem labelled ci-containerd on /dev/nvmea/ci-containerd",
        "logical volume nvmea/ci-workvols",
        "xfs filesystem labelled ci-workvols on /dev/nvmea/ci-workvols",
    ], "the declaration reader must still convict a plan that creates none of the declared state"
    assert _k3s_install_gaps(plan=_CONTROL_PLAN, role="server") == [
        "the k3s install pins no version: the node comes up on whatever is current",
        "the install does not start k3s in the profile's server role",
    ], "the k3s reader must still convict an unpinned, roleless install"
    assert _k3s_install_gaps(plan=_CONTROL_UNLABELLED_PLAN, role="server") == [
        "the node carries no pool role label, so nothing addresses it as a member"
    ], (
        "and must still convict a correctly pinned install that labels nothing — an unlabelled "
        "node boots, joins, and is reachable by no workload that selects the pool"
    )
    assert _gating_exposure(workflow=_CONTROL_WORKFLOW, nodes=_COMMITTED_NODES) == [
        "routed by pull_request",
        "addressed to a label set rather than one node: [self-hosted, poweredge-xubuntu-k3s]",
        "addressed to no committed node: ubuntu-latest",
    ], "the gating reader must still convict an event-routed job addressed anywhere but one node"
    assert _gating_exposure(workflow="jobs: {}", nodes=_COMMITTED_NODES) == [
        "the workflow declares no trigger at all"
    ], "and must read an absent trigger block as unproven rather than as safely non-gating"
