"""The docker_engine acceptance harness is told which KVM host it runs on.

A machine is bound ONLY through the inventory's host groups and host variables
(livespec-dev-tooling-prdxxe). The harness broke that in two places at once: the
FAULTS case scripts carried one machine's inventory name as an ssh `ProxyJump`
target AND as a directory component of the guest-key path, and
`acceptance/inventory-kvm.yml` carried the same name as a value eight times over.
Which machine is the KVM acceptance host is the inventory's decision
(`ansible/docker-engine-acceptance.yml` says so in as many words, and the key the
play fetches is already named after `inventory_hostname`), so the harness reads
that one fact from a variable and nothing in it names a machine.

The scripts are RUN rather than read for the refusal: the claim is that an
un-told harness stops BEFORE it reaches anything, and reading a shell script
cannot establish that. Running each with the variable absent costs nothing — the
refusal is the first thing past the `cd` — and no VM, no host and no ssh is
contacted. `inventory-kvm.yml` is read, because it is data.

Work-item: livespec-dev-tooling-mavj5i. Plan: livespec-orchestrator-beads-fabro
`petri-factory-on-gmktec`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

__all__: list[str] = []

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ACCEPTANCE = _REPO_ROOT / "ansible" / "roles" / "docker_engine" / "acceptance"
_FAULTS = _ACCEPTANCE / "faults"
_INVENTORY_KVM = _ACCEPTANCE / "inventory-kvm.yml"
_HOST_VARS = _REPO_ROOT / "ansible" / "inventory" / "host_vars"

# The one variable the harness is told, spelled once. The inventory reads it from
# the environment and the case scripts read it from the same place, so the
# harness has ONE source for the fact rather than one per file.
_KVM_HOST_VAR = "DOCKER_ENGINE_ACCEPTANCE_KVM_HOST"

# Every case script that reaches the guests through the KVM host — the four that
# carried the machine's name, plus `p05_p06.sh`, which sources `lib.sh` and so
# inherits the refusal rather than repeating it.
_HOST_REACHING_SCRIPTS = (
    "lib.sh",
    "h02.sh",
    "h03_h04.sh",
    "h04b.sh",
    "p05_p06.sh",
)


def _inventory_hosts() -> frozenset[str]:
    """Every machine the fleet inventory binds, read from its own `host_vars` stems."""
    stems = frozenset(path.stem for path in _HOST_VARS.glob("*.yml"))
    assert stems, "ansible/inventory/host_vars must bind at least one machine"
    return stems


def _carries_values(*, path: Path) -> bool:
    """Whether this file is one the harness ACTS on, rather than one it documents.

    An executable — by mode bit or by shebang, because the FAULTS tree holds both
    — and the harness inventories. `FAULTS.md` and `faults/README.md` are prose
    about the suite, and prose that names the machine a converge targets is
    provenance, which the maintainer ruled stays (livespec-dev-tooling-prdxxe).
    """
    return (
        bool(path.stat().st_mode & 0o111)
        or path.read_bytes().startswith(b"#!")
        or path.suffix in (".yml", ".yaml", ".j2")
    )


def _machine_names_on_value_lines(*, path: Path) -> list[str]:
    """Inventory machine names on this file's non-comment lines, line-numbered.

    Comments are provenance, not placement, and stay: the maintainer ruled so on
    livespec-dev-tooling-prdxxe. A `#` or `;` line is skipped for that reason, and
    everything else in the file is a value the harness acts on.
    """
    hosts = _inventory_hosts()
    hits: list[str] = []
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if raw.lstrip().startswith(("#", ";")):
            continue
        hits.extend(
            f"{path.relative_to(_REPO_ROOT)}:{number}:{host}"
            for host in sorted(hosts)
            if host in raw
        )
    return hits


def _run_without_the_kvm_host(*, script: Path) -> tuple[int, str]:
    """Run one case script with `DOCKER_ENGINE_ACCEPTANCE_KVM_HOST` absent."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("COVERAGE_", "COV_CORE_"))}
    env.pop(_KVM_HOST_VAR, None)
    completed = subprocess.run(
        ["bash", str(script)],
        cwd=str(_REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout + completed.stderr


def test_bash_is_available_to_run_the_shipped_case_scripts() -> None:
    """The lens this suite reads the scripts through, named rather than assumed."""
    assert shutil.which("bash") is not None


@pytest.mark.parametrize("name", _HOST_REACHING_SCRIPTS)
def test_a_case_script_refuses_when_no_kvm_host_was_supplied(*, name: str) -> None:
    """Refuse first, naming the variable — never guess which machine hosts the VMs.

    The removed literal could not fail usefully: pointed at a machine that is not
    this harness's KVM host, every case would fail at its first ssh with a
    connection error, which reads as a broken VM rather than as a harness nobody
    told where to run.
    """
    code, output = _run_without_the_kvm_host(script=_FAULTS / name)

    assert code != 0
    assert _KVM_HOST_VAR in output


def test_no_executable_or_inventory_in_the_acceptance_tree_names_a_machine() -> None:
    """The whole tree, not just the files that were noticed.

    Asserted over the directory rather than over a list of filenames because the
    defect's shape is a COPY: `lib.sh`'s two lines were duplicated into three
    sibling case scripts, and a fourth sibling (`h02.sh`) was missed by the audit
    that found the other three.
    """
    hits = [
        hit
        for path in sorted(_ACCEPTANCE.rglob("*"))
        if path.is_file() and _carries_values(path=path)
        for hit in _machine_names_on_value_lines(path=path)
    ]

    assert hits == []


def test_the_harness_inventory_reads_the_kvm_host_from_its_one_variable() -> None:
    """The inventory supplies the fact; the key directory is DERIVED from it.

    The directory is the half that is easy to leave behind: the play fetches the
    guest key to `~/.cache/docker-engine-guard-acceptance/<inventory_hostname>/`,
    so a harness that read the host from a variable and kept the directory literal
    would look clean and still break on any other machine.
    """
    inventory = _INVENTORY_KVM.read_text(encoding="utf-8")

    assert f"'{_KVM_HOST_VAR}'" in inventory
    assert "{{ docker_engine_acceptance_kvm_host }}" in inventory
    assert "docker_engine_acceptance_key_dir:" in inventory
    assert "{{ docker_engine_acceptance_key_dir }}/id_ed25519" in inventory
