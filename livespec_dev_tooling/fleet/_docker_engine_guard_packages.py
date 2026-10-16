"""The Docker engine install guard's fenced, audited package step.

The real host's `install_packages` seam calls `run_package_step` here, so
the fenced, audited transaction — the simulated transaction against the
committed allowlist, the SHA256 and maintainer-script digests, `dpkg -i`
under `DPKG_FRONTEND_LOCKED=1`, and the interrupted-install recovery —
lives in this module without reopening the guard module or the host
module.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Package fence". The step is inert
by construction: the guard drop-ins are in place before it runs, so the
postinst's start finds its condition unmet.

What belongs to the ROLE and not here: the apt timers, the wait for the
dpkg frontend lock, and the post-install `systemctl daemon-reload` (there
is no systemd unit-directory dpkg trigger on this OS, per design F6). The
role runs them AROUND this step, which assumes the frontend lock is
already held — see `_FENCED_ENV`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from livespec_dev_tooling.fleet._docker_engine_guard_package_audit import (
    Audit,
    InstalledPackage,
    audit_transaction,
    load_package_inputs,
    read_installed,
)
from livespec_dev_tooling.fleet._docker_engine_guard_package_runner import (
    COMMAND_TIMEOUT_SECONDS,
    INSTALL_TIMEOUT_SECONDS,
    TimedCommand,
    TimedRunner,
    default_runner,
)
from livespec_dev_tooling.fleet._docker_engine_guard_state import write_durable

__all__: list[str] = [
    "INTENDED_FILE",
    "PackageStepResult",
    "run_package_step",
]

# What tells dpkg that its caller already holds the frontend lock — the
# documented way for a frontend holding it to call dpkg (design R6). The
# role's lock-holding helper has held that lock since before the audit,
# so without this the install would block on the fence protecting it.
_FENCED_ENV: Final[dict[str, str]] = {"DPKG_FRONTEND_LOCKED": "1"}

# The provenance record design R7 requires: written into the run's own
# directory BEFORE the first package mutation, so a run interrupted
# anywhere in the install leaves behind what it intended to install.
INTENDED_FILE: Final[str] = "intended.json"

# The three states an interrupted UNPACK leaves a package in, and the only
# ones design F6 allows `dpkg --configure` to be aimed at. Narrow on
# purpose: `--configure -a` would adopt whatever else the host has left
# pending, which is the one thing the recovery branch must not do.
_RECOVERABLE_STATES: Final[frozenset[str]] = frozenset(
    {
        "half-configured",
        "half-installed",
        "unpacked",
    }
)

# The two states a helper killed during trigger processing leaves behind.
# Neither is broken enough for `--configure` nor finished enough to be
# installed over, so design G7 completes them with `--triggers-only`.
_TRIGGER_STATES: Final[frozenset[str]] = frozenset(
    {
        "triggers-awaited",
        "triggers-pending",
    }
)

# What a package dpkg holds nothing for reads as. A name `dpkg --audit`
# reported that the query did not carry then falls into no recovery state
# at all, rather than needing a second branch at every comparison.
_UNHELD: Final[InstalledPackage] = InstalledPackage(version="", status="")

# The one dpkg status that means a package is finished: not merely
# present, but unpacked AND configured. Every other status an audited
# package can hold is a transaction somebody did not complete, so it is
# the recovery branch's business and never evidence of an install.
_SETTLED: Final[str] = "installed"


@dataclass(frozen=True, kw_only=True)
class PackageStepResult:
    """What the step installed, or the refusal that stopped it before it did."""

    refusal: str | None = None
    installed: tuple[str, ...] = ()


def _addition_pairs(*, audit: Audit) -> tuple[tuple[str, str], ...]:
    """Each audited addition split back into its package name and its version.

    The additions are carried as `package=version` because that is the
    shape the post-install difference is compared in; the two halves are
    needed separately wherever dpkg's own table is indexed by name.
    """
    return tuple(
        (name, version)
        for name, _, version in (addition.partition("=") for addition in audit.additions)
    )


def _already_settled(*, audit: Audit, installed: Mapping[str, InstalledPackage]) -> bool:
    """Whether the host already holds every audited addition, finished.

    Design Mechanism 6's "packages installed" row, and the condition that
    makes this step idempotent. EVERY addition has to be settled at the
    audited version, not merely some: a host holding one of two is a
    transaction that has to finish, and finishing it is the install's own
    job rather than something to report as already done.

    The STATUS is part of the comparison and not an afterthought. A
    package left `unpacked` or `half-configured` by an interrupted
    install sits in dpkg's table at exactly the audited version, so a
    version-only test would read it as finished and skip the very
    transaction that has to complete it.
    """
    return all(
        installed.get(name, _UNHELD) == InstalledPackage(version=version, status=_SETTLED)
        for name, version in _addition_pairs(audit=audit)
    )


def _expected_difference(
    *, audit: Audit, before: Mapping[str, InstalledPackage]
) -> tuple[str, ...]:
    """The audited additions that can still APPEAR in dpkg's table, sorted.

    The difference below is computed as "in the after side, absent from
    the before side", so an audited package dpkg already holds a row for
    can never appear in it — whether that row is a settled install from
    an earlier run or the `unpacked` remains of an interrupted one. The
    whole audited set is therefore the wrong comparand on any host that
    is not bare, which is what made every re-run refuse.
    """
    return tuple(
        sorted(
            f"{name}={version}"
            for name, version in _addition_pairs(audit=audit)
            if name not in before
        )
    )


def _difference_refusal(
    *,
    expected: tuple[str, ...],
    before: Mapping[str, InstalledPackage],
    after: Mapping[str, InstalledPackage],
) -> str | None:
    """The post-install difference, unless it is exactly the additions expected.

    The audit cleared ONE transaction, and this difference is the only
    evidence that the transaction which actually ran was that one. So it
    is COMPARED with those additions rather than merely inspected for
    them: a dpkg run that also landed a package nobody audited — a
    dependency unpacked from a stale archive left in the cache, a
    resolver decision the simulation did not predict — raises no other
    signal at all.
    """
    difference = tuple(
        sorted(f"{name}={row.version}" for name, row in after.items() if name not in before)
    )
    if difference != expected:
        return (
            f"the post-install package difference {difference} is not the audited "
            f"additions {expected} this host did not already hold"
        )
    return None


def _recorded_packages(*, runs: Path) -> frozenset[str]:
    """Every package ANY guard run on this host recorded as intended.

    The union, not this run's own record, and that is implementation
    rider point 4: a rollback from `publishing` leaves the PREVIOUS run's
    packages part-installed, and a recovery keyed to the current run's id
    would read them as foreign and strand the host for every later run.

    A record that cannot be parsed is skipped rather than refused on: an
    intended record interrupted mid-write is not evidence of a foreign
    package, and the names it would have carried are already covered by
    the refusal below if nothing else accounts for them.
    """
    names: set[str] = set()
    for record in sorted(runs.glob(f"*/{INTENDED_FILE}")):
        try:
            payload = json.loads(record.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        names.update(str(addition).split("=")[0] for addition in payload["additions"])
    return frozenset(names)


def _flagged_packages(*, runner: TimedRunner) -> tuple[str, ...]:
    """Every package `dpkg --audit` names as needing attention.

    The report's headers wrap onto unindented continuation lines and only
    the package rows are indented, so the indent is what picks the names
    out of it.
    """
    report = runner(
        command=TimedCommand(argv=("dpkg", "--audit"), timeout_seconds=COMMAND_TIMEOUT_SECONDS)
    )
    return tuple(line.split()[0] for line in report.stdout.splitlines() if line.startswith(" "))


def _unaccounted_refusal(*, flagged: tuple[str, ...], runs: Path) -> str | None:
    """Every flagged package no guard run's recorded intended set accounts for.

    `dpkg --audit` naming something is not by itself a reason to stop: a
    rollback from `publishing` leaves a guard run's packages part
    installed and the next run has to be able to finish them. What the
    step may never do is step over somebody else's interrupted
    transaction, so membership in the union is the test.
    """
    recorded = _recorded_packages(runs=runs)
    foreign = tuple(sorted(name for name in flagged if name not in recorded))
    if foreign:
        return f"dpkg --audit names {foreign}, which no guard run recorded as intended"
    return None


def _in_states(
    *,
    flagged: tuple[str, ...],
    installed: Mapping[str, InstalledPackage],
    states: frozenset[str],
) -> tuple[str, ...]:
    """The flagged packages dpkg holds in one of `states`, sorted."""
    return tuple(sorted(name for name in flagged if installed.get(name, _UNHELD).status in states))


def _recover_interrupted(
    *,
    runner: TimedRunner,
    flagged: tuple[str, ...],
    installed: Mapping[str, InstalledPackage],
) -> None:
    """Finish what an interrupted install left, and only for those packages.

    Design F6's recovery branch. It runs BEFORE this run's own
    transaction because dpkg refuses to unpack over a database that
    still holds an unfinished one, and it is aimed at named packages
    rather than issued as `--configure -a`, which would adopt whatever
    else the host has left pending.

    Every name here has already been accounted for against the recorded
    intended sets, so the narrowness that remains is by STATE: the three
    an interrupted unpack leaves go to `--configure`, and the two a
    helper killed during trigger processing leaves go to
    `--triggers-only`. A package is in exactly one of those positions,
    and completing an unpacked package's triggers would skip the
    configuration it is actually waiting for.
    """
    recoverable = _in_states(flagged=flagged, installed=installed, states=_RECOVERABLE_STATES)
    if recoverable:
        _ = runner(
            command=TimedCommand(
                argv=("dpkg", "--configure", *recoverable),
                timeout_seconds=INSTALL_TIMEOUT_SECONDS,
                env=_FENCED_ENV,
            )
        )
    awaiting = _in_states(flagged=flagged, installed=installed, states=_TRIGGER_STATES)
    if awaiting:
        _ = runner(
            command=TimedCommand(
                argv=("dpkg", "--triggers-only", *awaiting),
                timeout_seconds=INSTALL_TIMEOUT_SECONDS,
                env=_FENCED_ENV,
            )
        )


def _drift_refusal(*, audit: Audit, installed: Mapping[str, InstalledPackage]) -> str | None:
    """Every version the audit relied on that has moved since it read them.

    An unattended upgrade landing libc6 while the audit downloaded and
    digested its archives breaks no committed digest and leaves the
    audited verdict resting on a host that no longer exists. A package
    that has GONE counts as moved for the same reason, which is why the
    comparison is on the version the audit saw and not on presence.
    """
    moved = tuple(
        sorted(
            name
            for name, version in audit.relied_on.items()
            if name not in installed or installed[name].version != version
        )
    )
    if moved:
        return f"these installed versions moved since the audit read them: {moved}"
    return None


def _audited(*, inputs: Path, runner: TimedRunner) -> Audit | str:
    """This run's cleared transaction, or the refusal that stops it being one.

    The two refusals reachable with no dpkg state read at all — inputs
    that cannot be read, and a transaction the audit will not clear —
    are answered together here, because that is the line this module set
    already draws: one half PROVES and the other MUTATES, and a refusal
    on the proving side must be reachable without touching the other.
    """
    declared = load_package_inputs(inputs=inputs)
    if isinstance(declared, str):
        return declared
    return audit_transaction(declared=declared, runner=runner)


def run_package_step(*, inputs: Path, runner: TimedRunner = default_runner) -> PackageStepResult:
    """Install exactly the audited package set named by this run's `inputs`.

    `dpkg -i` is issued on the audited `.deb` SET and nothing else, so
    the transaction that runs is byte-for-byte the one the audit cleared
    with no resolver decision left to apt. dpkg's own table is read on
    both sides of it, and the difference has to be the additions the
    host did not already hold — which on a host that holds all of them
    is no transaction at all.

    The intended record is written once the audit has cleared and before
    anything is mutated (design R7), so a run interrupted anywhere in
    the install leaves behind the set it meant to install — which is
    what lets the NEXT run tell its own unfinished work from somebody
    else's.
    """
    audit = _audited(inputs=inputs, runner=runner)
    if isinstance(audit, str):
        return PackageStepResult(refusal=audit)
    run_dir = inputs.parent
    write_durable(
        path=run_dir / INTENDED_FILE,
        data=json.dumps({"run": run_dir.name, "additions": list(audit.additions)}),
    )
    before = read_installed(runner=runner)
    drift = _drift_refusal(audit=audit, installed=before)
    if drift is not None:
        return PackageStepResult(refusal=drift)
    if _already_settled(audit=audit, installed=before):
        # Nothing to install, so nothing is mutated and no recovery is
        # anybody's business: the step returns having only READ. Issuing
        # `dpkg -i` again over a host that already matches the audit
        # would be a mutation with no transaction behind it.
        return PackageStepResult(installed=audit.additions)
    flagged = _flagged_packages(runner=runner)
    unaccounted = _unaccounted_refusal(flagged=flagged, runs=run_dir.parent)
    if unaccounted is not None:
        return PackageStepResult(refusal=unaccounted)
    _recover_interrupted(runner=runner, flagged=flagged, installed=before)
    _ = runner(
        command=TimedCommand(
            argv=("dpkg", "-i", *(str(deb) for deb in audit.debs)),
            timeout_seconds=INSTALL_TIMEOUT_SECONDS,
            env=_FENCED_ENV,
        )
    )
    difference = _difference_refusal(
        expected=_expected_difference(audit=audit, before=before),
        before=before,
        after=read_installed(runner=runner),
    )
    if difference is not None:
        return PackageStepResult(refusal=difference)
    return PackageStepResult(installed=audit.additions)
