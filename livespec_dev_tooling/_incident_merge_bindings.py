"""Production bindings for the incident-merge principal's `chain`, `queue` and `record` seams.

`incident_merge_principal.merge_incident_repair` takes every collaborator as an injected
seam. This module binds the three that touch the host, for the runner:

- ARM IDENTITY. The canonical `read-current` reader needs the attempt's identity (attempt,
  phase, operation, generation, owner), which neither the pull request nor the principal's
  interface carries. The observer already holds it durably in the repository's pre-merge arm
  record, so the runner reads that record (read-only) and refuses unless it is for THIS pull
  request. A wrong identity can only make the chain refuse; the chain stays the sole authority.
- CHAIN. `read-current` through the registered canonical process, never caller JSON.
- GATING READS. The label, the effective required checks and the queue are read with the
  merge App's OWN installation token (`token_forge_reader`), never the host's ambient `gh`
  credential, so the permissions the App was granted are the permissions the decision rests on.
- QUEUE. One GraphQL `mergeQueue` read, parsed by the principal's own parser; a failed read
  raises `QueueUnreadableError`, which the principal records and never gates on.
- RECORD. One comment on the incident work item through the credential wrapper.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import Any, Protocol

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from livespec_runtime_budget.github_budget import GhInvocation  # noqa: E402 — vendor path.
from returns.result import Failure  # noqa: E402 — vendor-path-aware import.

from livespec_dev_tooling._incident_observer_store import (  # noqa: E402
    load_record,
    read_observer_arm,
    record_path,
)
from livespec_dev_tooling.budgeted_gh import gh_read  # noqa: E402
from livespec_dev_tooling.checks._effective_required_checks import (  # noqa: E402
    ForgeReader,
)
from livespec_dev_tooling.incident_authority_client import (  # noqa: E402
    AuthorityRefusal,
    call_authority,
)
from livespec_dev_tooling.incident_merge_authority import MergeChainReader  # noqa: E402
from livespec_dev_tooling.incident_merge_principal import (  # noqa: E402
    IncidentRecorder,
    QueueEntries,
    QueueUnreadableError,
    queue_entries_ahead,
)
from livespec_dev_tooling.incident_strict_json import (  # noqa: E402
    IncidentJsonRefusalError,
    strict_json,
)

__all__: list[str] = [
    "ArmIdentity",
    "LedgerWriteError",
    "authority_chain_reader",
    "authority_command",
    "graphql_queue_reader",
    "ledger_recorder",
    "read_arm_identity",
    "token_forge_reader",
]

_WRAPPER = "/usr/local/bin/with-livespec-env.sh"
_TIMEOUT_SECONDS = 60
_QUERY = (
    "query($owner: String!, $name: String!) { repository(owner: $owner, name: $name) {"
    " mergeQueue { entries(first: 100) { nodes { position pullRequest { number } } } } } }"
)


class TextRunner(Protocol):
    """Runs one fixed argv and reports its exit status with its output (or why it never ran)."""

    def __call__(self, *, argv: Sequence[str]) -> tuple[int, str]: ...


class LedgerWriteError(Exception):
    """The ledger comment was not written; the outcome it describes may still have happened."""

    def __init__(self, *, incident_id: str, code: int, detail: str) -> None:
        super().__init__(f"the ledger comment on {incident_id} failed ({code}): {detail[:200]}")


@dataclass(frozen=True, kw_only=True)
class ArmIdentity:
    """The incident attempt the observer armed for one pull request."""

    incident_id: str
    attempt_id: str
    phase: str
    operation_id: str
    generation: int
    owner: str


def run_text(*, argv: Sequence[str]) -> tuple[int, str]:
    """Run one fixed argv without a shell; (-1, reason) when it could not run to an exit."""
    try:
        done = subprocess.run(  # noqa: S603 — fixed argv built here; no shell.
            list(argv), capture_output=True, text=True, timeout=_TIMEOUT_SECONDS, check=False
        )
    except (OSError, subprocess.SubprocessError) as unusable:
        return -1, f"{type(unusable).__name__}: {unusable}"
    return done.returncode, done.stdout if done.returncode == 0 else done.stderr


def read_arm_identity(*, state_dir: Path, repository: str, pr_number: int) -> ArmIdentity | str:
    """The armed attempt for `pr_number`, or the reason there is none."""
    try:
        record = load_record(path=record_path(directory=state_dir, repository=repository))
        arm = read_observer_arm(record=record)
    except (OSError, ValueError, TypeError, IncidentJsonRefusalError) as unreadable:
        return f"the observer's arm record is unreadable: {type(unreadable).__name__}"
    if arm is None:
        return f"no pre-merge arm is recorded for {repository}"
    if arm.pr_number != pr_number:
        return f"the recorded arm is for pull request {arm.pr_number}, not {pr_number}"
    return ArmIdentity(
        incident_id=arm.incident_item_id,
        attempt_id=arm.attempt_id,
        phase=arm.phase,
        operation_id=arm.operation_id,
        generation=arm.generation,
        owner=arm.owner,
    )


def authority_command(*, interpreter: Path, script: Path) -> list[str]:
    """The canonical authority process: the credential wrapper, then the serving interpreter."""
    return [_WRAPPER, "--", str(interpreter), str(script)]


def authority_chain_reader(
    *, command: Sequence[str], repository: str, repo: Path, identity: ArmIdentity
) -> MergeChainReader:
    """`read-current` for the armed attempt through the registered canonical process."""

    def read(*, incident_id: str) -> Any:
        if incident_id != identity.incident_id:
            return Failure(
                AuthorityRefusal(
                    code="incident-merge-runner-incident-mismatch",
                    detail=f"asked for {incident_id}, armed for {identity.incident_id}",
                )
            )
        flags = {
            "repo": str(repo),
            "repository": repository,
            "item": identity.incident_id,
            "attempt": identity.attempt_id,
            "phase": identity.phase,
            "operation": identity.operation_id,
            "generation": str(identity.generation),
            "owner": identity.owner,
        }
        return call_authority(command=command, action="read-current", flags=flags, cwd=repo)

    return read


def graphql_queue_reader(*, read: ForgeReader) -> QueueEntries:
    """The queue entries ahead of a pull request from one budgeted GraphQL read."""

    def queue(*, repo: str, pr_number: int) -> tuple[int, ...]:
        owner, _, name = repo.partition("/")
        args = ["api", "graphql", "-f", f"query={_QUERY}", "-F", f"owner={owner}"]
        answer = read(args=[*args, "-F", f"name={name}"])
        if answer.returncode != 0:
            raise QueueUnreadableError(detail=f"the queue read exited {answer.returncode}")
        try:
            payload = strict_json(text=answer.stdout, limit=None)
        except IncidentJsonRefusalError as unreadable:
            raise QueueUnreadableError(detail="the queue answer was not JSON") from unreadable
        return queue_entries_ahead(payload=payload, pr_number=pr_number)

    return queue


def ledger_recorder(*, run: TextRunner = run_text) -> IncidentRecorder:
    """One ledger comment on the incident work item, through the credential wrapper."""

    def record(*, incident_id: str, text: str) -> None:
        code, detail = run(argv=[_WRAPPER, "--", "bd", "comment", incident_id, text])
        if code != 0:
            raise LedgerWriteError(incident_id=incident_id, code=code, detail=detail)

    return record


def token_forge_reader(*, token: str, spawn: Callable[..., Any] = subprocess.run) -> ForgeReader:
    """The budgeted `gh` read, started with the App installation token in the child's environment.

    The budgeted client still builds the argv, spends the budget and reads the answer; only
    the process start is this module's. The token reaches the child through `GH_TOKEN` alone,
    so it is in no argv, no `GhInvocation` and no message this module writes.
    """
    environment = {
        "GH_TOKEN": token,
        "GH_PROMPT_DISABLED": "1",
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/"),
    }

    def execute(*, argv: list[str]) -> GhInvocation:
        try:
            done = spawn(
                argv,
                capture_output=True,
                text=True,
                check=False,
                timeout=_TIMEOUT_SECONDS,
                env=environment,
            )
        except (OSError, subprocess.SubprocessError) as unusable:
            return GhInvocation(argv=shlex.join(argv), unspawnable=type(unusable).__name__)
        return GhInvocation(
            argv=shlex.join(argv),
            stdout=done.stdout,
            stderr=done.stderr,
            returncode=done.returncode,
        )

    return partial(gh_read, execute=execute)
