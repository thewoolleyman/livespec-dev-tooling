"""Collect a reverted incident's original run with no operator command.

A tick reads only the controller's own durable record and the reference clone. Once the
recovery action for the registered landed attempt is completed with a published revert,
the revert commit is found on the branch by the `Incident-Action` trailer the inverse
stamps on it, and the original run is collected against the graph its workflow declares
at the merge revision. A run still in progress is waited on: the next tick retries it
until the run is terminal. The controller's record then marks the collection done, so a
later tick, or one after a restart, reads the record and does nothing. If the process
stops between recording the evidence and marking it, the next tick collects again;
collection is idempotent by evidence digest, so the incident item keeps one record.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_registration,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling._incident_run_types import EvidenceRefusal, RunEvidence
from livespec_dev_tooling.incident_observer import recovery_action_id
from livespec_dev_tooling.incident_original_run_flows import Collection, EntryPorts, collect
from livespec_dev_tooling.incident_run_evidence import evidence_digest

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

__all__: list[str] = ["WatchTick", "watch_once"]

# The receipt of a rollback the principal could not apply: no revert landed.
_NO_REVERT_PREFIX = "rollback-conflict:"
_COLLECTIONS = "original_run_collections"
_IN_PROGRESS = "incident-original-run-in-progress"


@dataclass(frozen=True, kw_only=True)
class WatchTick:
    """What one tick did: idle, waiting, refused by name, collected, or already done."""

    status: str
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class _Landed:
    registration: ObserverRegistration
    identity: str
    collected: bool


def _object(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


@impure_safe
def _landed(*, state_dir: Path, repository: str) -> _Landed | None:
    """The registered attempt and its recovery action id, once a revert was published."""
    with repository_lock(directory=state_dir, repository=repository) as path:
        record = load_record(path=path)
    registration = read_registration(record=record)
    if registration is None or registration.repository != repository:
        return None
    identity = recovery_action_id(registration=registration)
    action = _object(value=_object(value=record.get("actions")).get(identity))
    receipt = action.get("receipt")
    if action.get("status") != "completed" or not isinstance(receipt, str):
        return None
    if not receipt or receipt.startswith(_NO_REVERT_PREFIX):
        return None
    collected = identity in _object(value=record.get(_COLLECTIONS))
    return _Landed(registration=registration, identity=identity, collected=collected)


@impure_safe
def _revert_sha(*, ports: EntryPorts, landed: _Landed) -> str:
    """The commit the inverse published, found by its trailer on the reference clone's branch."""
    found = ports.git(
        [
            "rev-list",
            "-n1",
            "--fixed-strings",
            f"--grep=Incident-Action: {landed.identity}",
            f"origin/{landed.registration.branch}",
        ],
        b"",
    )
    sha = found.decode().strip()
    if not sha:
        raise LookupError(landed.identity)
    return sha


@impure_safe
def _mark_collected(*, state_dir: Path, landed: _Landed, evidence: RunEvidence) -> None:
    with repository_lock(directory=state_dir, repository=landed.registration.repository) as path:
        record = load_record(path=path)
        marks = _object(value=record.get(_COLLECTIONS)).copy()
        marks[landed.identity] = {
            "digest": evidence_digest(evidence=evidence),
            "run_id": evidence.original.run_id,
        }
        record[_COLLECTIONS] = marks
        save_record(path=path, record=record)


def _tick(*, state_dir: Path, landed: _Landed, revert_sha: str, ports: EntryPorts) -> WatchTick:
    result = collect(
        request=Collection(
            state_dir=state_dir, repository=landed.registration.repository, revert_sha=revert_sha
        ),
        ports=ports,
    )
    if isinstance(result, EvidenceRefusal):
        status = "waiting" if result.code == _IN_PROGRESS else "refused"
        return WatchTick(status=status, detail=f"{result.code}: {result.detail}")
    _ = _mark_collected(state_dir=state_dir, landed=landed, evidence=result)
    return WatchTick(status="collected", detail=evidence_digest(evidence=result))


def watch_once(*, state_dir: Path, repository: str, ports: EntryPorts) -> WatchTick:
    """Collect the registered original run if its revert has landed; otherwise do nothing."""
    found = _landed(state_dir=state_dir, repository=repository)
    landed = unsafe_perform_io(found.unwrap()) if is_successful(found) else None
    if landed is None:
        return WatchTick(status="idle")
    if landed.collected:
        return WatchTick(status="done")
    revert = _revert_sha(ports=ports, landed=landed)
    if not is_successful(revert):
        return WatchTick(status="waiting", detail="the published revert is not on the branch yet")
    return _tick(
        state_dir=state_dir,
        landed=landed,
        revert_sha=unsafe_perform_io(revert.unwrap()),
        ports=ports,
    )
