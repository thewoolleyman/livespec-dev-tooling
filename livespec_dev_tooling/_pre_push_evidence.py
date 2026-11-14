"""Pre-push evidence: a delegated pre-commit gate Job's green verdict for one tree.

livespec-dev-tooling's `SPECIFICATION/contracts.md` has the pre-commit hook
record this after a gate Job's green verdict for the FULL aggregate of a clean
staged tree (the evidence rule of its delegated pre-commit aggregate section),
and makes the delegated pre-push gate's same-tree pre-commit verdict rule its
only reader. It lives in a file of its own, beside the green token and
never inside it, so the green token's reader cannot mistake it for a token and a
local aggregate has no path that writes it.

The record names the gate Job in a field of its own. A record without one is
not evidence, and neither is one whose member list cannot be read whole.
"""

from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, cast

from livespec_dev_tooling._green_token_git import (
    git_dir,
    head_tree_hash,
    repo_root,
    worktree_is_clean,
)
from livespec_dev_tooling._pre_push_cluster_record import (
    Evidence,
)
from livespec_dev_tooling._pre_push_cluster_record import (
    confirmation as _cluster_confirmation,
)
from livespec_dev_tooling.config import (
    ConfigParseError,
    load_delegated_gate,
    load_delegated_pre_commit,
)
from livespec_dev_tooling.gate_remote_invocation import (
    default_gate_command_runner,
)

if TYPE_CHECKING:
    import structlog

__all__: list[str] = [
    "PRE_PUSH_EVIDENCE_FILE",
    "PrePushEvidence",
    "accepted_lines",
    "both_delegated_keys",
    "clear_evidence",
    "clear_for_worktree",
    "pre_commit_hook_writes_no_token",
    "read_evidence",
    "record_for_worktree",
    "refuses_pre_commit_token",
    "write_evidence",
]

PRE_PUSH_EVIDENCE_FILE = "livespec-pre-push-evidence.json"


class PrePushEvidence(NamedTuple):
    """A gate Job's green full-aggregate verdict for one staged tree."""

    tree_hash: str
    gate_job: str
    members_passed: tuple[str, ...]
    captured_at: str


def both_delegated_keys(*, repo_root: Path) -> bool:
    """True only when `delegated_gate` AND `delegated_pre_commit` are the literal `true`."""
    try:
        return (
            load_delegated_gate(repo_root=repo_root) is True
            and load_delegated_pre_commit(repo_root=repo_root) is True
        )
    except ConfigParseError:
        return False


