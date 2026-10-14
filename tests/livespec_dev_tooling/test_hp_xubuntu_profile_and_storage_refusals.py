"""hp-xubuntu's profile, as the one parser reads it, and the partitions no stage may write.

WHAT THIS FILE GRADES (work-item livespec-dev-tooling-7we6po, Definition of Done
assertion 3). hp-xubuntu's committed profile must parse through the ONE shared
parser `ci-runner/k3s/phase0-bare-metal/profile.sh` carrying `CLUSTER_ROLE=agent`,
`ADMISSION_CAPACITY_C=0` and a non-empty `NODE_TAINTS` holding `node-role/ci`;
and the storage stage must refuse any step that would write to `/dev/sda1`,
`/dev/sda2`, `/dev/sdc1` or `/dev/sdc2` — the node's root, its EFI system
partition, its 160 GiB sandbox swap and the 3.6 TiB sandbox store its running
Fabro factory depends on.

THE PARSE IS RUN THROUGH THE PARSER, NOT RE-IMPLEMENTED. A reader that matched
`^KEY=value$` here would prove the file's TEXT and say nothing about what the
stages receive — defaults, emptiness rules and the posture refusals all live in
`profile.sh`, and it is `profile.sh`'s answer that every stage acts on. So a
three-line bash harness sources it, calls `profile_load`, and prints the
resulting `CFG` table; that printed table is what the assertions read.

THE THREE-WAY REFUSAL IS THE POINT OF THE POSTURE, AND IT IS TESTED BY REMOVAL.
`CI_NODE_FACILITIES=none` means "joins the pool, executes no CI job", and the
parser refuses it unless the profile ALSO declares no CI storage,
`ADMISSION_CAPACITY_C=0` and a `node-role/ci` taint. Asserting the three values
are present proves only that someone typed them; taking each one away in turn and
watching the parser refuse is what proves a node cannot be half-opened — which
is the property that makes "opening hp to CI later is a profile edit and an
apply, and nothing else" true rather than hopeful.

THE REFUSAL IS PROVED BY COUNTERFACTUAL, because the converged node plans
nothing. hp declares no tier, so stage 1 against its committed profile issues not
one mutating command and there is nothing for the preservation guard to catch —
`test_stage_one_plans_not_one_command_*` asserts exactly that. The guard matters
for the day the profile DOES declare a tier, so each refusal case takes hp's own
committed `PRESERVED_PARTITIONS` and points a volume group's physical volume at
one of the four protected partitions. That is the same shape
`storage-layout-exit-tests.sh` proves the fixture plan with, run here against the
committed data.

HOW IT STAYS OFF EVERY HOST. Every case runs `storage-layout.sh --dry-run`, which
prints mutating commands and executes none, on a scratch PATH where the read-only
probes answer nothing and every mutating tool is a tripwire. `test_the_dry_runs_*`
asserts the tripwire log stayed empty. Nothing runs as root and no device on this
machine is read.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PHASE0 = _REPO_ROOT / "ci-runner" / "k3s" / "phase0-bare-metal"
_PARSER = _PHASE0 / "profile.sh"
_STAGE_ONE = _PHASE0 / "storage-layout.sh"
_HP_PROFILE = _PHASE0 / "profiles" / "hp-xubuntu.env"

# The Definition of Done's own four partitions, in its own order.
_PROTECTED = ("/dev/sda1", "/dev/sda2", "/dev/sdc1", "/dev/sdc2")

# Read-only probes the stage reaches for, answered with nothing so the plan is
# the profile's and not this machine's; and the mutating tools, which must never
# be invoked at all.
_PROBE_TOOLS = ("lsblk", "blkid", "pvs", "vgs", "lvs", "findmnt")
_MUTATING_TOOLS = (
    "apt-get",
    "sgdisk",
    "partprobe",
    "wipefs",
    "pvcreate",
    "vgcreate",
    "lvcreate",
    "mkfs.ext4",
    "mkfs.xfs",
    "mkfs.vfat",
    "mkswap",
    "udevadm",
)

# The harness that reads a profile THROUGH the shared parser. `die` is defined
# first because `profile.sh` expects its caller to have supplied it — every
# rejection goes through it — and the sort makes the printed table stable.
_PARSE_HARNESS = """
die() { printf 'FATAL: %s\\n' "$*" >&2; exit 1; }
# shellcheck source=/dev/null
source "$1"
profile_load "$2"
for key in "${!CFG[@]}"; do printf '%s=%s\\n' "$key" "${CFG[$key]}"; done | sort
"""


def _parse(*, profile: Path) -> subprocess.CompletedProcess[str]:
    """Read `profile` through `profile.sh` and return the completed harness run."""
    return subprocess.run(
        ["bash", "-c", _PARSE_HARNESS, "harness", str(_PARSER), str(profile)],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )


def _parsed(*, profile: Path) -> dict[str, str]:
    """`profile`'s keys as the parser resolves them, refusing a profile it rejects."""
    completed = _parse(profile=profile)
    assert completed.returncode == 0, (
        f"{profile.name} must parse through {_PARSER.name} — every stage of the rebuild "
        f"reads it through that one parser, so a profile it rejects is a node no stage can "
        f"act on:\n{completed.stdout}{completed.stderr}"
    )
    return dict(
        line.split("=", 1) for line in completed.stdout.splitlines() if line and "=" in line
    )


