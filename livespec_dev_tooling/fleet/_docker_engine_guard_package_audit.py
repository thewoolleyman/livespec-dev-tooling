"""What the Docker engine install guard's package step is allowed to touch.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Package fence". Governing design:
`docs/docker-engine-guard-design.md`, Mechanism 5 as amended by R6 and F6.

This module is the half of the fence that runs BEFORE anything is
mutated: the committed inputs a controller uploaded for one run, and the
audit that decides whether the transaction they describe may run at all.
It is separate from the step itself (`_docker_engine_guard_packages.py`)
because the two have different jobs on different sides of the lock — one
proves, the other mutates — and because a refusal here must be reachable
with no dpkg state touched.

Expected refusals are RETURNED as the reason an operator reads, never
raised: the modules are copied onto the guarded host and run against its
bare interpreter, where the `returns` railway is not importable.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from livespec_dev_tooling.fleet._docker_engine_guard_runner import (
    COMMAND_TIMEOUT_SECONDS,
    TimedCommand,
    TimedRunner,
)

__all__: list[str] = [
    "INPUTS_FILE",
    "QUERY_ARGV",
    "Audit",
    "InstalledPackage",
    "PackageInputs",
    "PackageSpec",
    "audit_transaction",
    "load_package_inputs",
    "read_installed",
]

# The controller writes a run's inputs only into that run's own `inputs/`
# directory, so this name is resolved against the directory the step was
# handed and never against a path the inputs themselves carry.
INPUTS_FILE: Final[str] = "packages.json"

# The simulated transaction, which the committed specs are appended to.
# `--no-install-recommends` keeps apt from widening the set, and
# `--no-remove` makes a transaction that would remove something an apt
# ERROR rather than a silent `Remv` line — belt and braces, because the
# answer is read line by line regardless.
SIMULATE_ARGV: Final[tuple[str, ...]] = (
    "apt-get",
    "-s",
    "install",
    "--no-install-recommends",
    "--no-remove",
)

# The one package query the fence makes, in the one format it parses. Both
# fields are asked for together because dpkg's table is read once per side
# of the install: the VERSION is what the post-install difference compares,
# and the STATUS is what tells a half-installed package from a settled one.
QUERY_ARGV: Final[tuple[str, ...]] = (
    "dpkg-query",
    "-W",
    "-f",
    "${binary:Package} ${Version} ${db:Status-Status}\n",
)

# The field of an `apt-cache show` stanza that carries the archive's own
# statement about the file's bytes.
_INDEX_DIGEST_FIELD: Final[str] = "SHA256:"

# How many fields a line of that output carries when dpkg holds the
# package. A line with fewer is a package dpkg knows of and holds nothing
# for; `read_installed` records why that is not a parse failure.
_QUERY_FIELD_COUNT: Final[int] = 3


@dataclass(frozen=True, kw_only=True)
class PackageSpec:
    """One committed allowlist row: a package, its version, its archive file.

    `scripts` maps a maintainer-script name to the SHA256 a human read and
    committed for it. Those scripts are the programs the install runs as
    root, so they are the one thing here no archive statement vouches for.
    """

    package: str
    version: str
    deb: str
    scripts: Mapping[str, str]


@dataclass(frozen=True, kw_only=True)
class PackageInputs:
    """The committed inputs one run's package step is allowed to act on."""

    specs: tuple[PackageSpec, ...]
    cache: Path
    # Absolute host path mapped to the SHA256 committed for it: the apt
    # hook files and the dpkg configuration the install rides on.
    config_digests: Mapping[str, str]
    # The directories whose EVERY file one of those digests has to cover,
    # so a configuration file that was ADDED refuses as well as one
    # altered. An absent directory is zero uncovered files, not a refusal.
    config_dirs: tuple[str, ...]


@dataclass(frozen=True, kw_only=True)
class Audit:
    """What the audit cleared: the exact files to install, and what they add."""

    # In the order the allowlist declares them, which is the order dpkg
    # unpacks them in: the committed inputs decide it, not this module.
    debs: tuple[Path, ...]
    # `package=version` per allowlist row, sorted — the difference the
    # post-install query has to show, and nothing else.
    additions: tuple[str, ...]


