"""Delegate an opted-in pre-commit aggregate to a staged-tree gate Job."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from livespec_dev_tooling._gate_host_authority import (
    host_authority_decision,
    run_host_authority_members,
)
from livespec_dev_tooling._gate_remote_assembly import declared_gate_check_suite
from livespec_dev_tooling.config import ConfigParseError, load_delegated_pre_commit
from livespec_dev_tooling.gate_credential import gates_kubeconfig_readable
from livespec_dev_tooling.gate_remote_delegate import gate_remote_request, resolve_renderer
from livespec_dev_tooling.gate_remote_invocation import default_gate_command_runner
from livespec_dev_tooling.gate_remote_verdict import (
    GATE_FAILED,
    GATE_PASSED,
    run_gated_push,
)
from livespec_dev_tooling.green_token import write_pre_commit_evidence
from livespec_dev_tooling.incident_gate_entry import IncidentEntrance

__all__: list[str] = ["PreCommitVerdict", "main", "run_pre_commit"]

_GATED_TREE_CHECK = "check-pre-commit-gated-tree"
_LOCAL_FALLBACK = 75


@dataclass(frozen=True, kw_only=True)
class PreCommitVerdict:
    """The pre-commit route and the staged-tree evidence it received."""

    local: bool
    reason: str
    job_name: str | None = None
    tree_hash: str | None = None
    exit_status: int | None = None
    output_checksum: str | None = None
    full_aggregate: bool = False


def run_pre_commit(*, repo_root: Path) -> PreCommitVerdict:
    """Delegate only an eligible opted-in pre-commit aggregate, else gate locally."""
    try:
        enabled = load_delegated_pre_commit(repo_root=repo_root) is True
    except ConfigParseError:
        enabled = False
    if not enabled:
        return PreCommitVerdict(local=True, reason="delegated_pre_commit is not enabled")
    if not gates_kubeconfig_readable():
        return PreCommitVerdict(local=True, reason="gates kubeconfig is not readable")
    tree_hash = _staged_tree_hash(repo_root=repo_root)
    if not tree_hash:
        return PreCommitVerdict(
            local=True,
            reason="the staged tree could not be read, so the pre-commit aggregate gates locally",
        )
    check_suite = _pre_commit_check_suite(repo_root=repo_root)
    if check_suite is None:
        return PreCommitVerdict(
            local=True,
            reason=(
                "the gate check suite could not be read, so the pre-commit aggregate gates locally"
            ),
            tree_hash=tree_hash,
        )
    return _run_remote(repo_root=repo_root, tree_hash=tree_hash, check_suite=check_suite)


def _staged_tree_hash(*, repo_root: Path) -> str:
    """Read the index tree the pre-commit aggregate must gate."""
    from returns.result import Failure

    written = default_gate_command_runner(argv=["git", "write-tree"], cwd=repo_root)
    if isinstance(written, Failure):
        return ""
    return written.unwrap().stdout.strip()


def _staged_tree_selects_full_aggregate(*, repo_root: Path, tree_hash: str) -> bool:
    """Say whether the hook ran the FULL aggregate for the gated tree, else False.

    A Job's exit status is the same for a full pass and for the doc-only or Red-leg
    subset, so the host classifies the staged tree itself: no staged `.py` selects the
    doc-only subset, and exactly one staged `tests/*.py` with no staged
    `livespec_dev_tooling/*.py` selects the Red leg, whatever other `.py` files are
    staged. Anything unreadable answers False, because evidence must never be claimed
    for a run that cannot be shown to be full.
    """
    from returns.result import Failure

    listed = default_gate_command_runner(
        argv=["git", "diff", "-z", "--name-only", "--diff-filter=AM", "HEAD", tree_hash],
        cwd=repo_root,
    )
    if isinstance(listed, Failure) or listed.unwrap().returncode != 0:
        return False
    staged_py = [name for name in listed.unwrap().stdout.split("\0") if name.endswith(".py")]
    if not staged_py:
        return False
    staged_tests = [name for name in staged_py if name.startswith("tests/")]
    staged_impl = [name for name in staged_py if name.startswith("livespec_dev_tooling/")]
    return not (len(staged_tests) == 1 and not staged_impl)


def _staged_commit(*, repo_root: Path, tree_hash: str) -> str:
    """Wrap the index tree in a commit object the gate client can publish."""
    from returns.result import Failure

    argv = [
        "git",
        "-c",
        "user.name=livespec-pre-commit",
        "-c",
        "user.email=pre-commit@livespec.invalid",
        "commit-tree",
        tree_hash,
        "-p",
        "HEAD",
        "-mpre-commit aggregate of the staged tree",
    ]
    committed = default_gate_command_runner(argv=argv, cwd=repo_root)
    if isinstance(committed, Failure):
        return ""
    return committed.unwrap().stdout.strip()


def _pre_commit_check_suite(*, repo_root: Path) -> tuple[str, ...] | None:
    """Keep the declared bootstrap while substituting the staged-tree aggregate."""
    from returns.result import Failure

    declared = declared_gate_check_suite(repo_root=repo_root)
    if isinstance(declared, Failure):
        return None
    return (*declared.unwrap()[:-1], _GATED_TREE_CHECK)


def _run_remote(
    *, repo_root: Path, tree_hash: str, check_suite: tuple[str, ...]
) -> PreCommitVerdict:
    """Run the aggregate remotely and accept only a matching staged-tree verdict."""
    from returns.result import Failure

    built = gate_remote_request(
        repo_root=repo_root,
        renderer=resolve_renderer(repo_root=repo_root),
        runner=default_gate_command_runner,
        tree_hash=tree_hash,
        check_suite=check_suite,
    )
    if isinstance(built, Failure):
        return PreCommitVerdict(
            local=True,
            reason=f"the gate Job could not be submitted: {built.failure().detail}",
            tree_hash=tree_hash,
        )
    source = _staged_commit(repo_root=repo_root, tree_hash=tree_hash)
    if not source:
        return PreCommitVerdict(
            local=True,
            reason=(
                "the staged tree could not be committed for the gate, so the aggregate "
                "gates locally"
            ),
            tree_hash=tree_hash,
        )
    request = replace(built.unwrap(), source_ref=source, capture_output=True)
    remote = run_gated_push(request=request, runner=default_gate_command_runner)
    if remote.tree_hash != tree_hash:
        return PreCommitVerdict(
            local=True,
            reason=(
                "the gate Job did not return a verdict for the staged tree, so the aggregate "
                "gates locally"
            ),
            job_name=remote.job_name,
            tree_hash=tree_hash,
        )
    if remote.state == GATE_PASSED:
        joined = host_authority_decision(
            verdict=remote,
            ran=run_host_authority_members(
                repo_root=repo_root, tree_hash=tree_hash, runner=default_gate_command_runner
            ),
        )
        return PreCommitVerdict(
            local=False,
            reason=joined.detail,
            job_name=joined.job_name,
            tree_hash=tree_hash,
            exit_status=0 if joined.state == GATE_PASSED else 1,
            output_checksum=joined.output_checksum,
            full_aggregate=_staged_tree_selects_full_aggregate(
                repo_root=repo_root, tree_hash=tree_hash
            ),
        )
    if remote.state == GATE_FAILED:
        return PreCommitVerdict(
            local=False,
            reason=remote.detail,
            job_name=remote.job_name,
            tree_hash=tree_hash,
            exit_status=1,
            output_checksum=remote.output_checksum,
        )
    return PreCommitVerdict(
        local=True,
        reason=(
            "the gate Job reached no verdict for the staged tree, so the aggregate gates locally"
        ),
        job_name=remote.job_name,
        tree_hash=tree_hash,
    )


@IncidentEntrance(surface="pre-commit-delegate")
def main() -> int:
    """Run the selected route and report whether the shell must fall back locally."""
    import structlog

    parser = argparse.ArgumentParser(description="Delegate an opted-in pre-commit aggregate.")
    _ = parser.add_argument("command", choices=["run"])
    _ = parser.parse_args()
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    verdict = run_pre_commit(repo_root=Path.cwd())
    log = structlog.get_logger("pre_commit_delegate")
    if verdict.local:
        if verdict.reason != "delegated_pre_commit is not enabled":
            log.warning(
                "GATED_LOCALLY",
                reason=verdict.reason,
                job_name=verdict.job_name,
                tree_hash=verdict.tree_hash,
            )
        return _LOCAL_FALLBACK
    log.info(
        "delegated pre-commit aggregate completed",
        job_name=verdict.job_name,
        tree_hash=verdict.tree_hash,
        exit_status=verdict.exit_status,
        output_checksum=verdict.output_checksum,
        reason=verdict.reason,
    )
    if verdict.exit_status == 0 and not verdict.full_aggregate:
        log.info(
            "no pre-commit aggregate evidence recorded: the gate Job ran the doc-only or "
            "Red-leg subset for the staged tree, so the pre-push gate still runs every "
            "tree-pure member",
            job_name=verdict.job_name,
            tree_hash=verdict.tree_hash,
        )
    elif (
        verdict.exit_status == 0
        and verdict.tree_hash
        and verdict.job_name
        and verdict.output_checksum
    ):
        _ = write_pre_commit_evidence(
            cwd=Path.cwd(),
            log=log,
            run_id=f"pre-commit-delegate:{verdict.job_name}:{verdict.tree_hash}",
            output_checksum=verdict.output_checksum,
            tree_hash=verdict.tree_hash,
        )
    return 1 if verdict.exit_status is None else verdict.exit_status


if __name__ == "__main__":
    raise SystemExit(main())
