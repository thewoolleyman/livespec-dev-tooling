"""Protected effect records, independent of tenant and caller-held observer locks."""

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling._incident_observer_store import repository_lock, save_record
from livespec_dev_tooling._incident_observer_types import RecoveryIntent
from livespec_dev_tooling._incident_recovery_journal_history import JournalHistory
from livespec_dev_tooling._incident_recovery_journal_identity import JournalCodec
from livespec_dev_tooling._incident_recovery_journal_types import JournalResult, RetainedAction
from livespec_dev_tooling.incident_controller_installation import ControllerInstallation
from livespec_dev_tooling.incident_strict_json import IncidentJsonRefusalError

__all__: list[str] = ["JournalStore"]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac
_MAX_RECORD = 16 * 1024 * 1024
_UNAVAILABLE = "protected recovery action or effect history unavailable"


def _resolved(*, path: Path) -> Path:
    try:
        return path.resolve(strict=True)
    except RuntimeError as error:
        raise OSError(_UNAVAILABLE) from error


def _protected(*, path: Path) -> bool:
    resolved = _resolved(path=path)
    for entry in (path, *path.parents, resolved, *resolved.parents):
        link, target = entry.lstat(), entry.stat()
        sticky = entry.is_dir() and target.st_uid == 0 and bool(target.st_mode & stat.S_ISVTX)
        if (
            link.st_uid not in {0, os.geteuid()}
            or target.st_uid not in {0, os.geteuid()}
            or (target.st_mode & 0o022 and not sticky)
        ):
            return False
    return path.is_absolute()


def _private(*, path: Path, directory: bool = False) -> None:
    mode = path.stat().st_mode
    valid_kind = stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)
    if not (_protected(path=path) and valid_kind and not stat.S_IMODE(mode) & 0o077):
        message = "unprotected recovery journal path"
        raise OSError(message)


def _record(*, path: Path) -> dict[str, Any]:
    _private(path=path)
    with path.open("rb") as stream:
        raw = stream.read(_MAX_RECORD + 1)
    data: Any = JournalCodec.decode(raw=raw, limit=_MAX_RECORD)
    if not isinstance(data, dict):
        message = "invalid protected journal object"
        raise TypeError(message)
    return cast("dict[str, Any]", data)


def _contained(*, path: Path, parent: Path) -> None:
    if _resolved(path=path).parent != _resolved(path=parent):
        message = "recovery journal path escapes provisioned directory"
        raise OSError(message)