def load_package_inputs(*, inputs: Path) -> PackageInputs | str:
    """This run's committed package inputs, or the refusal that stops the step.

    An absent allowlist is a REFUSAL rather than an empty install. Read
    as "install nothing" it would make a malformed or truncated upload
    indistinguishable from a transaction that succeeded, and the step
    would report a clean install having audited nothing at all.
    """
    path = inputs / INPUTS_FILE
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return f"the run's package inputs at {path} could not be read: {error}"
    declared = payload.get("allow")
    if not declared:
        return f"the run's package inputs at {path} declare no package allowlist"
    specs = tuple(
        PackageSpec(
            package=row["package"],
            version=row["version"],
            deb=row["deb"],
            scripts=dict(row["scripts"]),
        )
        for row in declared
    )
    return PackageInputs(
        specs=specs,
        cache=Path(payload["cache"]),
        config_digests=dict(payload["config_digests"]),
        config_dirs=tuple(payload["config_dirs"]),
    )


@dataclass(frozen=True, kw_only=True)
class InstalledPackage:
    """One row of dpkg's own table: the version it holds, and the state it is in."""

    version: str
    status: str


def read_installed(*, runner: TimedRunner) -> dict[str, InstalledPackage]:
    """Every package dpkg knows, mapped to the version and status it holds.

    A line dpkg emits without all three fields is dropped rather than
    guessed at, and that case is measured rather than defensive:
    `dpkg-query -W` lists a package dpkg merely KNOWS OF, pulled in by
    some dependency, with an EMPTY version field and the status
    `not-installed`. Admitted as a package at some version it would be a
    phantom in both the post-install difference and the drift comparison.
    """
    answer = runner(command=TimedCommand(argv=QUERY_ARGV, timeout_seconds=COMMAND_TIMEOUT_SECONDS))
    rows: dict[str, InstalledPackage] = {}
    for line in answer.stdout.splitlines():
        fields = line.split()
        if len(fields) == _QUERY_FIELD_COUNT:
            rows[fields[0]] = InstalledPackage(version=fields[1], status=fields[2])
    return rows


def _simulation_refusal(*, output: str, allow: Mapping[str, str]) -> str | None:
    """The first line of the simulated transaction the allowlist does not cover.

    Three shapes refuse, and each is read off the line itself because apt
    reports none of them as an error. A `Remv` line is a removal. An
    `Inst` line carrying a BRACKETED version before the parenthesised one
    is an UPGRADE of a package the host already holds — a resolver
    satisfying the pins by moving something else, which is exactly the
    collateral change a guarded install must not make. And an `Inst` line
    naming a (package, version) pair the committed allowlist does not
    carry is the resolver widening the transaction.
    """
    for line in output.splitlines():
        fields = line.split()
        if fields[:1] == ["Remv"]:
            return f"the simulated transaction removes {fields[1]}: {line.strip()}"
        if fields[:1] != ["Inst"]:
            continue
        if fields[2].startswith("["):
            return f"the simulated transaction upgrades the installed {fields[1]}: {line.strip()}"
        version = fields[2].lstrip("(")
        if allow.get(fields[1]) != version:
            return (
                f"the simulated transaction installs {fields[1]}={version}, "
                "outside the committed allowlist"
            )
    return None


def _read(*, runner: TimedRunner, argv: tuple[str, ...], cwd: Path | None = None) -> str:
    """One bounded read through the runner, answered as its standard output."""
    answer = runner(
        command=TimedCommand(argv=argv, timeout_seconds=COMMAND_TIMEOUT_SECONDS, cwd=cwd)
    )
    return answer.stdout


def _index_digest(*, spec: PackageSpec, runner: TimedRunner) -> str | None:
    """The `SHA256:` the archive index carries for this exact package and version.

    `None` when the index entry carries none at all, which a source that
    publishes no checksums produces — and which must refuse rather than
    read as "nothing to compare against".
    """
    shown = _read(runner=runner, argv=("apt-cache", "show", f"{spec.package}={spec.version}"))
    for line in shown.splitlines():
        if line.startswith(_INDEX_DIGEST_FIELD):
            return line[len(_INDEX_DIGEST_FIELD) :].strip()
    return None


