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

from dataclasses import dataclass
from pathlib import Path
from typing import Final

from livespec_dev_tooling.fleet._docker_engine_guard_package_audit import (
    audit_transaction,
    load_package_inputs,
)
from livespec_dev_tooling.fleet._docker_engine_guard_runner import (
    INSTALL_TIMEOUT_SECONDS,
    TimedCommand,
    TimedRunner,
    default_runner,
)

__all__: list[str] = [
    "PackageStepResult",
    "run_package_step",
]

# What tells dpkg that its caller already holds the frontend lock — the
# documented way for a frontend holding it to call dpkg (design R6). The
# role's lock-holding helper has held that lock since before the audit,
# so without this the install would block on the fence protecting it.
_FENCED_ENV: Final[dict[str, str]] = {"DPKG_FRONTEND_LOCKED": "1"}


@dataclass(frozen=True, kw_only=True)
class PackageStepResult:
    """What the step installed, or the refusal that stopped it before it did."""

    refusal: str | None = None
    installed: tuple[str, ...] = ()


def run_package_step(*, inputs: Path, runner: TimedRunner = default_runner) -> PackageStepResult:
    """Install exactly the audited package set named by this run's `inputs`.

    `dpkg -i` is issued on the audited `.deb` SET and nothing else, so
    the transaction that runs is byte-for-byte the one the audit cleared
    with no resolver decision left to apt.
    """
    declared = load_package_inputs(inputs=inputs)
    if isinstance(declared, str):
        return PackageStepResult(refusal=declared)
    audit = audit_transaction(declared=declared)
    _ = runner(
        command=TimedCommand(
            argv=("dpkg", "-i", *(str(deb) for deb in audit.debs)),
            timeout_seconds=INSTALL_TIMEOUT_SECONDS,
            env=_FENCED_ENV,
        )
    )
    return PackageStepResult(installed=audit.additions)
