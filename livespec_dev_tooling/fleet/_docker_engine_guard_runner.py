"""The ONE external-command seam the Docker engine install guard's host runs through.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions" (this repository):
every external command the guard runs MUST go through one runner with an
explicit timeout.

The timeout is a REQUIRED argument rather than a default, and that is the
whole reason this module exists. The guard deletes firewall rules and
kills cgroups on a host reachable only over Tailscale; one `iptables`
blocked on the xtables lock, or one `systemctl stop` waiting on a daemon
that never exits, would hold a rollback phase past its own budget and
leave the machine half torn down with nobody able to reach it. A command
that exceeds its bound is therefore REPORTED (as `timeout(1)`'s own exit
code, so a runner timeout and a `timeout -k 10` phase kill read the same)
rather than raised: a phase that cannot finish one command still has to
run its remaining ones.

Stdlib only, Python 3.10 syntax, for the reason
`_docker_engine_guard_model.py` records.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, Protocol

__all__: list[str] = [
    "TIMEOUT_RETURNCODE",
    "GuardCommandResult",
    "GuardCommandRunner",
    "run_command",
]

# `timeout(1)`'s own code for "the bound expired", so the rollback
# driver's `timeout -k 10` phase kill and a single command's expiry are
# one signal to whatever reads them.
TIMEOUT_RETURNCODE: Final[int] = 124


@dataclass(frozen=True, kw_only=True)
class GuardCommandResult:
    """What one external command did: the argv it ran, its code, its output.

    The argv is carried back rather than merely passed in because the
    host actions are asserted on the argv they EMIT -- that is what a
    test of "the kill names exactly these three units" reads.
    """

    argv: tuple[str, ...]
    returncode: int
    stdout: str


class GuardCommandRunner(Protocol):
    """One timed external command. The host's only way out to the machine."""

    def __call__(self, *, argv: Sequence[str], timeout_seconds: int) -> GuardCommandResult: ...


def run_command(*, argv: Sequence[str], timeout_seconds: int) -> GuardCommandResult:
    """Run `argv` under `timeout_seconds`, reporting an expiry instead of raising."""
    try:
        completed = subprocess.run(
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return GuardCommandResult(argv=tuple(argv), returncode=TIMEOUT_RETURNCODE, stdout="")
    return GuardCommandResult(
        argv=tuple(argv), returncode=completed.returncode, stdout=completed.stdout
    )
