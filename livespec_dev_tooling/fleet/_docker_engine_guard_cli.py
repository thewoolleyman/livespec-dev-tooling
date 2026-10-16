"""The Docker engine install guard's command line: parse a request, report an outcome.

The role invokes the guard as `<guard> <op> <run>` inside a transient
`systemd-run` unit whose `TimeoutStartSec` is that operation's budget,
so everything the guard needs beyond the two positional arguments has a
default naming the specification's own locations. The overrides exist
for one reason: the disposable acceptance host, which must be driven
somewhere other than `/var/lib` and `/run`.

Reporting is a concern of its own, and a real one. A refusal that
reaches an operator as an exit code alone does not say which run holds
the host, how far it got, or when the dead-man will take it back — and
on a machine reachable only over Tailscale, the next step depends
entirely on those three.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.fleet._docker_engine_guard_model import (
    DEFAULT_RUNTIME_ROOT,
    DEFAULT_STATE_ROOT,
    DEFAULT_WINDOW_SECONDS,
    OPERATIONS,
    GuardPaths,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from livespec_dev_tooling.fleet._docker_engine_guard_model import GuardOutcome, Operation

__all__: list[str] = [
    "LOGGER_NAME",
    "CliRequest",
    "emit",
    "parse_request",
]

LOGGER_NAME = "docker_engine_guard"

_PROG = "docker-engine-guard"
_DESCRIPTION = "Install the Docker engine on a k3s host behind a dead-man rollback."


@dataclass(frozen=True, kw_only=True)
class CliRequest:
    """One parsed invocation: which operation, on which run, against which roots."""

    operation: Operation
    run: str
    paths: GuardPaths
    window_seconds: int


def parse_request(*, argv: Sequence[str]) -> CliRequest:
    """Read one invocation's arguments into the request the guard acts on."""
    parser = argparse.ArgumentParser(prog=_PROG, description=_DESCRIPTION)
    _ = parser.add_argument("operation", choices=OPERATIONS)
    _ = parser.add_argument("run")
    _ = parser.add_argument("--state-root", default=str(DEFAULT_STATE_ROOT))
    _ = parser.add_argument("--runtime-root", default=str(DEFAULT_RUNTIME_ROOT))
    _ = parser.add_argument("--window-seconds", type=int, default=DEFAULT_WINDOW_SECONDS)
    args = parser.parse_args(list(argv))
    return CliRequest(
        operation=args.operation,
        run=args.run,
        paths=GuardPaths(state_root=Path(args.state_root), runtime_root=Path(args.runtime_root)),
        window_seconds=args.window_seconds,
    )


def emit(*, outcome: GuardOutcome) -> int:
    """Write the outcome's report where an operator reads it, and hand back its code."""
    logger = logging.getLogger(LOGGER_NAME)
    for line in outcome.report_lines():
        logger.info(line)
    return outcome.exit_code
