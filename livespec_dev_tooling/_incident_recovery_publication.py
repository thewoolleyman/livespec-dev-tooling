"""The recovery principal's durable per-action publication record.

One action may need several publication ATTEMPTS: a definite `head-moved`
proves the earlier attempt had no effect, and the same immutable action is then
recomputed against the new master head. The record keeps every attempt, in
order, and at most one is open. An attempt is `reserved` before any forge call,
`prepared` once its revert commit exists (a commit object only; master has not
moved), and terminal as `head-moved` or `abandoned` when it provably had no
effect. The action's merge receipt, once recorded, is final.

The ordering is the whole point. The ref update that moves master is sent ONLY
for a `prepared` attempt whose commit is already durable here, so after any
timeout or restart the one commit that could have landed is known by its SHA,
and a repeated publication re-sends that same commit instead of minting a second
revert. Records use the observer store's atomic replace with file and directory
fsync, and a per-action lock serializes every reader that may write.
"""

from __future__ import annotations

import fcntl
import os
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, cast

from livespec_dev_tooling._incident_observer_store import save_record
from livespec_dev_tooling._incident_recovery_journal_values import JournalValues
from livespec_dev_tooling.incident_protected_path import protected_path

__all__: list[str] = [
    "Publication",
    "PublicationAttempt",
    "PublicationLedger",
    "PublicationReceipt",
]

_OPEN = frozenset({"reserved", "prepared"})
_STATES = _OPEN | {"head-moved", "abandoned"}
_MAX_RECORD = 1024 * 1024


@dataclass(frozen=True, kw_only=True)
class PublicationAttempt:
    """One exact publish request against one expected master head."""

    request_sha256: str
    expected_head: str
    tree_sha: str
    status: str
    commit: str | None = None


@dataclass(frozen=True, kw_only=True)
class PublicationReceipt:
    """The exact merged revert: its commit on master and its verified tree."""

    receipt: str
    merge_sha: str
    tree_sha: str


@dataclass(frozen=True, kw_only=True)
class Publication:
    """Every attempt of one action, and its final receipt once recorded."""

    action_id: str
    attempts: tuple[PublicationAttempt, ...] = ()
    receipt: PublicationReceipt | None = None

    @property
    def open_attempt(self) -> PublicationAttempt | None:
        last = self.attempts[-1] if self.attempts else None
        return last if last is not None and last.status in _OPEN else None

    def with_attempt(self, *, attempt: PublicationAttempt) -> Publication:
        """Replace the open attempt, or append a new one when none is open."""
        kept = self.attempts[:-1] if self.open_attempt is not None else self.attempts
        return replace(self, attempts=(*kept, attempt))

    def committed(self, *, merge_sha: str, tree_sha: str) -> Publication:
        prepared = cast("PublicationAttempt", self.open_attempt)
        return replace(
            self.with_attempt(attempt=replace(prepared, status="prepared", commit=merge_sha)),
            receipt=PublicationReceipt(
                receipt=_receipt_text(action_id=self.action_id, merge_sha=merge_sha),
                merge_sha=merge_sha,
                tree_sha=tree_sha,
            ),
        )


def _receipt_text(*, action_id: str, merge_sha: str) -> str:
    return f"recovery-inverse:{action_id}:commit:{merge_sha}"


def _attempt(*, raw: Any) -> PublicationAttempt:
    data = JournalValues.object(value=raw)
    commit = data.get("commit")
    if not (
        set(data) == {"request_sha256", "expected_head", "tree_sha", "status", "commit"}
        and JournalValues.digest(value=data["request_sha256"])
        and JournalValues.sha(value=data["expected_head"])
        and JournalValues.sha(value=data["tree_sha"])
        and data["status"] in _STATES
        and (commit is None or JournalValues.sha(value=commit))
        and (commit is not None or data["status"] != "prepared")
    ):
        message = "invalid recovery publication attempt"
        raise ValueError(message)
    return PublicationAttempt(**data)


def _decode(*, raw: Any, action_id: str) -> Publication:
    data = JournalValues.object(value=raw)
    receipt = JournalValues.object(value=data.get("receipt"))
    attempts = data.get("attempts")
    if not (
        set(data) == {"schema", "action_id", "attempts", "receipt"}
        and type(data["schema"]) is int
        and data["schema"] == 1
        and data["action_id"] == action_id
        and isinstance(attempts, list)
        and (data["receipt"] is None or set(receipt) == {"receipt", "merge_sha", "tree_sha"})
    ):
        message = "invalid recovery publication record"
        raise ValueError(message)
    decoded = Publication(
        action_id=action_id,
        attempts=tuple(_attempt(raw=item) for item in cast("list[Any]", attempts)),
        receipt=PublicationReceipt(**receipt) if receipt else None,
    )
    final, last = decoded.receipt, decoded.open_attempt
    if final is not None and (
        last is None
        or (last.status, last.commit, last.tree_sha)
        != ("prepared", final.merge_sha, final.tree_sha)
        or final.receipt != _receipt_text(action_id=action_id, merge_sha=final.merge_sha)
    ):
        message = "recovery publication receipt does not match its action"
        raise ValueError(message)
    return decoded


def _private(*, path: Path, directory: bool) -> None:
    info = path.lstat()
    kind = stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)
    if (
        not kind
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) & 0o077
        or not protected_path(path=path)
    ):
        message = f"unprotected recovery publication path: {path}"
        raise OSError(message)


@dataclass(frozen=True, kw_only=True)
class PublicationLedger:
    """Per-action records beside the protected journal, under a per-action lock."""

    directory: Path

    @contextmanager
    def hold(self, *, action_id: str) -> Iterator[None]:
        _private(path=self.directory, directory=True)
        lock = self.directory / f"{action_id}.publication.lock"
        flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
        descriptor = os.open(lock, flags, 0o600)
        try:
            _private(path=lock, directory=False)
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            os.close(descriptor)

    def load(self, *, action_id: str) -> Publication:
        """The action's record; an absent file is no attempt, a damaged one raises."""
        path = self.directory / f"{action_id}.publication.json"
        if not path.exists() and not path.is_symlink():
            return Publication(action_id=action_id)
        _private(path=path, directory=False)
        raw = path.read_bytes()
        return _decode(raw=JournalValues.decode(raw=raw, limit=_MAX_RECORD), action_id=action_id)

    def save(self, *, publication: Publication) -> None:
        record: dict[str, object] = {
            "schema": 1,
            "action_id": publication.action_id,
            "attempts": [asdict(attempt) for attempt in publication.attempts],
            "receipt": None if publication.receipt is None else asdict(publication.receipt),
        }
        save_record(
            path=self.directory / f"{publication.action_id}.publication.json", record=record
        )