def _refused(*, profile: Path, naming: str) -> None:
    """The parser must reject `profile`, and its message must name `naming`."""
    completed = _parse(profile=profile)
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode != 0
    ), f"{_PARSER.name} must REFUSE {profile.name}; it parsed it cleanly:\n{output}"
    assert naming in output, (
        f"{_PARSER.name}'s refusal must name {naming!r}, so an operator is told which key is "
        f"in the way rather than that something is;\noutput={output!r}"
    )


@pytest.fixture
def probe_path(*, tmp_path: Path) -> tuple[str, Path]:
    """A PATH whose probes answer nothing and whose mutating tools are tripwires."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log = tmp_path / "tripwire.log"
    for tool in _PROBE_TOOLS:
        fake = bin_dir / tool
        fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        fake.chmod(0o755)
    for tool in _MUTATING_TOOLS:
        fake = bin_dir / tool
        fake.write_text(
            f'#!/bin/sh\nprintf "{tool} %s\\n" "$*" >> "{log}"\nexit 0\n', encoding="utf-8"
        )
        fake.chmod(0o755)
    return f"{bin_dir}{os.pathsep}{os.environ['PATH']}", log


def _stage_one(
    *, profile: Path, probe_path: tuple[str, Path], consent: str | None = None
) -> subprocess.CompletedProcess[str]:
    """`storage-layout.sh --dry-run <profile>`, which executes nothing at all."""
    argv = ["bash", str(_STAGE_ONE), "--dry-run"]
    if consent is not None:
        argv.append(f"--i-consent-to-destroy={consent}")
    return subprocess.run(
        [*argv, str(profile)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={**os.environ, "PATH": probe_path[0]},
    )


def _clobbering_fixture(*, partition: str, tmp_path: Path) -> Path:
    """hp's committed profile, edited to declare a tier ON a protected partition.

    The ONE counterfactual this file needs, and it changes exactly what it must:
    the posture becomes `full` (the parser refuses a tier under `none`, which is
    the whole point of that posture) and one volume group's physical volume
    becomes `partition`. `PRESERVED_PARTITIONS`, `TARGET_DEVICE` and every other
    value stay as committed, so the refusal that fires is hp's own.
    """
    edited = []
    for line in _HP_PROFILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("CI_NODE_FACILITIES="):
            edited.append("CI_NODE_FACILITIES=full")
        elif line.startswith("PV_PARTLABEL="):
            edited.append("PV_PARTLABEL=lvm")
        elif line.startswith("VOLUME_GROUPS="):
            edited.append(f"VOLUME_GROUPS=nvmea:{partition}")
        elif line.startswith("LOGICAL_VOLUMES="):
            edited.append("LOGICAL_VOLUMES=nvmea:ci-cache:10GiB:ext4:ci-cache")
        elif line.startswith("ROLE_TIERS="):
            edited.append("ROLE_TIERS=ci-cache:nvmea")
        else:
            edited.append(line)
    fixture = tmp_path / f"hp-clobbering-{partition.replace('/', '-')}.env"
    fixture.write_text("\n".join(edited) + "\n", encoding="utf-8")
    return fixture


def _without(*, line_prefix: str, replacement: str, tmp_path: Path, name: str) -> Path:
    """hp's committed profile with one key's line replaced."""
    fixture = tmp_path / name
    fixture.write_text(
        "\n".join(
            replacement if line.startswith(line_prefix) else line
            for line in _HP_PROFILE.read_text(encoding="utf-8").splitlines()
        )
        + "\n",
        encoding="utf-8",
    )
    return fixture


# --- the parse half of the assertion ---------------------------------------


def test_the_committed_hp_profile_parses_as_a_closed_agent_at_capacity_zero() -> None:
    """The three values the Definition of Done names, as the ONE parser resolves them."""
    parsed = _parsed(profile=_HP_PROFILE)
    assert parsed["CLUSTER_ROLE"] == "agent", (
        f"hp joins the pool as an AGENT; the parser read CLUSTER_ROLE="
        f"{parsed['CLUSTER_ROLE']!r}"
    )
    assert parsed["ADMISSION_CAPACITY_C"] == "0", (
        f"hp must advertise NO churn slot, which is what keeps the cohort's quota at 44 "
        f"(poweredge 32 + gmktec 12 + hp 0) rather than changing the number the whole Kueue "
        f"derivation rests on; the parser read {parsed['ADMISSION_CAPACITY_C']!r}"
    )
    assert "node-role/ci=" in parsed["NODE_TAINTS"], (
        f"hp's NODE_TAINTS must be non-empty and carry a node-role/ci record: the zero "
        f"capacity stops Kueue's ADMISSION and only the taint stops the SCHEDULER; the "
        f"parser read {parsed['NODE_TAINTS']!r}"
    )
    assert parsed["NODE_TAINTS"].endswith(":NoSchedule"), (
        f"and the record's effect must be NoSchedule, which is what the Definition of Done "
        f"names and what `kubectl describe node` will report; got {parsed['NODE_TAINTS']!r}"
    )
    assert parsed["CI_NODE_FACILITIES"] == "none", (
        f"and the posture that ties the other three together must be `none`; the parser read "
        f"{parsed['CI_NODE_FACILITIES']!r}"
    )


def test_the_closed_posture_cannot_be_half_undone_one_key_at_a_time(*, tmp_path: Path) -> None:
    """Each leg of "taking nothing" removed in turn, and refused by name.

    This is what makes the posture a statement rather than three coincidences. A
    profile that declared no CI facilities while advertising churn slots would
    admit work it has nothing to run it with; one that left the taint off would
    be scheduled onto directly, past Kueue entirely.
    """
    _refused(
        profile=_without(
            line_prefix="ADMISSION_CAPACITY_C=",
            replacement="ADMISSION_CAPACITY_C=12",
            tmp_path=tmp_path,
            name="hp-advertising-capacity.env",
        ),
        naming="ADMISSION_CAPACITY_C must be 0",
    )
    _refused(
        profile=_without(
            line_prefix="NODE_TAINTS=",
            replacement="NODE_TAINTS=",
            tmp_path=tmp_path,
            name="hp-untainted.env",
        ),
        naming="must carry a node-role/ci=",
    )
    _refused(
        profile=_without(
            line_prefix="ROLE_TIERS=",
            replacement="ROLE_TIERS=ci-cache:nvmea",
            tmp_path=tmp_path,
            name="hp-declaring-a-tier.env",
        ),
        naming="'ROLE_TIERS' must be empty",
    )


def test_a_posture_the_parser_does_not_know_is_refused_rather_than_defaulted(
    *, tmp_path: Path
) -> None:
    """The typo arm: `non` must not read as "not none" and build a tier carrier.

    `CI_NODE_FACILTIES=none` (the key misspelt) is already caught as an unknown
    key. `CI_NODE_FACILITIES=non` would not be, and the consequence of reading it
    as the default is a factory host provisioned as a CI node.
    """
    _refused(
        profile=_without(
            line_prefix="CI_NODE_FACILITIES=",
            replacement="CI_NODE_FACILITIES=non",
            tmp_path=tmp_path,
            name="hp-misspelt-posture.env",
        ),
        naming="CI_NODE_FACILITIES must be 'full' or 'none', got 'non'",
    )


# --- the storage half of the assertion -------------------------------------


def test_stage_one_plans_not_one_command_against_the_committed_hp_profile(
    *, probe_path: tuple[str, Path]
) -> None:
    """A node that declares no CI storage is converged, and the stage says so.

    "Re-runnable against a node already in its profile's declared state, changing
    nothing" is what the runner-pool node rebuild recipe in
    `SPECIFICATION/non-functional-requirements.md` requires of every stage, and a
    node with nothing declared is in that state from the start. Before this gate
    existed the stage planned an `apt-get install gdisk parted lvm2` here — an
    install on a factory host for a layout it does not have.
    """
    completed = _stage_one(profile=_HP_PROFILE, probe_path=probe_path)
    assert completed.returncode == 0, (
        f"stage 1 against hp's committed profile must exit 0:\n"
        f"{completed.stdout}{completed.stderr}"
    )
    planned = [line for line in completed.stdout.splitlines() if line.startswith("+ ")]
    assert planned == [], (
        f"stage 1 must plan NO mutating command on a node declaring CI_NODE_FACILITIES=none; "
        f"it planned {planned}"
    )
    assert "CI_NODE_FACILITIES=none" in completed.stdout, (
        f"and it must say WHY it has nothing to do, naming the key: a stage that printed "
        f"nothing would be indistinguishable from one that failed to read the profile;\n"
        f"stdout={completed.stdout!r}"
    )


@pytest.mark.parametrize("partition", _PROTECTED)
def test_any_stage_that_would_write_to_a_protected_partition_is_refused(
    *, partition: str, probe_path: tuple[str, Path], tmp_path: Path
) -> None:
    """hp's root, its ESP, its sandbox swap and its 3.6 TiB sandbox store.

    `/dev/sda1` and `/dev/sda2` are the operating system this host boots;
    `/dev/sdc1` is the 160 GiB swap the sandbox containers rely on and `/dev/sdc2`
    the store at `/srv/sandbox-storage` that every Fabro run's image layers live
    on. Losing any of the four takes the factory down, and the first two take the
    host with it.

    The refusal is UNCONDITIONAL and is not a consent question — see the
    companion test below.
    """
    fixture = _clobbering_fixture(partition=partition, tmp_path=tmp_path)
    completed = _stage_one(profile=fixture, probe_path=probe_path)
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode != 0
    ), f"a plan that would write to {partition} must exit non-zero; it exited 0:\n{output}"
    assert "REFUSED" in output and partition in output, (
        f"and the refusal must name {partition}, so an operator reading it knows which "
        f"partition was protected rather than that something was;\noutput={output!r}"
    )
    assert "PRESERVED_PARTITIONS" in output, (
        f"and must name the KEY that protected it, which is the only thing that tells an "
        f"operator where the decision lives;\noutput={output!r}"
    )


@pytest.mark.parametrize("partition", _PROTECTED)
def test_consent_does_not_unlock_a_protected_partition(
    *, partition: str, probe_path: tuple[str, Path], tmp_path: Path
) -> None:
    """Preservation outranks consent, and the WORDING has to say so.

    `--i-consent-to-destroy` grants one destructive step against a target the
    profile is willing to lose. A `PRESERVED_PARTITIONS` entry is a target the
    profile is NOT willing to lose, so no flag unlocks it. Asserting the wording
    and not merely the exit code is the point: a refusal that advised
    `--i-consent-to-destroy=/dev/sdc2` would be advice that the key can be
    overridden, which is the one thing it promises it cannot.
    """
    fixture = _clobbering_fixture(partition=partition, tmp_path=tmp_path)
    completed = _stage_one(profile=fixture, probe_path=probe_path, consent=partition)
    output = completed.stdout + completed.stderr
    assert (
        completed.returncode != 0 and "REFUSED" in output
    ), f"naming {partition} in --i-consent-to-destroy must not unlock it:\n{output}"
    assert (
        "no --i-consent-to-destroy unlocks it" in output
    ), f"and the refusal must say so in its own words;\noutput={output!r}"


def test_the_dry_runs_executed_not_one_mutating_command(
    *, probe_path: tuple[str, Path], tmp_path: Path
) -> None:
    """The guard that makes every case above safe to run anywhere."""
    _stage_one(profile=_HP_PROFILE, probe_path=probe_path)
    for partition in _PROTECTED:
        _stage_one(
            profile=_clobbering_fixture(partition=partition, tmp_path=tmp_path),
            probe_path=probe_path,
        )
    log = probe_path[1]
    executed = log.read_text(encoding="utf-8") if log.exists() else ""
    assert executed == "", (
        f"a `--dry-run` must print its plan and execute NOTHING; these invocations ran:\n"
        f"{executed}"
    )
