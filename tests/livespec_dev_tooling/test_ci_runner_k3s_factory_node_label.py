"""Every pool node's k3s install plan carries the FACTORY node label; hp-xubuntu's joins.

WHY THIS FILE EXISTS (work-item livespec-dev-tooling-7we6po, maintainer rulings
2026-10-12 and 2026-10-13 on epic livespec-sqvj7p). `hp-xubuntu` joins the k3s
pool as a FULL agent but CLOSED TO CI by its committed profile — a
`node-role/ci` `NoSchedule` taint plus `ADMISSION_CAPACITY_C=0`, so the cohort's
churn-slot quota stays 44 — and all THREE pool nodes carry a per-node FACTORY
label that the kubernetes-sandbox-backend plugin will select on. The label is a
fact of each node's committed profile (`FACTORY_NODE`), rendered by the ONE
procedure, so a fourth node is a fourth profile and never a fourth script
(`SPECIFICATION/non-functional-requirements.md` §"Runner-pool node rebuild
recipe", "One profile per node").

WHY A PYTEST FILE AND NOT ONLY `provision-k3s-exit-tests.sh`. That shell suite
is the artifact the Definition of Done names and it is extended alongside this
file — but nothing in `just check` runs it, so a regression in it is a
regression nobody is told about. These assertions ride the gated suite instead,
over the SAME `--dry-run` the shell suite drives, so the plan an operator reads
is checked on every commit.

HOW IT STAYS OFF EVERY HOST. Every case runs `provision-k3s.sh --dry-run`, which
by construction executes no step, on a scratch PATH of TRIPWIRES for the
host-mutating tools the steps underneath would reach for. `test_the_dry_runs_*`
asserts the tripwire log stayed empty, so a plan that executed something fails
here rather than on a node.

THE ONE SUBSTITUTION, AND WHY IT IS NOT A CHEAT — the same one
`provision-k3s-exit-tests.sh` §E makes. An agent profile names
`CLUSTER_TOKEN_FILE` as a path ON THE NODE holding a cluster credential this
tree does not carry, and `provision-k3s.sh` refuses an absent token file in
`--dry-run` too (on purpose: a plan that could not have run must not be printed
as though it could). So each agent profile is copied with that ONE key
redirected at a scratch `0600` file, and `test_only_the_token_file_line_*`
asserts it is the only line that differs.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_K3S = _REPO_ROOT / "ci-runner" / "k3s"
_SCRIPT = _K3S / "provision-k3s.sh"
_PROFILES = _K3S / "phase0-bare-metal" / "profiles"

# The label this work-item introduces, stated because the Definition of Done
# asks for "the factory node label" and the key is this change's to choose. It
# is spelled in the `ci-runner.io/` namespace beside the pool's existing
# `ci-runner.io/cache-tier-carrier`, and the script is asserted to define it
# exactly once below, so this stays the only place it is written down twice.
_FACTORY_LABEL = "ci-runner.io/factory=true"

# hp-xubuntu's own measured facts, from the read-only read of 2026-10-13 the
# work-item carries. Stated rather than derived: the whole point of the
# assertions is that the committed profile yields THESE, so reading them back
# out of the profile would assert nothing.
_HP = "hp-xubuntu"
_HP_JOIN = "https://192.168.1.200:6443"
_HP_NODE_IP = "192.168.1.4"
_HP_NODE_CIDR = "192.168.1.4/24"
_HP_TAINT = "node-role/ci=factory:NoSchedule"
_HP_DATA_DIR = "/srv/sandbox-storage/k3s"

# The host-mutating tools the steps underneath the plan reach for. A dry run
# must invoke none of them.
_TRIPWIRE_TOOLS = ("curl", "k3s", "kubectl", "helm", "install", "chmod", "tar", "findmnt")

_TOKEN_FILE_LINE = re.compile(r"^CLUSTER_TOKEN_FILE=.*$", re.MULTILINE)
_CLUSTER_ROLE_LINE = re.compile(r"^CLUSTER_ROLE=(?P<role>.*)$", re.MULTILINE)
_PLAN_COMMAND_LINE = re.compile(r"^ {5}\+ (?P<command>.*)$", re.MULTILINE)


def _committed_profiles() -> dict[str, Path]:
    """Every committed phase0 profile, by node name."""
    profiles = {path.stem: path for path in sorted(_PROFILES.glob("*.env"))}
    assert profiles, f"the committed node profiles must still live in {_PROFILES}"
    return profiles


def _hp_profile() -> Path:
    """hp-xubuntu's committed profile, refused by name when it does not exist yet."""
    profile = _PROFILES / f"{_HP}.env"
    assert profile.is_file(), (
        f"{profile.relative_to(_REPO_ROOT)} must be committed: hp-xubuntu joins the pool as "
        f"a second AGENT profile consumed by the one procedure, never as a second procedure "
        f"(SPECIFICATION/non-functional-requirements.md §'Runner-pool node rebuild recipe')"
    )
    return profile


