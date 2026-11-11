"""Commit-time replay delegation seam."""

from __future__ import annotations

import sys
from dataclasses import dataclass, replace
from functools import partial
from pathlib import Path

from livespec_dev_tooling._gate_remote_assembly import refuses_declaration
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

import structlog  # noqa: E402  — vendor-path-aware import.
from returns.result import Failure  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = ["ReplayVerdict", "run_one_test", "run_replay", "unrefused"]


@dataclass(frozen=True, kw_only=True)
class ReplayVerdict:
    """The selected replay route and, when available, its remote evidence."""

    local: bool
    reason: str
    job_name: str | None = None
    tree_hash: str | None = None
    exit_status: int | None = None
    output_checksum: str | None = None
    # A refusal rejects the committed configuration: its consumer refuses the
    # commit naming the key, and must never read it as an absent verdict.
    refused: bool = False


# A Red or Green replay Job runs ONE recorded test module with no worker count,
# so it takes the replay contract's size, never the repository's full-suite
# declaration (contracts.md "Delegated commit-time replay test runs", Replay
# Job size).
_SINGLE_TEST_JOB_SIZE = ("--cpu", "2", "--memory", "3Gi", "--parallelism", "1")


def run_replay(
    *, repo_root: Path, pytest_argv: list[str], single_test: bool = False
) -> ReplayVerdict:
    """Decide whether a replay leg stays local or is delegated.

    `single_test` marks a Red or Green leg, whose Job is sized by the replay
    contract. A suite-green leg leaves it unset and keeps the declared size.
    """
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
    return _run_remote(
        repo_root=repo_root,
        pytest_argv=pytest_argv,
        tree_hash=tree_hash,
        resources=_SINGLE_TEST_JOB_SIZE if single_test else None,
    )


# The Red and Green legs' entry point: one recorded test module, at the replay
# contract's size. A suite-green leg calls run_replay itself and keeps the
# repository's declared size.
run_one_test = partial(run_replay, single_test=True)


def unrefused(*, verdict: ReplayVerdict) -> ReplayVerdict:
    """Pass a replay verdict on, or stop the commit when the delegate refused it.

    Running the leg locally instead would let a refused Red pass as a valid
    failing Red, so a refusal ends the commit before any pytest run or trailer.
    """
    if verdict.refused:
        structlog.PrintLogger(file=sys.stderr).msg(verdict.reason)
        raise SystemExit(1)
    return verdict


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


def _run_remote(
    *,
    repo_root: Path,
    pytest_argv: list[str],
    tree_hash: str,
    resources: tuple[str, ...] | None,
) -> ReplayVerdict:
    """Submit the selected index tree and retain the Job's own verdict."""
    built = gate_remote_request(
        repo_root=repo_root,
        renderer=resolve_renderer(repo_root=repo_root),
        runner=default_gate_command_runner,
        tree_hash=tree_hash,
        pytest_argv=tuple(pytest_argv),
        resources=resources,
    )
    if isinstance(built, Failure):
        refused = refuses_declaration(failure=built.failure())
        return ReplayVerdict(
            local=False,
            reason=(
                f"the commit is refused: unusable gate Job resources: {built.failure().detail}"
                if refused
                else f"the gate Job reached no verdict: {built.failure().detail}"
            ),
            tree_hash=tree_hash,
            refused=refused,
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
    # Only a one-file leg is sized by the caller. Killed for memory or evicted,
    # it proved nothing about its test, and read as a failed run it would pass
    # as a valid Red (contracts.md "Delegated commit-time replay test runs",
    # Replay Job size), so it is an absent verdict and the leg runs locally.
    if resources is not None and remote.resource_kill:
        return ReplayVerdict(
            local=False,
            reason=f"the replay Job ended {remote.resource_kill}, so no verdict: {remote.detail}",
            job_name=remote.job_name,
            tree_hash=tree_hash,
        )
    exit_status = 0 if remote.state == GATE_PASSED else 1 if remote.state == GATE_FAILED else None
    return ReplayVerdict(
        local=False,
        reason=remote.detail,
        job_name=remote.job_name,
        tree_hash=tree_hash,
        exit_status=exit_status,
        output_checksum=remote.output_checksum,
    )
