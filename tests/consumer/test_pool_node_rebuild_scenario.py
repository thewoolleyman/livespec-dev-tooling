"""Consumer-tier: `SPECIFICATION/scenarios.md` §"a pool node is rebuilt from bare metal by the recipe and its profile".

    Given `ci-runner/k3s/` carries one node rebuild procedure whose first stage
    is `ci-runner/k3s/phase0-bare-metal/` and one committed profile per pool node
    And a pool node is powered on with empty storage
    When an operator runs the procedure naming that node's profile
    Then the node's storage layout, base operating system, pinned k3s, and
    node-local mechanisms MUST reach the profile's declared state with no step
    performed by hand
    And the node MUST join the pool and execute a non-gating job addressed to it alone
    And re-running the procedure against the finished node MUST change nothing
    and MUST refuse every step that would destroy its populated storage
    And the rehearsal's outcome MUST be recorded naming the procedure revision
    and the profile

The first stage is DRIVEN here — `storage-layout.sh --dry-run`, over a scratch
PATH in which every read-only probe is faked and every mutating command is a
TRIPWIRE that records and exits 0. Two properties come out of that which
nothing static can reach: that the plan a profile yields is byte-for-byte the
committed one (so "no step performed by hand" is a comparison rather than a
claim), and that a run against a node whose storage is already populated
REFUSES rather than proceeds.

What is NOT here. The stage-2, stage-3 and stage-4 artifacts are not driven:
each mutates a host by construction and the tree's own off-host suites
(`base-os-install-exit-tests.sh`, `provision-k3s-exit-tests.sh`,
`install-node-exit-tests.sh`) are where they are exercised. And the REHEARSAL
RECORD is not here at all — `SPECIFICATION/non-functional-requirements.md`
§"Runner-pool node rebuild recipe" puts it "in the plan store or on the owning
ledger item", both outside this tree, so asserting it against a committed file
would be asserting a copy rather than the record.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

pytestmark = pytest.mark.consumer

_REPO_ROOT = Path(__file__).resolve().parents[2]
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_PHASE0 = _K3S / "phase0-bare-metal"
_STORAGE_LAYOUT = _PHASE0 / "storage-layout.sh"
_PROFILES = _PHASE0 / "profiles"
_SERVER_PROFILE = _PROFILES / "poweredge-xubuntu.env"
_SERVER_PLAN = _PROFILES / "poweredge-xubuntu.expected-plan"
_AGENT_PROFILE = _PROFILES / "gmktec-xubuntu.env"
_KUEUE_DIR = _K3S / "phase2" / "kueue"

# The consent flag, and the two things it does NOT unlock.
_CONSENT = "--i-consent-to-destroy"
_REFUSED = "REFUSED"
_PRESERVED_KEY = "PRESERVED_PARTITIONS"

# Every mutating command the stage can reach, faked as a tripwire: a dry run
# that executed anything leaves this file non-empty. `apt-get` is here for the
# sharpest reason of the set — the machine running this suite is the one kind
# that really has it, so a preflight bug reaching an install would install
# packages onto a developer's own workstation.
_TRIPWIRE_TOOLS = (
    "sgdisk",
    "wipefs",
    "partprobe",
    "udevadm",
    "pvcreate",
    "vgcreate",
    "lvcreate",
    "mkswap",
    "mkfs.ext4",
    "mkfs.xfs",
    "mkfs.vfat",
    "apt-get",
)
# The read-only probes, faked to report a BARE node: no volume group, no
# logical volume, no filesystem signature. `blkid`'s "nothing there" is exit 2,
# which is its own spelling and not the others'.
_ABSENT_PROBES = ("lsblk", "pvs", "vgs", "lvs")

# The two commands the WHOLE-DEVICE plan takes and the free-space plan does
# not: erasing the target device's partition table, and creating the storage
# controller's virtual disk.
_ERASE = "sgdisk --zap-all"
_ADD_VIRTUAL_DISK = "add vd"

_PLAN_LINE = re.compile(r"^\+ (?P<command>.*)$", re.MULTILINE)
_NODE_NAME = re.compile(r"^NODE_NAME=(?P<node>\S+)\s*$", re.MULTILINE)
_HOSTNAME_SELECTOR = re.compile(r"^\s*kubernetes\.io/hostname:\s*(?P<node>\S+)\s*$", re.MULTILINE)
_NUMBERED_ARTIFACT = re.compile(r"^(?P<step>\d+)\. \*\*(?P<artifact>.+?)\*\*")
# The one section of the k3s README that IS the rebuild sequence. Scoping to it
# matters: the file carries other numbered lists (the k3s installer's own
# steps, for one), and reading the nearest list as the sequence would answer a
# different question convincingly.
_SEQUENCE_HEADING = "## Rebuild sequence"


def _fakes(*, root: Path, populated_device: str | None = None) -> Path:
    """A scratch PATH directory of faked probes and tripwired mutations.

    `populated_device` makes `blkid` report a partition table already on that
    device — which is what "the finished node" looks like to this stage, and
    the state its consent gate exists for.
    """
    directory = root / "bin"
    directory.mkdir(parents=True, exist_ok=True)
    tripwire = root / "tripwire"
    _ = tripwire.write_text("", encoding="utf-8")
    for tool in _TRIPWIRE_TOOLS:
        _write_tool(
            directory=directory,
            name=tool,
            body=f'printf "%s %s\\n" "$(basename "$0")" "$*" >> "{tripwire}"\nexit 0',
        )
    for tool in _ABSENT_PROBES:
        _write_tool(directory=directory, name=tool, body="exit 1")
    if populated_device is None:
        _write_tool(directory=directory, name="blkid", body="exit 2")
    else:
        _write_tool(
            directory=directory,
            name="blkid",
            body=(
                'for arg in "$@"; do dev="$arg"; done\n'
                f'if [ "$dev" = "{populated_device}" ]; then\n'
                '  case " $* " in *" PTTYPE "*) echo gpt; exit 0 ;; esac\n'
                "fi\n"
                "exit 2"
            ),
        )
    return directory


def _write_tool(*, directory: Path, name: str, body: str) -> None:
    """Write one executable fake onto the scratch PATH."""
    tool = directory / name
    _ = tool.write_text(f"#!/usr/bin/env bash\n{body}\n", encoding="utf-8")
    tool.chmod(0o755)


def _plan(
    *, root: Path, profile: Path, flags: list[str] | None = None, populated: str | None = None
) -> tuple[int, str]:
    """Run stage 1 in `--dry-run`; return (rc, combined output).

    `--dry-run` is what keeps this off any host by construction; the tripwires
    are the belt to that suspender, asserted separately.
    """
    directory = _fakes(root=root, populated_device=populated)
    env = dict(os.environ)
    env["PATH"] = f"{directory}{os.pathsep}{env.get('PATH', '')}"
    completed = subprocess.run(
        ["bash", str(_STORAGE_LAYOUT), "--dry-run", *(flags or []), str(profile)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
        timeout=300,
    )
    return completed.returncode, completed.stdout + completed.stderr


def _tripwire(*, root: Path) -> str:
    """Whatever a dry run actually executed — which must be nothing."""
    return (root / "tripwire").read_text(encoding="utf-8")


def _refusals(*, output: str) -> list[str]:
    """The refusal lines alone.

    The target has to be read off the REFUSED line ITSELF, not found loose in
    the output: the script prints a progress banner naming the device it is
    about to work on, so a refusal stripped of every target name still leaves
    that device's name somewhere in the capture. Asserting over the whole blob
    would certify the naming this scenario requires against a string the
    refusal did not write.
    """
    return [line for line in output.splitlines() if _REFUSED in line]


def test_the_rebuild_plan_is_the_committed_one_and_it_is_the_profile_s_not_the_script_s(
    *, tmp_path: Path
) -> None:
    """The scenario's "reach the profile's declared state with NO STEP PERFORMED BY HAND".

    THE WHOLE PLAN, AS AN EQUALITY: every mutating command stage 1 plans
    against a bare node, in order, compared against the plan committed beside
    the profile. An equality is what a subset assertion cannot do — a step
    silently added, dropped or reworded between two asserted rungs passes an
    ordered-subset check unnoticed — and it is the only form in which "the
    procedure and its profile produce the rebuild" is falsifiable at all.

    ONE PROCEDURE, ONE PROFILE PER NODE: the same script, handed the second
    node's profile, must plan that node's DIFFERENT shape — no controller
    virtual disk and no whole-device erase, because that node keeps the
    operating system it already runs. A second pool node is a second profile
    consumed by the same script, never a second script; if the two profiles
    produced the same plan, one of them would not be describing its own node.

    The run is a `--dry-run` with every mutating command tripwired and the
    tripwire asserted empty, so this proves what it proves without touching a
    disk. The scenario's re-run and refusal clauses are the sibling
    `test_re_running_against_a_populated_node_refuses_every_destructive_step_by_name`'s.
    """
    bare = tmp_path / "bare"
    rc, output = _plan(root=bare, profile=_SERVER_PROFILE)
    assert rc == 0, f"a dry run against a bare node must succeed; rc={rc} output={output}"
    planned = [match.group("command") for match in _PLAN_LINE.finditer(output)]
    expected = [
        line
        for line in _SERVER_PLAN.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert planned == expected, (
        f"the plan the recipe and this node's profile produce must be the committed one, "
        f"command for command: a rebuild is only reproducible from git while the whole "
        f"sequence is pinned, and an ordered-subset check would let a step be added, dropped "
        f"or reworded between two rungs unnoticed; planned={planned} expected={expected}"
    )
    assert _tripwire(root=bare) == "", (
        f"and a dry run must execute NOTHING — the plan is printed, not taken; "
        f"tripwire={_tripwire(root=bare)!r}"
    )

    agent = tmp_path / "agent"
    agent_rc, agent_output = _plan(root=agent, profile=_AGENT_PROFILE)
    assert agent_rc == 0, f"the second node's profile must plan cleanly too; rc={agent_rc}"
    agent_planned = [match.group("command") for match in _PLAN_LINE.finditer(agent_output)]
    assert agent_planned and agent_planned != planned, (
        f"one script, two profiles, two DIFFERENT plans — a second pool node is a second "
        f"profile, never a second script, and identical plans would mean one of the profiles "
        f"is not describing its own node; second plan={agent_planned}"
    )
    assert not any(
        _ERASE in command or _ADD_VIRTUAL_DISK in command for command in agent_planned
    ), (
        f"the node that KEEPS its operating system must plan neither a whole-device erase nor "
        f"a storage-controller virtual disk: that is the free-space plan's defining property, "
        f"and it is what makes the procedure usable on a node already carrying a root "
        f"filesystem; plan={agent_planned}"
    )
    assert any(_ERASE in command for command in planned) and any(
        _ADD_VIRTUAL_DISK in command for command in planned
    ), (
        f"while the node rebuilt from empty storage plans both — the contrast is what makes "
        f"the assertion above about the PROFILE rather than about the script; plan={planned}"
    )


def test_re_running_against_a_populated_node_refuses_every_destructive_step_by_name(
    *, tmp_path: Path
) -> None:
    """The scenario's "re-running MUST change nothing and MUST refuse every step that would destroy its populated storage".

    RE-RUNNING CHANGES NOTHING: run against a device that already carries a
    partition table — which is what the finished node looks like to this stage
    — and the destructive step must REFUSE, naming the target, and must stay
    refused when the consent names something else. A refusal that does not name
    its target is how an operator consents to the wrong volume.

    AND IT MUST STILL BE OPENABLE ON PURPOSE: consent naming exactly that
    target lets the deliberate rebuild through. A gate nobody can open is a
    gate that gets deleted, so asserting only the refusals would certify a
    posture the procedure could not actually hold.

    PRESERVATION OUTRANKS CONSENT: a partition the profile lists as preserved
    is refused BY NAME even when the invocation consents to destroying it, and
    the refusal names the key that protects it. That is the difference between
    "are you sure" and "not this one", and the free-space plan — a node rebuilt
    around the operating system it is running — rests entirely on the second.
    """
    finished = tmp_path / "finished"
    refused_rc, refused = _plan(root=finished, profile=_SERVER_PROFILE, populated="/dev/sda")
    refusals = _refusals(output=refused)
    assert refused_rc != 0 and any("/dev/sda" in line for line in refusals), (
        f"re-run against a node whose storage is already populated, the destructive step must "
        f"refuse and the REFUSAL ITSELF must NAME the target — a refusal that does not name it "
        f"lets an operator consent to the wrong volume; "
        f"rc={refused_rc} refusals={refusals} output={refused}"
    )
    assert _tripwire(root=finished) == "", (
        f"and the refused run must have executed nothing at all; "
        f"tripwire={_tripwire(root=finished)!r}"
    )

    elsewhere = tmp_path / "elsewhere"
    other_rc, other = _plan(
        root=elsewhere,
        profile=_SERVER_PROFILE,
        flags=[f"{_CONSENT}=/dev/sdz"],
        populated="/dev/sda",
    )
    assert other_rc != 0 and _REFUSED in other, (
        f"consent naming a DIFFERENT target must not grant this one, or the flag degrades "
        f"into a blanket 'yes' typed once; rc={other_rc} output={other}"
    )

    deliberate = tmp_path / "deliberate"
    consented_rc, consented = _plan(
        root=deliberate,
        profile=_SERVER_PROFILE,
        flags=[f"{_CONSENT}=/dev/sda"],
        populated="/dev/sda",
    )
    assert consented_rc == 0 and "consent given for /dev/sda" in consented, (
        f"and consent naming exactly that target must let the deliberate rebuild through: a "
        f"gate nobody can open on purpose is a gate that gets deleted; rc={consented_rc} "
        f"output={consented}"
    )

    preserved = _AGENT_PROFILE.read_text(encoding="utf-8")
    clobbering = tmp_path / "clobbering.env"
    _ = clobbering.write_text(
        re.sub(
            r"^VOLUME_GROUPS=.*$",
            "VOLUME_GROUPS=nvmea:/dev/nvme0n1p1",
            preserved,
            count=1,
            flags=re.MULTILINE,
        ),
        encoding="utf-8",
    )
    for flags in ([], [f"{_CONSENT}=/dev/nvme0n1p1"]):
        root = tmp_path / f"preserved{len(flags)}"
        preserved_rc, preserved_output = _plan(root=root, profile=clobbering, flags=flags)
        assert (
            preserved_rc != 0
            and _REFUSED in preserved_output
            and "/dev/nvme0n1p1" in preserved_output
            and _PRESERVED_KEY in preserved_output
        ), (
            f"a step naming a PRESERVED partition must be refused by name, and consent must "
            f"not unlock it — preservation is a different key, not a stronger flavour of "
            f"consent, and it is what stands between a re-run and the operating system the "
            f"free-space plan exists to keep; flags={flags} rc={preserved_rc} "
            f"output={preserved_output}"
        )
        assert _tripwire(root=root) == "", f"tripwire={_tripwire(root=root)!r}"


def test_every_node_the_pool_addresses_by_name_has_its_own_committed_profile() -> None:
    """§ the scenario's first Given, and its "addressed to it alone" clause.

    "one node rebuild procedure whose first stage is
    `ci-runner/k3s/phase0-bare-metal/` and ONE COMMITTED PROFILE PER POOL NODE."
    The first half is a property of the documented sequence: a rebuild whose
    step 1 is the k3s install reads as complete and silently rebuilds onto
    whatever disk was already there, which is exactly the gap this tree closed.

    The second half is only decidable against the nodes that actually exist,
    and the committed gitops is where they are named: a manifest that addresses
    a node by `kubernetes.io/hostname` — the mechanism by which a job is
    addressed to ONE node — names a node the pool has. Every such node must
    carry a profile, or that node is the one the procedure cannot rebuild, and
    the omission is invisible because everything else about the pool keeps
    working.
    """
    readme = (_K3S / "README.md").read_text(encoding="utf-8").splitlines()
    start = next(index for index, line in enumerate(readme) if line.startswith(_SEQUENCE_HEADING))
    end = next(
        index for index, line in enumerate(readme[start + 1 :], start + 1) if line.startswith("## ")
    )
    sequence = [
        (int(match.group("step")), match.group("artifact"))
        for line in readme[start:end]
        for match in [_NUMBERED_ARTIFACT.match(line)]
        if match is not None
    ]
    first = [artifact for step, artifact in sequence if step == 1]
    assert first and all("phase0-bare-metal/" in artifact for artifact in first), (
        f"the documented rebuild sequence must START at the bare-metal stage: a sequence "
        f"whose first step is the k3s install reads as a complete rebuild and quietly "
        f"assumes the storage it finds; first step(s)={first}"
    )

    profiled = {
        match.group("node")
        for path in sorted(_PROFILES.glob("*.env"))
        for match in [_NODE_NAME.search(path.read_text(encoding="utf-8"))]
        if match is not None
    }
    assert len(profiled) == len(list(_PROFILES.glob("*.env"))), (
        f"every committed profile must name its node, or the mapping below is a guess; "
        f"named={sorted(profiled)}"
    )

    addressed = {
        match.group("node")
        for path in sorted(_KUEUE_DIR.glob("*.yaml"))
        for match in _HOSTNAME_SELECTOR.finditer(path.read_text(encoding="utf-8"))
    }
    assert addressed, (
        f"at least one committed manifest must address a node by hostname — that selector IS "
        f"the mechanism for a job addressed to one node alone; searched="
        f"{_KUEUE_DIR.relative_to(_REPO_ROOT)}"
    )
    unprofiled = sorted(addressed - profiled)
    assert not unprofiled, (
        f"every node the pool addresses by name must have its own committed profile, or that "
        f"node cannot be rebuilt by the recipe and nothing about the running pool says so; "
        f"unprofiled={unprofiled} profiled={sorted(profiled)}"
    )