@dataclass(frozen=True, kw_only=True)
class JournalStore:
    """Preserve one exact action result under a separate effect-journal lock.

    Writers acquire or borrow the observer repository fence first. This class
    never writes the observer record. Lookup authenticates a point-in-time
    retained-action snapshot before journal access.
    """

    installation: ControllerInstallation

    def perform(
        self, *, operation: str, intent: RecoveryIntent, request: dict[str, Any] | None = None
    ) -> JournalResult:
        if operation not in {"lookup", "reserve", "conflict"} or (
            operation != "lookup" and request is None
        ):
            return JournalResult(
                status="refused", reason="supported exact journal operation required"
            )
        try:
            if operation == "lookup":
                return self._transaction(operation=operation, intent=intent, request=request)
            with repository_lock(
                directory=self.installation.state,
                repository=self.installation.repository,
                existing_only=True,
            ):
                return self._transaction(operation=operation, intent=intent, request=request)
        except (OSError, ValueError, IncidentJsonRefusalError, TypeError, KeyError, RecursionError):
            return JournalResult(status="unavailable", reason=_UNAVAILABLE)

    def _transaction(
        self, *, operation: str, intent: RecoveryIntent, request: dict[str, Any] | None
    ) -> JournalResult:
        directory = self._directory()
        retained = self._authenticate(intent=intent)
        if retained is None:
            return JournalResult(status="refused", reason="exact retained recovery action required")
        with self._lock(directory=directory, action_id=intent.action_id) as path:
            retained = self._authenticate(intent=intent)
            if retained is None:
                return JournalResult(status="refused", reason="retained recovery action changed")
            return self._perform_locked(
                path=path,
                operation=operation,
                intent=intent,
                retained=retained,
                request=request,
            )

    def _directory(self) -> Path:
        state = self.installation.state
        _private(path=state, directory=True)
        directory = state / "recovery-journal"
        _private(path=directory, directory=True)
        _contained(path=directory, parent=state)
        return directory

    def _authenticate(self, *, intent: RecoveryIntent) -> RetainedAction | None:
        if intent.registration.repository != self.installation.repository:
            return None
        name = hashlib.sha256(self.installation.repository.encode()).hexdigest() + ".json"
        path = self.installation.state / name
        _contained(path=path, parent=self.installation.state)
        return JournalCodec.retained(record=_record(path=path), intent=intent)

    @contextmanager
    def _lock(self, *, directory: Path, action_id: str) -> Iterator[Path]:
        flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
        descriptor = os.open(directory / (action_id + ".lock"), flags, 0o600)
        try:
            with os.fdopen(descriptor, "a+b", closefd=False) as lock:
                _private(path=directory / (action_id + ".lock"))
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
                try:
                    yield directory / (action_id + ".json")
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    def _perform_locked(
        self,
        *,
        path: Path,
        operation: str,
        intent: RecoveryIntent,
        retained: RetainedAction,
        request: dict[str, Any] | None,
    ) -> JournalResult:
        if path.exists() or path.is_symlink():
            _contained(path=path, parent=path.parent)
            entry = _record(path=path)
            return self._recover(
                entry=entry, operation=operation, intent=intent, retained=retained, request=request
            )
        if operation == "lookup":
            return JournalResult(
                status="absent" if retained.status == "pending" else "unavailable",
                reason="definitive journal absence for pending action"
                if retained.status == "pending"
                else "completed action has no independent effect history",
            )
        if retained.status != "pending":
            return JournalResult(
                status="refused", reason="completed action cannot acquire a new terminal result"
            )
        return self._persist(
            path=path, operation=operation, request=cast("dict[str, Any]", request)
        )

    def _recover(
        self,
        *,
        entry: dict[str, Any],
        operation: str,
        intent: RecoveryIntent,
        retained: RetainedAction,
        request: dict[str, Any] | None,
    ) -> JournalResult:
        result = JournalHistory.validate(entry=entry, intent=intent)
        if retained.status == "completed" and result.receipt != retained.receipt:
            return JournalResult(
                status="unavailable", reason="completed action has conflicting effect history"
            )
        if operation == "lookup" or (
            entry["operation"] == operation
            and JournalCodec.canonical(value=entry["request"])
            == JournalCodec.canonical(value=request)
        ):
            return result
        return JournalResult(
            status="refused", reason="action conflicts with immutable effect history"
        )

    def _persist(self, *, path: Path, operation: str, request: dict[str, Any]) -> JournalResult:
        context = self._context(request=request) if operation == "conflict" else None
        if operation == "conflict" and context is None:
            return JournalResult(
                status="refused", reason="independently authenticated conflict scope required"
            )
        entry = JournalHistory.entry(operation=operation, request=request, context=context)
        save_record(path=path, record=entry)
        return JournalHistory.result(operation=operation, request=request)

    def _context(self, *, request: dict[str, Any]) -> str | None:
        directory = self.installation.state / "recovery-journal-contexts"
        _private(path=directory, directory=True)
        _contained(path=directory, parent=self.installation.state)
        path = directory / (request["intent"]["action_id"] + ".json")
        if not path.exists() and not path.is_symlink():
            return None
        _contained(path=path, parent=directory)
        context = _record(path=path)
        if (
            set(context) != {"schema", "request"}
            or type(context["schema"]) is not int
            or context["schema"] != 1
        ):
            return None
        _ = JournalCodec.request(operation="conflict", raw=context["request"])
        return (
            JournalHistory.digest(value=context)
            if JournalCodec.canonical(value=context["request"])
            == JournalCodec.canonical(value=request)
            else None
        )
