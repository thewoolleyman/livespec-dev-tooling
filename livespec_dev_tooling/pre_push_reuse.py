"""Run the host half of a qualifying delegated pre-commit verdict."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling import check_authority, check_purity  # noqa: E402
from livespec_dev_tooling._pre_push_evidence import accepted_lines  # noqa: E402
from livespec_dev_tooling.gate_remote_invocation import default_gate_command_runner  # noqa: E402

if TYPE_CHECKING:
    import structlog

__all__: list[str] = ["run_pre_push_command", "run_pre_push_reuse"]

CONTINUE_WITH_OWN_GATE = 3
PRE_PUSH_EVIDENCE = "pre-push-evidence"
PRE_PUSH_REUSE = "pre-push-reuse"
PRE_PUSH_COMMANDS = (PRE_PUSH_EVIDENCE, PRE_PUSH_REUSE)


def _write(*, text: str) -> None:
    """Write an operator-facing reuse result to stdout."""
    _ = sys.stdout.write(text)
    _ = sys.stdout.flush()


def _host_members(
    *, targets: list[str], cwd: Path, log: structlog.stdlib.BoundLogger
) -> tuple[str, ...] | None:
    """Return every given member a qualifying Job verdict cannot stand in for."""
    audited = check_purity.audit_check_purity(targets=tuple(targets), repo_root=cwd)
    if not is_successful(audited):
        malformed = unsafe_perform_io(audited.failure())
        log.error("pre-push reuse: member purity declaration is malformed", member=malformed.target)
        return None
    authority = check_authority.repository_authority_members(repo_root=cwd)
    if not is_successful(authority):
        malformed = unsafe_perform_io(authority.failure())
        log.error(
            "pre-push reuse: member authority declaration is malformed", member=malformed.target
        )
        return None
    audit = unsafe_perform_io(audited.unwrap())
    forced = frozenset(audit.world_reading) | frozenset(audit.undeclared)
    forced |= frozenset(unsafe_perform_io(authority.unwrap()))
    return tuple(target for target in targets if target in forced)


def run_pre_push_reuse(*, cwd: Path, targets: list[str], log: structlog.stdlib.BoundLogger) -> int:
    """Reuse evidence or tell the caller to continue with its normal gate."""
    evidence = accepted_lines(cwd=cwd, log=log)
    if evidence is None:
        return CONTINUE_WITH_OWN_GATE
    gate_job, tree_hash, *passed = evidence
    host_members = _host_members(targets=targets, cwd=cwd, log=log)
    if host_members is None:
        return 1
    passed_members = frozenset(passed)
    forced_members = frozenset(host_members)
    members_to_run = tuple(
        target for target in targets if target not in passed_members or target in forced_members
    )
    skipped = len(targets) - len(members_to_run)
    _write(text=f"pre-push reuse: accepted gate Job {gate_job} for tree {tree_hash}\n")
    for member in members_to_run:
        _write(text=f"pre-push reuse: running member {member} on the pushing host\n")
        completed = default_gate_command_runner(argv=["just", member], cwd=cwd, stream=True)
        if not is_successful(completed) or completed.unwrap().returncode != 0:
            log.error("pre-push reuse: member failed", member=member)
            return 1
    _write(text=f"pre-push reuse: skipped {skipped} member(s) the verdict covered\n")
    return 0


def run_pre_push_command(
    *, command: str, cwd: Path, targets: list[str], log: structlog.stdlib.BoundLogger
) -> int:
    """Dispatch the two command-line readers of delegated pre-commit evidence."""
    if command == PRE_PUSH_REUSE:
        return run_pre_push_reuse(cwd=cwd, targets=targets, log=log)
    lines = accepted_lines(cwd=cwd, log=log)
    _write(text="".join(f"{line}\n" for line in lines or ()))
    return 1 if lines is None else 0
