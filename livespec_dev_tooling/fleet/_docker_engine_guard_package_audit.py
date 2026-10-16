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

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__: list[str] = [
    "INPUTS_FILE",
    "Audit",
    "PackageInputs",
    "PackageSpec",
    "audit_transaction",
    "load_package_inputs",
]

# The controller writes a run's inputs only into that run's own `inputs/`
# directory, so this name is resolved against the directory the step was
# handed and never against a path the inputs themselves carry.
INPUTS_FILE: Final[str] = "packages.json"


@dataclass(frozen=True, kw_only=True)
class PackageSpec:
    """One committed allowlist row: a package, its version, its archive file."""

    package: str
    version: str
    deb: str


@dataclass(frozen=True, kw_only=True)
class PackageInputs:
    """The committed inputs one run's package step is allowed to act on."""

    specs: tuple[PackageSpec, ...]
    cache: Path


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
        PackageSpec(package=row["package"], version=row["version"], deb=row["deb"])
        for row in declared
    )
    return PackageInputs(specs=specs, cache=Path(payload["cache"]))


def audit_transaction(*, declared: PackageInputs) -> Audit:
    """Prove what the install may touch, before the step has touched anything."""
    return Audit(
        debs=tuple(declared.cache / spec.deb for spec in declared.specs),
        additions=tuple(sorted(f"{spec.package}={spec.version}" for spec in declared.specs)),
    )