def _verification_refusal(*, spec: PackageSpec, deb: Path, runner: TimedRunner) -> str | None:
    """Why this downloaded archive may not be installed, or `None` if it may.

    The download happens here because it changes no dpkg state, so it is
    safe on either side of the lock (design R6), and the whole point of
    doing it at all is that the installed transaction is then the audited
    FILE rather than a resolver decision repeated later.

    The SHA256 is compared against the ARCHIVE INDEX entry for that exact
    (package, version) rather than against a digest committed in the role:
    the index is the archive's own statement about the file, so a mirror
    serving different bytes under the pinned version is caught without the
    role re-committing a digest at every security update. The maintainer
    scripts go the other way, against digests a human read and committed.
    """
    _ = _read(
        runner=runner,
        argv=("apt-get", "download", f"{spec.package}={spec.version}"),
        cwd=deb.parent,
    )
    if not deb.is_file():
        # `apt-get download` exits 0 having written nothing when the
        # pinned version has fallen out of the index.
        return f"`apt-get download` left no {deb.name} in {deb.parent}"
    index = _index_digest(spec=spec, runner=runner)
    if index is None:
        return f"the archive index entry for {spec.package}={spec.version} carries no SHA256"
    if hashlib.sha256(deb.read_bytes()).hexdigest() != index:
        return f"{deb.name}'s SHA256 differs from the archive index entry for it"
    control = _read(runner=runner, argv=("dpkg-deb", "-f", str(deb), "Version")).strip()
    if control != spec.version:
        # A file name collision in the cache: the right name, another version.
        return f"{deb.name} carries control version {control}, not {spec.version}"
    for script, committed in sorted(spec.scripts.items()):
        shown = _read(runner=runner, argv=("dpkg-deb", "-I", str(deb), script))
        if hashlib.sha256(shown.encode("utf-8")).hexdigest() != committed:
            return f"{deb.name}'s {script} differs from its committed digest"
    return None


def _configuration_refusal(*, declared: PackageInputs) -> str | None:
    """The host apt or dpkg configuration file a committed digest does not vouch for.

    Neither kind is incidental to a fenced install: an apt hook is a
    program apt runs around every transaction, and a `dpkg.cfg.d`
    fragment can rewrite what unpacking MEANS — a `force-all`, a
    `path-exclude` — so an unexpected one is exactly the gap between the
    transaction that was audited and what the host does with it.

    Both halves are checked, and the second is the one that matters: a
    check verifying only the files it already knew about would be
    entirely silent about one that was ADDED to either directory.
    """
    for path_text, committed in sorted(declared.config_digests.items()):
        path = Path(path_text)
        if not path.is_file():
            return f"the committed configuration file {path} is absent from this host"
        if hashlib.sha256(path.read_bytes()).hexdigest() != committed:
            return f"{path} differs from its committed digest"
    for directory in declared.config_dirs:
        # `glob` rather than `iterdir`: a host carrying no fragment
        # directory at all is zero uncovered files, not an error.
        for found in sorted(Path(directory).glob("*")):
            if found.as_posix() not in declared.config_digests:
                return f"{found} is a configuration file no committed digest covers"
    return None


def audit_transaction(*, declared: PackageInputs, runner: TimedRunner) -> Audit | str:
    """Prove what the install may touch, before the step has touched anything.

    The host's own apt and dpkg configuration is checked FIRST, before a
    single command runs: it decides what every later command in this
    transaction would MEAN, so simulating against it would be simulating
    against an unknown.
    """
    unvouched_configuration = _configuration_refusal(declared=declared)
    if unvouched_configuration is not None:
        return unvouched_configuration
    simulated = _read(
        runner=runner,
        argv=(*SIMULATE_ARGV, *(f"{spec.package}={spec.version}" for spec in declared.specs)),
    )
    refusal = _simulation_refusal(
        output=simulated,
        allow={spec.package: spec.version for spec in declared.specs},
    )
    if refusal is not None:
        return refusal
    debs = tuple(declared.cache / spec.deb for spec in declared.specs)
    for spec, deb in zip(declared.specs, debs, strict=True):
        unvouched = _verification_refusal(spec=spec, deb=deb, runner=runner)
        if unvouched is not None:
            return unvouched
    return Audit(
        debs=tuple(declared.cache / spec.deb for spec in declared.specs),
        additions=tuple(sorted(f"{spec.package}={spec.version}" for spec in declared.specs)),
    )
