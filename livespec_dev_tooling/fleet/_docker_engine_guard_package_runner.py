"""The timed command runner the Docker engine install guard's PACKAGE FENCE shells through.

Governing specification: `SPECIFICATION/non-functional-requirements.md`
section "Docker engine install guard", "Host actions" — every external
command the guard runs MUST go through one runner with an explicit
timeout. This module IS that runner, and it is a SEAM rather than a
helper: the package fence reaches `apt-get`, `apt-cache`, `dpkg` and
`dpkg-deb` only through it, so a whole transaction can be decided in
tests against RECORDED command output with nothing spawned at all.

STDLIB ONLY, for the reason `_docker_engine_guard_model.py` records: these
modules are copied onto a factory host as
`/usr/local/libexec/docker-engine-guard` and run against its bare
interpreter, where `dry-python/returns` is not importable. An expected
failure is therefore carried in a RETURNED value, exactly as the Result
rails require — only the carrier differs.
"""

from __future__ import annotations

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Protocol

__all__: list[str] = [
    "COMMAND_TIMEOUT_SECONDS",
    "FENCED_ENV",
    "INSTALL_TIMEOUT_SECONDS",
    "CommandOutput",
    "TimedCommand",
    "TimedRunner",
    "default_runner",
]

# What tells dpkg that its caller already holds the frontend lock — the
# documented way for a frontend holding it to call dpkg (design R6). The
# role's lock-holding helper has held that lock since before the audit,
# so without this the install would block on the fence protecting it.
#
# It lives beside the timeouts because it is the same kind of fact: not
# something any one step decides, but how EVERY dpkg this fence issues
# has to be called. Each of the three — the install, the re-unpack and
# the configure — carries it, and `default_runner` below is where it is
# merged over the ambient environment rather than replacing it.
FENCED_ENV: Final[dict[str, str]] = {"DPKG_FRONTEND_LOCKED": "1"}

# The bound on every READ the fence makes: a simulated transaction, an
# archive index lookup, a package query. Generous enough for an apt
# resolver run on a loaded host and far inside `publish`'s 1800-second
# budget, because a read that blocks to the budget would take the whole
# operation's unit down with it and leave no verdict at all.
COMMAND_TIMEOUT_SECONDS: Final[int] = 120

# The bound on the one MUTATION: `dpkg -i` over the audited set, plus the
# dpkg triggers it runs. Separate from the read bound because unpacking
# and configuring three engine packages is minutes of work where a query
# is seconds, and a shared number would have to be the larger of the two.
INSTALL_TIMEOUT_SECONDS: Final[int] = 600


@dataclass(frozen=True, kw_only=True)
class TimedCommand:
    """One external command: its argv, its explicit timeout, where it runs.

    Carried as a record rather than as four runner parameters so the
    protocol below stays one method taking one argument. That is what
    lets a test record exactly what each step of the fence emitted and
    assert on the argv itself, which is the only evidence that the
    transaction run is the transaction audited.
    """

    argv: Sequence[str]
    timeout_seconds: int
    cwd: Path | None = None
    # ADDITIONS to the ambient environment, never a replacement for it.
    env: Mapping[str, str] | None = None


@dataclass(frozen=True, kw_only=True)
class CommandOutput:
    """One command's exit status and what it wrote to standard output."""

    returncode: int
    stdout: str


class TimedRunner(Protocol):
    """Run one command to completion under the timeout that command carries."""

    def __call__(self, *, command: TimedCommand) -> CommandOutput: ...


def default_runner(*, command: TimedCommand) -> CommandOutput:
    """Spawn `command` for real. The guard package step's one process boundary.

    `env` is merged OVER the ambient environment rather than passed
    through, because the single variable the fence sets
    (`DPKG_FRONTEND_LOCKED`) has to ride alongside the environment dpkg
    needs and the guard did not build — PATH above all. Passed through,
    the install would run with an environment of exactly one variable.
    """
    environment = None if command.env is None else {**os.environ, **command.env}
    completed = subprocess.run(
        list(command.argv),
        cwd=command.cwd,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
        timeout=command.timeout_seconds,
    )
    return CommandOutput(returncode=completed.returncode, stdout=completed.stdout)
