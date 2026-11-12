"""Temporary Red-phase surface for delegated pre-push evidence reuse."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling import check_authority, check_purity
from livespec_dev_tooling.gate_remote_invocation import default_gate_command_runner

if TYPE_CHECKING:
    import structlog

CONTINUE_WITH_OWN_GATE = 3
PRE_PUSH_EVIDENCE = "pre-push-evidence"
PRE_PUSH_REUSE = "pre-push-reuse"
PRE_PUSH_COMMANDS = (PRE_PUSH_EVIDENCE, PRE_PUSH_REUSE)


def accepted_lines(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> None:
    """Stand in for qualification until the Green implementation is staged."""
    del cwd, log
    return None


def run_pre_push_reuse(*, cwd: Path, targets: list[str], log: structlog.stdlib.BoundLogger) -> int:
    """Fail the behavioral assertion until the shared command is implemented."""
    del cwd, targets, log
    return 0


def run_pre_push_command(
    *, command: str, cwd: Path, targets: list[str], log: structlog.stdlib.BoundLogger
) -> int:
    """Fail the behavioral assertion until the shared command is implemented."""
    del command, cwd, targets, log
    return 0
