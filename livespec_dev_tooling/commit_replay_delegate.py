"""Commit-time replay delegation seam."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.config import ConfigParseError, load_delegated_commit_tests
from livespec_dev_tooling.gate_credential import gates_kubeconfig_readable

__all__: list[str] = ["ReplayVerdict", "run_replay"]


@dataclass(frozen=True, kw_only=True)
class ReplayVerdict:
    """The location and result of one replay leg."""

    local: bool
    reason: str


def run_replay(*, repo_root: Path, pytest_argv: list[str]) -> ReplayVerdict:
    """Decide how the replay leg should run."""
    _ = pytest_argv
    try:
        enabled = load_delegated_commit_tests(repo_root=repo_root) is True
    except ConfigParseError:
        enabled = False
    if not enabled:
        return ReplayVerdict(local=True, reason="delegated_commit_tests is not enabled")
    readable = gates_kubeconfig_readable()
    return ReplayVerdict(
        local=not readable,
        reason={
            False: "gates kubeconfig is not readable",
            True: "delegated replay completed",
        }[readable],
    )
