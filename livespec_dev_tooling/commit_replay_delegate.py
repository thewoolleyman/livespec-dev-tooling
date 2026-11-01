"""Commit-time replay delegation seam."""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from pathlib import Path

from livespec_dev_tooling.config import ConfigParseError, load_delegated_commit_tests
from livespec_dev_tooling.gate_credential import gates_kubeconfig_readable
from livespec_dev_tooling.gate_remote_delegate import gate_remote_request, resolve_renderer
from livespec_dev_tooling.gate_remote_invocation import default_gate_command_runner
from livespec_dev_tooling.gate_remote_verdict import (
    GATE_FAILED,
    GATE_PASSED,
    run_gated_push,
)

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


def _staged_commit(*, repo_root: Path, tree_hash: str) -> str:
    """Wrap the index tree in a commit object the gate can push."""
    argv = [
        "git",
        "-c",
        "user.name=livespec-replay",
        "-c",
        "user.email=replay@livespec.invalid",
        "commit-tree",
        tree_hash,
        "-p",
        "HEAD",
        "-mcommit-time replay of the staged tree",
    ]
    committed = default_gate_command_runner(argv=argv, cwd=repo_root)
    if isinstance(committed, Failure):
        return ""
    return committed.unwrap().stdout.strip()


def _run_remote(*, repo_root: Path, pytest_argv: list[str], tree_hash: str) -> ReplayVerdict:
    """Submit the selected index tree and retain the Job's own verdict."""
    built = gate_remote_request(
        repo_root=repo_root,
        renderer=resolve_renderer(repo_root=repo_root),
        runner=default_gate_command_runner,
        tree_hash=tree_hash,
        pytest_argv=tuple(pytest_argv),
    )
    if isinstance(built, Failure):
        return ReplayVerdict(
            local=False,
            reason=f"the gate Job reached no verdict: {built.failure().detail}",
            tree_hash=tree_hash,
        )
    source = _staged_commit(repo_root=repo_root, tree_hash=tree_hash)
    if not source:
        return ReplayVerdict(
            local=False,
            reason="the staged tree could not be committed for the gate",
            tree_hash=tree_hash,
        )
    request = replace(built.unwrap(), source_ref=source, capture_output=True)
    remote = run_gated_push(request=request, runner=default_gate_command_runner)
    exit_status = 0 if remote.state == GATE_PASSED else 1 if remote.state == GATE_FAILED else None
    return ReplayVerdict(
        local=False,
        reason=remote.detail,
        job_name=remote.job_name,
        tree_hash=tree_hash,
        exit_status=exit_status,
        output_checksum=remote.output_checksum,
    )