@pytest.fixture
def tripwire_path(*, tmp_path: Path) -> tuple[str, Path]:
    """A PATH whose host-mutating tools append to a log instead of running."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    log = tmp_path / "tripwire.log"
    for tool in _TRIPWIRE_TOOLS:
        fake = bin_dir / tool
        fake.write_text(
            f'#!/bin/sh\nprintf "{tool} %s\\n" "$*" >> "{log}"\nexit 0\n', encoding="utf-8"
        )
        fake.chmod(0o755)
    return f"{bin_dir}{os.pathsep}{os.environ['PATH']}", log


def _runnable_copy(*, profile: Path, tmp_path: Path) -> Path:
    """`profile` with its `CLUSTER_TOKEN_FILE` redirected at a scratch 0600 file.

    Only an AGENT profile names one; a server's key is empty and is left exactly
    as committed, so a server's plan is built from the committed bytes entirely.
    """
    text = profile.read_text(encoding="utf-8")
    role = _CLUSTER_ROLE_LINE.search(text)
    assert role is not None, f"{profile.name} must declare CLUSTER_ROLE"
    if role["role"] != "agent":
        return profile
    token = tmp_path / f"{profile.stem}-join-token"
    token.write_text("K10deadbeef::server:notasecret\n", encoding="utf-8")
    token.chmod(0o600)
    copy = tmp_path / profile.name
    copy.write_text(
        _TOKEN_FILE_LINE.sub(f"CLUSTER_TOKEN_FILE={token}", text, count=1), encoding="utf-8"
    )
    return copy


def _dry_run(*, profile: Path, tripwire_path: tuple[str, Path], tmp_path: Path) -> str:
    """`provision-k3s.sh --dry-run <profile>`, which executes nothing at all."""
    runnable = _runnable_copy(profile=profile, tmp_path=tmp_path)
    completed = subprocess.run(
        ["bash", str(_SCRIPT), "--dry-run", str(runnable)],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
        env={**os.environ, "PATH": tripwire_path[0]},
    )
    output = completed.stdout + completed.stderr
    assert completed.returncode == 0, (
        f"`provision-k3s.sh --dry-run {profile.name}` must exit 0 — a plan an operator "
        f"cannot be handed is a node that cannot be rebuilt:\n{output}"
    )
    return output


def _install_command(*, output: str) -> str:
    """The ONE k3s install command the printed plan carries."""
    commands = _PLAN_COMMAND_LINE.findall(output)
    assert len(commands) == 1, (
        f"the plan must carry exactly one `+ `-prefixed install command; found "
        f"{len(commands)}. This reader cannot assert against a plan it cannot locate;\n"
        f"output={output!r}"
    )
    return commands[0]


# --- the Definition of Done's first assertion ------------------------------


def test_every_committed_pool_profile_plans_the_factory_node_label(
    *, tripwire_path: tuple[str, Path], tmp_path: Path
) -> None:
    """All three nodes carry the factory label: poweredge, gmktec AND hp.

    The maintainer's ruling is that the label is per-node and on every pool node,
    because the kubernetes-sandbox-backend plugin selects on it and poweredge
    stays untainted. So this is asserted over the committed set rather than over
    a list this file keeps — a fourth profile is covered the day it lands.
    """
    _hp_profile()
    for node, profile in sorted(_committed_profiles().items()):
        command = _install_command(
            output=_dry_run(profile=profile, tripwire_path=tripwire_path, tmp_path=tmp_path)
        )
        assert f"--node-label {_FACTORY_LABEL}" in command, (
            f"{node}'s install plan must register the factory node label "
            f"{_FACTORY_LABEL!r}: the sandbox backend selects factory capacity on it, and a "
            f"node that joins without it is invisible to that selector;\ncommand={command!r}"
        )


def test_the_hp_plan_is_the_agent_join_its_measured_facts_imply(
    *, tripwire_path: tuple[str, Path], tmp_path: Path
) -> None:
    """hp joins the first node's cluster, pinned, tainted, and on the sandbox disk.

    `--node-ip` is PINNED and not inferred because hp's wired `enp11s0` and its
    wireless `wlp10s0` are both on 192.168.1.0/24: a node that registered on the
    wireless address would be one the cluster cannot reach it on.
    """
    output = _dry_run(profile=_hp_profile(), tripwire_path=tripwire_path, tmp_path=tmp_path)
    command = _install_command(output=output)
    for fragment in (
        f"agent --server {_HP_JOIN}",
        f"--node-ip {_HP_NODE_IP}",
        f"--node-taint {_HP_TAINT}",
        f"--data-dir {_HP_DATA_DIR}",
        f"--node-label {_FACTORY_LABEL}",
    ):
        assert (
            fragment in command
        ), f"hp's agent install command must carry {fragment!r};\ncommand={command!r}"
    assert _HP_NODE_CIDR not in command, (
        f"`--node-ip` must be the BARE address: the netplan CIDR is what the base-OS stage "
        f"writes and what k3s rejects;\ncommand={command!r}"
    )
    assert f"node:     {_HP}" in output and "role:     agent" in output, (
        f"the plan header must state the node and the role it read from the profile, so an "
        f"operator reading it knows which machine it is for;\noutput={output!r}"
    )


def test_a_profile_that_declares_no_factory_node_plans_no_factory_label(
    *, tripwire_path: tuple[str, Path], tmp_path: Path
) -> None:
    """The control arm: the label must come from the PROFILE, not from the script.

    Without this every assertion above would pass against a script that appended
    the label unconditionally, and `FACTORY_NODE` would be decoration.
    """
    source = _hp_profile().read_text(encoding="utf-8")
    assert "FACTORY_NODE=true" in source, (
        f"hp's profile must declare FACTORY_NODE=true — the key is what the label is "
        f"rendered from;\nprofile={source!r}"
    )
    fixture = tmp_path / "not-a-factory.env"
    fixture.write_text(source.replace("FACTORY_NODE=true", "FACTORY_NODE=false"), encoding="utf-8")
    command = _install_command(
        output=_dry_run(profile=fixture, tripwire_path=tripwire_path, tmp_path=tmp_path)
    )
    assert _FACTORY_LABEL not in command, (
        f"a node whose profile declares FACTORY_NODE=false must plan no factory label at "
        f"all;\ncommand={command!r}"
    )


def test_the_factory_label_is_written_down_once_in_the_procedure(
    *, tripwire_path: tuple[str, Path], tmp_path: Path
) -> None:
    """One source for the label's spelling, in the script that renders it.

    The Ansible reconcile that keeps the label on an ALREADY-JOINED node reads it
    from its own role defaults — a second spelling there is a different fact the
    day one of them is edited, which is exactly how a retired taint came back on
    gmktec (livespec-dev-tooling-yapwva). `tests/livespec_dev_tooling/
    test_ci_pool_factory_only_agent_roles.py` holds the two to agreement.
    """
    del tripwire_path, tmp_path
    body = _SCRIPT.read_text(encoding="utf-8")
    occurrences = body.count(_FACTORY_LABEL)
    assert occurrences == 1, (
        f"{_SCRIPT.name} must spell {_FACTORY_LABEL!r} exactly once — as the constant both "
        f"role's install commands read; found {occurrences}"
    )


def test_the_dry_runs_executed_not_one_host_mutating_command(
    *, tripwire_path: tuple[str, Path], tmp_path: Path
) -> None:
    """The guard that makes every case above safe to run anywhere."""
    for profile in sorted(_committed_profiles().values()):
        _dry_run(profile=profile, tripwire_path=tripwire_path, tmp_path=tmp_path)
    log = tripwire_path[1]
    executed = log.read_text(encoding="utf-8") if log.exists() else ""
    assert executed == "", (
        f"a `--dry-run` must print its plan and execute NOTHING; these invocations ran:\n"
        f"{executed}"
    )


def test_only_the_token_file_line_differs_from_each_committed_agent_profile(
    *, tmp_path: Path
) -> None:
    """The substitution above is one line, and the committed value is the node's own path."""
    for node, profile in sorted(_committed_profiles().items()):
        text = profile.read_text(encoding="utf-8")
        role = _CLUSTER_ROLE_LINE.search(text)
        assert role is not None
        if role["role"] != "agent":
            continue
        assert "CLUSTER_TOKEN_FILE=/etc/rancher/k3s/agent-join-token" in text, (
            f"{node}'s profile must name the join token's path ON THE NODE; this tree carries "
            f"no secret and the token is read by k3s at run time"
        )
        copy = _runnable_copy(profile=profile, tmp_path=tmp_path)
        differing = [
            (before, after)
            for before, after in zip(
                text.splitlines(), copy.read_text(encoding="utf-8").splitlines(), strict=True
            )
            if before != after
        ]
        assert len(differing) == 1 and differing[0][0].startswith("CLUSTER_TOKEN_FILE="), (
            f"only {node}'s CLUSTER_TOKEN_FILE line may be redirected; every other value in "
            f"the asserted plan is the committed one. Differing: {differing}"
        )
        assert stat.S_IMODE((tmp_path / f"{node}-join-token").stat().st_mode) == 0o600, (
            "the scratch token must be owner-only, or the script refuses it for the reason "
            "it exists to refuse"
        )
