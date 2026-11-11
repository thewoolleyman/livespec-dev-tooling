"""What a delegated pre-commit run's green verdict leaves behind for later gates.

Two records, for two readers. Suite-green same-tree evidence serves the
commit-msg suite-green leg and is recorded for any green FULL-aggregate verdict
from a named Job. Pre-push evidence serves the delegated pre-push gate alone and
additionally needs the Job's member list and a host that still holds exactly
the judged tree, clean (livespec-dev-tooling's `SPECIFICATION/contracts.md`,
the evidence rule of its delegated pre-commit aggregate section). A doc-only or
Red-leg subset records neither.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling._pre_push_evidence import record_for_worktree
from livespec_dev_tooling.gate_remote_invocation import default_gate_command_runner
from livespec_dev_tooling.green_token import write_pre_commit_evidence

if TYPE_CHECKING:
    import structlog

    from livespec_dev_tooling.pre_commit_delegate import PreCommitVerdict

__all__: list[str] = ["host_holds_tree", "record_delegated_evidence"]


def _git_answer(*, repo_root: Path, argv: list[str]) -> tuple[int, str] | None:
    """One git command's exit status and stripped stdout, or None when it did not run."""
    from returns.result import Success

    outcome = default_gate_command_runner(argv=argv, cwd=repo_root)
    if not isinstance(outcome, Success):
        return None
    result = outcome.unwrap()
    return (result.returncode, result.stdout.strip())


def host_holds_tree(*, repo_root: Path, tree_hash: str) -> bool:
    """Say whether the host still holds exactly the staged tree the Job judged.

    No unstaged change, no untracked non-ignored file, and `git write-tree` still
    naming the submitted tree. Anything unreadable answers False, because pre-push
    evidence must never be claimed for a tree the host cannot show it still holds.
    """
    return (
        _git_answer(repo_root=repo_root, argv=["git", "diff", "--quiet"]) == (0, "")
        and _git_answer(
            repo_root=repo_root, argv=["git", "ls-files", "--others", "--exclude-standard"]
        )
        == (0, "")
        and _git_answer(repo_root=repo_root, argv=["git", "write-tree"]) == (0, tree_hash)
    )


def record_delegated_evidence(
    *, cwd: Path, log: structlog.stdlib.BoundLogger, verdict: PreCommitVerdict
) -> None:
    """Record what a green delegated verdict earned, and say what it did not."""
    if verdict.exit_status != 0:
        return
    if not verdict.full_aggregate:
        log.info(
            "no pre-commit aggregate evidence recorded: the gate Job ran the doc-only or "
            "Red-leg subset for the staged tree, so the pre-push gate still runs every "
            "tree-pure member",
            job_name=verdict.job_name,
            tree_hash=verdict.tree_hash,
        )
        return
    if not (verdict.tree_hash and verdict.job_name and verdict.output_checksum):
        return
    _ = write_pre_commit_evidence(
        cwd=cwd,
        log=log,
        run_id=f"pre-commit-delegate:{verdict.job_name}:{verdict.tree_hash}",
        output_checksum=verdict.output_checksum,
        tree_hash=verdict.tree_hash,
    )
    if verdict.members_passed is None or not verdict.host_unchanged:
        log.info(
            "no pre-push evidence recorded: the gate Job reported no member list, or the "
            "working tree was not clean, or the index no longer names the judged tree",
            job_name=verdict.job_name,
            tree_hash=verdict.tree_hash,
        )
        return
    record_for_worktree(
        cwd=cwd,
        log=log,
        tree_hash=verdict.tree_hash,
        gate_job=verdict.job_name,
        members_passed=verdict.members_passed,
    )
