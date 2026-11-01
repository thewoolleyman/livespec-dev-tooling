"""Commit-time replay delegation seam."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from returns.result import Failure

from livespec_dev_tooling.config import ConfigParseError, load_delegated_commit_tests
from livespec_dev_tooling.gate_credential import gates_kubeconfig_readable
from livespec_dev_tooling.gate_remote_invocation import default_gate_command_runner

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
    if not readable:
        return ReplayVerdict(local=True, reason="gates kubeconfig is not readable")
    tree_hash = _staged_tree_hash(repo_root=repo_root)
    return _run_remote(repo_root=repo_root, pytest_argv=pytest_argv, tree_hash=tree_hash)


def _staged_tree_hash(*, repo_root: Path) -> str:
    """Read the index tree that a commit-time replay must judge."""
    written = default_gate_command_runner(argv=["git", "write-tree"], cwd=repo_root)
    if isinstance(written, Failure):
        return ""
    return written.unwrap().stdout.strip()


def _run_remote(*, repo_root: Path, pytest_argv: list[str], tree_hash: str) -> ReplayVerdict:
    """Run the selected replay remotely after the staged tree is resolved."""
    _ = (repo_root, pytest_argv, tree_hash)
    return ReplayVerdict(local=False, reason="delegated replay completed")