def write_evidence(
    *, path: Path, tree_hash: str, gate_job: str, members_passed: tuple[str, ...]
) -> PrePushEvidence:
    """Write the record and return the values persisted."""
    evidence = PrePushEvidence(
        tree_hash=tree_hash,
        gate_job=gate_job,
        members_passed=members_passed,
        captured_at=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
    _ = path.write_text(
        json.dumps(
            {
                "tree_hash": evidence.tree_hash,
                "gate_job": evidence.gate_job,
                "members_passed": list(evidence.members_passed),
                "captured_at": evidence.captured_at,
            }
        ),
        encoding="utf-8",
    )
    return evidence


def read_evidence(*, path: Path) -> PrePushEvidence | None:
    """The record at `path`, or None when it is absent, unreadable or incomplete."""
    try:
        record = cast("dict[str, object]", json.loads(path.read_text(encoding="utf-8")))
        tree_hash, gate_job, captured_at = (
            record["tree_hash"],
            record["gate_job"],
            record["captured_at"],
        )
        members: object = record["members_passed"]
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        return None
    scalars = (tree_hash, gate_job, captured_at)
    if not all(isinstance(value, str) and value for value in scalars):
        return None
    if not isinstance(members, list):
        return None
    listed = cast("list[object]", members)
    if not all(isinstance(member, str) and member for member in listed):
        return None
    return PrePushEvidence(
        tree_hash=cast("str", tree_hash),
        gate_job=cast("str", gate_job),
        members_passed=tuple(cast("list[str]", listed)),
        captured_at=cast("str", captured_at),
    )


def clear_evidence(*, path: Path) -> None:
    """Remove any earlier record, so only the latest pre-commit run can leave one."""
    path.unlink(missing_ok=True)


def _evidence_path(*, cwd: Path) -> Path:
    """The worktree's pre-push evidence path, beside its green token."""
    return git_dir(cwd=cwd) / PRE_PUSH_EVIDENCE_FILE


def clear_for_worktree(*, cwd: Path) -> None:
    """Drop the worktree's earlier record; outside a git worktree there is none."""
    try:
        path = _evidence_path(cwd=cwd)
    except (OSError, subprocess.CalledProcessError):
        return
    clear_evidence(path=path)


def record_for_worktree(
    *,
    cwd: Path,
    log: structlog.stdlib.BoundLogger,
    tree_hash: str,
    gate_job: str,
    members_passed: tuple[str, ...],
) -> None:
    """Record a gate Job's green full-aggregate verdict for the worktree's pre-push gate."""
    evidence = write_evidence(
        path=_evidence_path(cwd=cwd),
        tree_hash=tree_hash,
        gate_job=gate_job,
        members_passed=members_passed,
    )
    log.info(
        "pre-push evidence written",
        tree_hash=evidence.tree_hash,
        gate_job=evidence.gate_job,
        members_passed=len(evidence.members_passed),
    )


def accepted_lines(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> tuple[str, ...] | None:
    """The gate Job, the tree, then each member, of a verdict this push may accept.

    It qualifies only in a repository that sets both delegated keys, when the
    record names its gate Job, the worktree is clean and its HEAD tree is the
    tree the record names. Anything else answers None.
    """
    if not both_delegated_keys(repo_root=repo_root(cwd=cwd)):
        return None
    evidence = read_evidence(path=_evidence_path(cwd=cwd))
    if evidence is None:
        log.info("pre-push evidence: none recorded for a delegated pre-commit gate Job")
        return None
    current = head_tree_hash(cwd=cwd)
    if current != evidence.tree_hash or not worktree_is_clean(cwd=cwd):
        log.info(
            "pre-push evidence: not accepted, the worktree is dirty or its HEAD tree differs",
            evidence_tree_hash=evidence.tree_hash,
            current_tree_hash=current,
            gate_job=evidence.gate_job,
        )
        return None
    confirmation = _cluster_confirmation(
        evidence=Evidence(
            tree_hash=evidence.tree_hash,
            gate_job=evidence.gate_job,
            members_passed=evidence.members_passed,
        ),
        cwd=cwd,
        runner=default_gate_command_runner,
    )
    if confirmation.missing:
        log.info(
            "pre-push evidence: the cluster no longer holds the gate Job record",
            gate_job=evidence.gate_job,
        )
        return None
    if not confirmation.matches:
        log.info(
            "pre-push evidence: the cluster record disagrees with the evidence",
            gate_job=evidence.gate_job,
            disagreements=[
                {"field": field, "evidence": expected, "cluster": actual}
                for field, expected, actual in confirmation.disagreements
            ],
        )
        return None
    return (evidence.gate_job, evidence.tree_hash, *evidence.members_passed)


def pre_commit_hook_writes_no_token(*, cwd: Path) -> bool:
    """True where the pre-commit hook's local aggregate must not write the green token."""
    return both_delegated_keys(repo_root=repo_root(cwd=cwd))


def refuses_pre_commit_token(*, cwd: Path, token_path: Path) -> bool:
    """True when the token is pre-commit aggregate evidence in a both-keys repository.

    There a pre-commit pass stands in for the pre-push gate only through this
    module's own evidence, never through the green token.
    """
    try:
        token: object = json.loads(token_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    if not isinstance(token, dict) or "pre_commit_aggregate" not in token:
        return False
    return both_delegated_keys(repo_root=repo_root(cwd=cwd))
