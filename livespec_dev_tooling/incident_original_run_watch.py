"""Collect a reverted incident's original run with no operator command.

A tick reads only the controller's own durable record and the reference clone. Once the
recovery action for the registered landed attempt is completed with a `recovery-inverse`
receipt, the revert is the commit that receipt names, never a search of the branch: it
must be on the branch and quote the `Incident-Action` trailer the inverse stamps on it.
The original run is then collected against the graph its workflow declares at the merge
revision. A run still in progress is waited on: the next tick retries it
until the run is terminal. The controller's record then marks the collection done, so a
later tick, or one after a restart, reads the record and does nothing. If the process
stops between recording the evidence and marking it, the next tick collects again;
collection is idempotent by evidence digest, so the incident item keeps one record.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from livespec_dev_tooling._incident_observer_ack import recovery_action_id
from livespec_dev_tooling._incident_observer_store import (
    load_record,
    read_registration,
    repository_lock,
    save_record,
)
from livespec_dev_tooling._incident_observer_types import ObserverRegistration
from livespec_dev_tooling._incident_original_run_ports import bound_ports
from livespec_dev_tooling._incident_run_types import EvidenceRefusal, RunEvidence
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_original_run_flows import Collection, EntryPorts, collect
from livespec_dev_tooling.incident_run_evidence import evidence_digest

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402
from returns.pipeline import is_successful  # noqa: E402
from returns.unsafe import unsafe_perform_io  # noqa: E402

__all__: list[str] = ["OriginalRunWatcher", "WatchTick", "installed_watcher", "watch_once"]

_COMMIT = re.compile(r"[0-9a-f]{40}")
_COLLECTIONS = "original_run_collections"
_IN_PROGRESS = "incident-original-run-in-progress"
_QUIET = frozenset({"idle", "done"})


@dataclass(frozen=True, kw_only=True)
class WatchTick:
    """What one tick did: idle, waiting, refused by name, collected, or already done."""

    status: str
    detail: str = ""


@dataclass(frozen=True, kw_only=True)
class _Landed:
    registration: ObserverRegistration
    identity: str
    revert_sha: str
    collected: bool


def _object(*, value: object) -> dict[str, object]:
    return cast("dict[str, object]", value) if isinstance(value, dict) else {}


def _published_commit(*, identity: str, receipt: str) -> str | None:
    """The commit a `recovery-inverse` receipt for this action names; None for any other."""
    prefix = f"recovery-inverse:{identity}:commit:"
    commit = receipt.removeprefix(prefix) if receipt.startswith(prefix) else ""
    return commit if _COMMIT.fullmatch(commit) else None


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
    revert = _published_commit(identity=identity, receipt=receipt)
    if revert is None:
        return None
    collected = identity in _object(value=record.get(_COLLECTIONS))
    return _Landed(
        registration=registration, identity=identity, revert_sha=revert, collected=collected
    )


@impure_safe
def _published_revert(*, ports: EntryPorts, landed: _Landed) -> str:
    """The recorded inverse commit, once the branch carries it and it quotes its action."""
    _ = ports.git(
        [
            "merge-base",
            "--is-ancestor",
            landed.revert_sha,
            f"origin/{landed.registration.branch}",
        ],
        b"",
    )
    message = ports.git(["show", "-s", "--format=%B", landed.revert_sha], b"").decode()
    if f"Incident-Action: {landed.identity}" not in message.splitlines():
        raise LookupError(landed.identity)
    return landed.revert_sha


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
    revert = _published_revert(ports=ports, landed=landed)
    if not is_successful(revert):
        return WatchTick(
            status="waiting", detail="the published revert is not on the branch with its trailer"
        )
    return _tick(
        state_dir=state_dir,
        landed=landed,
        revert_sha=unsafe_perform_io(revert.unwrap()),
        ports=ports,
    )


@dataclass(frozen=True, kw_only=True)
class OriginalRunWatcher:
    """Ticks the collection on an interval for the life of the controller process.

    The only state is the controller's durable record, so a restarted process resumes
    exactly where the last one stopped. Ports are built per tick and only when a
    collection is owed, so an idle controller never fetches the reference clone.
    """

    state_dir: Path
    repository: str
    ports: Callable[[], EntryPorts | None]
    interval_seconds: float = 60.0
    stop: threading.Event = field(default_factory=threading.Event)
    failed: threading.Event = field(default_factory=threading.Event)

    def tick(self) -> WatchTick:
        """Collect if a collection is owed and the tenant credential is available."""
        owed = _landed(state_dir=self.state_dir, repository=self.repository)
        landed = unsafe_perform_io(owed.unwrap()) if is_successful(owed) else None
        if landed is None or landed.collected:
            return WatchTick(status="idle")
        ports = self.ports()
        if ports is None:
            return WatchTick(status="waiting", detail="the tenant credential is unavailable")
        return watch_once(state_dir=self.state_dir, repository=self.repository, ports=ports)

    def run(self) -> None:
        """Tick until stopped; a tick that cannot reach its inputs is retried next interval.

        Each outcome that differs from the previous tick's is named on stderr, which the
        service unit sends to the journal. Only the expected input failures are absorbed:
        any other error is a bug and ends the loop, so `start` can end the service.
        """
        previous = WatchTick(status="idle")
        while not self.stop.wait(self.interval_seconds):
            try:
                current = self.tick()
            except (OSError, subprocess.SubprocessError, ValueError) as error:
                current = WatchTick(status="failed", detail=str(error))
            if current != previous and current.status not in _QUIET:
                _ = sys.stderr.write(
                    f"incident-original-run-watch: {current.status}: {current.detail}\n"
                )
            previous = current

    def start(self, *, on_exit: Callable[[], None]) -> threading.Thread:
        """Run the watcher on a daemon thread; `on_exit` runs if it ends without being stopped.

        A daemon thread that dies leaves the service answering HTTP with nothing collecting,
        so the service passes its own shutdown and exits non-zero for systemd to restart it.
        """
        thread = threading.Thread(
            target=self._supervised,
            kwargs={"on_exit": on_exit},
            name="incident-original-run-watcher",
            daemon=True,
        )
        thread.start()
        return thread

    def _supervised(self, *, on_exit: Callable[[], None]) -> None:
        try:
            self.run()
        finally:
            if not self.stop.is_set():
                self.failed.set()
                on_exit()


def installed_watcher(
    *, installation: ControllerInstallation, interval_seconds: float = 60.0
) -> OriginalRunWatcher:
    """The watcher bound to one verified controller installation."""
    return OriginalRunWatcher(
        state_dir=installation.state,
        repository=installation.repository,
        ports=lambda: bound_ports(installation=installation),
        interval_seconds=interval_seconds,
    )
