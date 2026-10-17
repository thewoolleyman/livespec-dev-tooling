"""Re-unpacking a half-installed intended package from its audited archive.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Package fence", as amended in
revise v076, and `SPECIFICATION/scenarios.md` section "Scenario: a
Docker engine install guard publish resumed after a kill during an
intended package's unpack re-unpacks it from its audited archive".
Governing design: `docs/docker-engine-guard-design.md` F6.

dpkg cannot CONFIGURE a half-installed package. The state means the
unpack itself did not finish, so dpkg answers `package docker.io is not
ready for configuration / cannot configure (current status
'half-installed')` and exits 1, and its own documentation says the
package needs reinstallation. Measured on poweredge guard-vm-0 and
guard-vm-2 on 2026-10-17 against release v1.112.10 (FAULTS B-06 and
M-04): a SIGKILL during `dpkg -i`'s unpack of docker.io left it
`half-installed`, recovery aimed `dpkg --configure` at it, and because
the step may issue `dpkg -i` only over an EMPTY `dpkg --audit`, the
state could never clear and every later run on that host refused
identically. Proven on guard-vm-1 the same evening: `dpkg --unpack` of
that package's own audited archive moves it to `unpacked`, after which
`dpkg --configure runc containerd docker.io` leaves all three installed
with `dpkg --audit` empty.

So this module is the one branch that UNPACKS outside the step's own
`dpkg -i`, and the fence around it is why it is separated from the step:
each `dpkg --unpack` names exactly ONE file, that file is one of THIS
run's audited `.deb` files, and the archive is matched to the leftover
on package name, version AND architecture — so a leftover the audited
set does not carry at that exact identity REFUSES rather than being
unpacked from a neighbouring archive the audit cleared for another row.

The leftover's architecture is read per leftover rather than by widening
the table read `QUERY_ARGV` makes: that read answers for every package
on the host and its three fields are what the drift and post-install
comparisons rest on, while an architecture is needed only for the
handful of packages `dpkg --audit` names.

Expected refusals are RETURNED as the reason an operator reads, never
raised: the modules are copied onto the guarded host and run against its
bare interpreter, where the `returns` railway is not importable.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from livespec_dev_tooling.fleet._docker_engine_guard_package_audit import (
    UNHELD,
    InstalledPackage,
)
from livespec_dev_tooling.fleet._docker_engine_guard_package_runner import (
    COMMAND_TIMEOUT_SECONDS,
    FENCED_ENV,
    INSTALL_TIMEOUT_SECONDS,
    TimedCommand,
    TimedRunner,
)

__all__: list[str] = [
    "HALF_INSTALLED",
    "Reunpacked",
    "reunpack_half_installed",
]

# The dpkg status an interrupted UNPACK leaves, and the one state
# `dpkg --configure` can do nothing at all with.
HALF_INSTALLED: Final[str] = "half-installed"

# The leftover's architecture, asked for one package at a time. It is
# the one field of the match dpkg's own table read does not carry.
_ARCHITECTURE_QUERY: Final[tuple[str, ...]] = (
    "dpkg-query",
    "-W",
    "-f",
    "${Architecture}\n",
)

# The three control fields that identify an archive, asked for together.
# `dpkg-deb -f` given MORE than one field prints `Field: value` lines
# instead of the bare value one field yields — and prints them in the
# order the control file carries them rather than the order they were
# asked for, so the answer is indexed by NAME and never by position.
_IDENTITY_FIELDS: Final[tuple[str, ...]] = (
    "Package",
    "Version",
    "Architecture",
)


@dataclass(frozen=True, kw_only=True)
class _Identity:
    """One package named the way dpkg's database and a `.deb` both name it."""

    package: str
    version: str
    architecture: str


@dataclass(frozen=True, kw_only=True)
class Reunpacked:
    """What the re-unpack did, or the refusal that stopped it before it did."""

    refusal: str | None = None
    unpacked: tuple[str, ...] = ()


def _read(*, runner: TimedRunner, argv: tuple[str, ...]) -> str:
    """One bounded read through the runner, answered as its standard output."""
    answer = runner(command=TimedCommand(argv=argv, timeout_seconds=COMMAND_TIMEOUT_SECONDS))
    return answer.stdout


def _archive_identity(*, deb: Path, runner: TimedRunner) -> _Identity:
    """What archive `deb` says it is, read from its own control stanza."""
    stanza = _read(runner=runner, argv=("dpkg-deb", "-f", str(deb), *_IDENTITY_FIELDS))
    fields = {
        name.strip(): value.strip()
        for name, _, value in (line.partition(":") for line in stanza.splitlines())
    }
    return _Identity(
        package=fields.get("Package", ""),
        version=fields.get("Version", ""),
        architecture=fields.get("Architecture", ""),
    )


def _leftover_identity(*, name: str, row: InstalledPackage, runner: TimedRunner) -> _Identity:
    """What dpkg holds for the leftover `name`, in those same three fields.

    The architecture QUALIFIER that `${binary:Package}` and
    `dpkg --audit` both carry for a non-native package is dropped from
    the name, because an archive's `Package` field never carries it and
    the architecture is compared on its own field instead.
    """
    architecture = _read(runner=runner, argv=(*_ARCHITECTURE_QUERY, name)).strip()
    return _Identity(package=name.partition(":")[0], version=row.version, architecture=architecture)


def reunpack_half_installed(
    *,
    runner: TimedRunner,
    flagged: tuple[str, ...],
    installed: Mapping[str, InstalledPackage],
    debs: tuple[Path, ...],
) -> Reunpacked:
    """Re-unpack every half-installed leftover from this run's audited archives.

    Answered as the names re-unpacked, because a caller holding the dpkg
    table read BEFORE this ran no longer has a true one: a re-unpacked
    package is `unpacked` afterwards, and it is THAT state the recovery's
    `dpkg --configure` has to be aimed at.

    A leftover no audited `.deb` of this run carries at that exact
    identity REFUSES. Unpacking a neighbouring archive instead would be
    a transaction nobody audited, aimed at a database already holding an
    unfinished one — and the step cannot proceed either way, because
    design F6 requires a fresh transaction to start from an empty
    `dpkg --audit` and this report can no longer be emptied.
    """
    unpacked: list[str] = []
    for name in sorted(flagged):
        row = installed.get(name, UNHELD)
        if row.status != HALF_INSTALLED:
            continue
        wanted = _leftover_identity(name=name, row=row, runner=runner)
        matched = [deb for deb in debs if _archive_identity(deb=deb, runner=runner) == wanted]
        if not matched:
            return Reunpacked(
                refusal=(
                    f"no audited `.deb` of this run carries {wanted.package} "
                    f"{wanted.version} {wanted.architecture}, which dpkg holds "
                    f"{HALF_INSTALLED}, so it cannot be re-unpacked"
                )
            )
        _ = runner(
            command=TimedCommand(
                argv=("dpkg", "--unpack", str(matched[0])),
                timeout_seconds=INSTALL_TIMEOUT_SECONDS,
                env=FENCED_ENV,
            )
        )
        unpacked.append(name)
    return Reunpacked(unpacked=tuple(unpacked))
