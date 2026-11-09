"""Collect a reverted incident's original run with no operator command.

A tick reads only the controller's own durable record and the reference clone. Once the
recovery action for the registered landed attempt is completed with a published revert,
the revert commit is found on the branch by the `Incident-Action` trailer the inverse
stamps on it, and the original run is collected against the graph its workflow declares
at the merge revision. Collection is idempotent by evidence digest, so a tick that runs
twice, or after a restart, leaves one evidence record on the incident item.
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
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling._incident_run_types import EvidenceRefusal
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


@dataclass(frozen=True, kw_only=True)
class WatchTick:
    """What one tick did: idle, waiting on a revert, refused by name, or collected."""

    status: str
    detail: str = ""


@impure_safe
def _landed(*, state_dir: Path, repository: str) -> tuple[ObserverRegistration, str] | None:
    """The registered attempt and its recovery action id, once a revert was published."""
    with repository_lock(directory=state_dir, repository=repository) as path:
        record = load_record(path=path)
    registration = read_registration(record=record)
    if registration is None or registration.repository != repository:
        return None
    identity = recovery_action_id(registration=registration)
    actions = record.get("actions")
    action = cast("dict[str, object]", actions).get(identity) if isinstance(actions, dict) else None
    receipt = cast("dict[str, object]", action).get("receipt") if isinstance(action, dict) else None
    completed = isinstance(action, dict) and cast("dict[str, object]", action).get("status") == (
        "completed"
    )
    if not completed or not isinstance(receipt, str) or receipt.startswith(_NO_REVERT_PREFIX):
        return None
    return registration, identity


@impure_safe
def _revert_sha(*, ports: EntryPorts, registration: ObserverRegistration, identity: str) -> str:
    """The commit the inverse published, found by its trailer on the reference clone's branch."""
    found = ports.git(
        [
            "rev-list",
            "-n1",
            "--fixed-strings",
            f"--grep=Incident-Action: {identity}",
            f"origin/{registration.branch}",
        ],
        b"",
    )
    return found.decode().strip()


def watch_once(*, state_dir: Path, repository: str, ports: EntryPorts) -> WatchTick:
    """Collect the registered original run if its revert has landed; otherwise do nothing."""
    landed = _landed(state_dir=state_dir, repository=repository)
    found = unsafe_perform_io(landed.unwrap()) if is_successful(landed) else None
    if found is None:
        return WatchTick(status="idle")
    registration, identity = found
    revert = _revert_sha(ports=ports, registration=registration, identity=identity)
    if not is_successful(revert):
        return WatchTick(status="waiting", detail="the published revert is not on the branch yet")
    result = collect(
        request=Collection(
            state_dir=state_dir,
            repository=repository,
            revert_sha=unsafe_perform_io(revert.unwrap()),
        ),
        ports=ports,
    )
    status, detail = (
        ("refused", f"{result.code}: {result.detail}")
        if isinstance(result, EvidenceRefusal)
        else ("collected", evidence_digest(evidence=result))
    )
    return WatchTick(status=status, detail=detail)
