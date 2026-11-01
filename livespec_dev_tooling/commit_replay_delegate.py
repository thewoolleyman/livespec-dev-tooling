"""Commit-time replay delegation seam."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from livespec_dev_tooling.config import ConfigParseError, load_delegated_commit_tests
from livespec_dev_tooling.gate_credential import gates_kubeconfig_readable
from livespec_dev_tooling.gate_remote_invocation import default_gate_command_runner

# `returns` is vendored, so a direct module invocation needs to make its
# sibling package importable before it imports the Result implementation.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.result import Failure  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = ["ReplayVerdict", "run_replay"]


@dataclass(frozen=True, kw_only=True)
class ReplayVerdict:
    """The selected replay route and, when available, its remote evidence."""

    local: bool
    reason: str
    job_name: str | None = None
    tree_hash: str | None = None
    exit_status: int | None = None
    output_checksum: str | None = None


def run_replay(*, repo_root: Path, pytest_argv: list[str]) -> ReplayVerdict:
    """Decide whether a replay leg stays local or is delegated."""
    try:
        enabled = load_delegated_commit_tests(repo_root=repo_root) is True
    except ConfigParseError:
        enabled = False
    if not enabled:
        return ReplayVerdict(local=True, reason="delegated_commit_tests is not enabled")
    if not gates_kubeconfig_readable():
        return ReplayVerdict(local=True, reason="gates kubeconfig is not readable")
    tree_hash = _staged_tree_hash(repo_root=repo_root)
    if not tree_hash:
        return ReplayVerdict(local=False, reason="the staged tree could not be read")
    return _run_remote(repo_root=repo_root, pytest_argv=pytest_argv, tree_hash=tree_hash)


def _staged_tree_hash(*, repo_root: Path) -> str:
    """Read the index tree that a commit-time replay must judge."""
    written = default_gate_command_runner(argv=["git", "write-tree"], cwd=repo_root)
    if isinstance(written, Failure):
        return ""
    return written.unwrap().stdout.strip()


def _run_remote(*, repo_root: Path, pytest_argv: list[str], tree_hash: str) -> ReplayVerdict:
    """Represent an unanswered remote replay as an explicit no-verdict result."""
    _ = (repo_root, pytest_argv)
    return ReplayVerdict(
        local=False,
        reason="the gate Job reached no verdict",
        tree_hash=tree_hash,
    )
