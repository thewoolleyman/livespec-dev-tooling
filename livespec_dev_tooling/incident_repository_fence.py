"""Context-bound repository flocks transferable through an inherited descriptor."""

from __future__ import annotations

import fcntl
import hashlib
import os
import stat
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

__all__: list[str] = [
    "REPOSITORY_FENCE_FD_ENV",
    "RepositoryFence",
    "borrow_repository_fence",
    "current_repository_fence",
    "hold_repository_fence",
]

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-dln3ac
REPOSITORY_FENCE_FD_ENV = "LIVESPEC_INCIDENT_REPOSITORY_FENCE_FD"
_FENCE_REFUSAL = "protected live repository fence required"
_MIN_FENCE_DESCRIPTOR = 3


@dataclass(kw_only=True)
class RepositoryFence:
    """One live OS lock, scoped to its owning process, thread and context."""

    descriptor: int
    repository: str
    directory: Path
    owner_pid: int
    owner_thread: int
    active: bool = True


_FENCES: ContextVar[tuple[RepositoryFence, ...]] = ContextVar("repository_fences", default=())


def _protected_directory(*, directory: Path) -> None:
    try:
        resolved = directory.resolve(strict=True)
    except RuntimeError as error:
        raise OSError(_FENCE_REFUSAL) from error
    for entry in (directory, *directory.parents, resolved, *resolved.parents):
        link, target = entry.lstat(), entry.stat()
        sticky = entry.is_dir() and target.st_uid == 0 and bool(target.st_mode & stat.S_ISVTX)
        if (
            link.st_uid not in {0, os.geteuid()}
            or target.st_uid not in {0, os.geteuid()}
            or (target.st_mode & 0o022 and not sticky)
        ):
            raise OSError(_FENCE_REFUSAL)
    if not directory.is_absolute() or not directory.is_dir() or directory.stat().st_mode & 0o077:
        raise OSError(_FENCE_REFUSAL)


def _lock_path(*, directory: Path, repository: str) -> Path:
    return directory / (hashlib.sha256(repository.encode()).hexdigest() + ".lock")


def _validate_descriptor(*, descriptor: int, directory: Path, repository: str) -> None:
    if type(descriptor) is not int or descriptor < _MIN_FENCE_DESCRIPTOR or not repository:
        raise OSError(_FENCE_REFUSAL)
    _protected_directory(directory=directory)
    path = _lock_path(directory=directory, repository=repository)
    link, actual = path.lstat(), os.fstat(descriptor)
    if (
        not stat.S_ISREG(link.st_mode)
        or not stat.S_ISREG(actual.st_mode)
        or (link.st_dev, link.st_ino) != (actual.st_dev, actual.st_ino)
        or actual.st_uid not in {0, os.geteuid()}
        or stat.S_IMODE(actual.st_mode) & 0o077
    ):
        raise OSError(_FENCE_REFUSAL)


def current_repository_fence(
    *, repository: str, directory: Path | None = None
) -> RepositoryFence | None:
    """Return only the current context's still-open, exact repository lock."""
    try:
        expected = None if directory is None else directory.resolve()
    except (OSError, RuntimeError):
        return None
    matches: list[RepositoryFence] = []
    for fence in reversed(_FENCES.get()):
        if (
            not fence.active
            or fence.repository != repository
            or fence.owner_pid != os.getpid()
            or fence.owner_thread != threading.get_ident()
            or (expected is not None and fence.directory != expected)
        ):
            continue
        try:
            _validate_descriptor(
                descriptor=fence.descriptor, directory=fence.directory, repository=repository
            )
            # A private original FD still owns this flock. A closed public FD
            # reused for a new open of the same inode cannot borrow that OFD.
            fcntl.flock(fence.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, RuntimeError):
            continue
        matches.append(fence)
    if len({fence.directory for fence in matches}) != 1:
        return None
    return matches[0]


@contextmanager
def _registered_fence(
    *, descriptor: int, directory: Path, repository: str
) -> Iterator[RepositoryFence]:
    resolved = directory.resolve()
    fence = RepositoryFence(
        descriptor=os.dup(descriptor),
        repository=repository,
        directory=resolved,
        owner_pid=os.getpid(),
        owner_thread=threading.get_ident(),
    )
    token = _FENCES.set((*_FENCES.get(), fence))
    try:
        yield fence
    finally:
        fence.active = False
        _FENCES.reset(token)
        try:
            _validate_descriptor(
                descriptor=fence.descriptor, directory=fence.directory, repository=repository
            )
            fcntl.flock(fence.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, RuntimeError):
            # The consumer closed/reused its public descriptor. Do not close
            # a replacement FD; the private owning descriptor is still ours.
            pass
        else:
            os.close(fence.descriptor)


@contextmanager
def borrow_repository_fence(
    *, descriptor: int, directory: Path, repository: str
) -> Iterator[RepositoryFence]:
    """Retain an inherited OFD; closing our duplicate never unlocks its owner."""
    _validate_descriptor(descriptor=descriptor, directory=directory, repository=repository)
    duplicate = os.dup(descriptor)
    try:
        _validate_descriptor(descriptor=duplicate, directory=directory, repository=repository)
        # The caller's same OFD succeeds immediately; another open of a held
        # lock refuses instead of deadlocking the caller that is waiting on us.
        fcntl.flock(duplicate, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with _registered_fence(
            descriptor=duplicate, directory=directory, repository=repository
        ) as fence:
            yield fence
    finally:
        # LOCK_UN here would release the parent's shared flock as well.
        os.close(duplicate)


@contextmanager
def hold_repository_fence(
    *, directory: Path, repository: str, existing_only: bool = False
) -> Iterator[RepositoryFence]:
    """Serialize ALL controller and ordinary-reconciler mutations per repo.

    Production must provision this directory on the independent controller,
    inaccessible to candidate trees. A filesystem error propagates as refusal;
    there is no unlocked, tenant-backed, or wrapper-backed fallback.
    """
    if existing_only:
        _protected_directory(directory=directory)
    else:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    current = current_repository_fence(repository=repository, directory=directory)
    if current is not None:
        yield current
        return
    if any(
        fence.active and fence.repository == repository and fence.directory == directory.resolve()
        for fence in _FENCES.get()
    ):
        # Invalid matching context can still hold a private owning OFD;
        # reopening its inode would self-deadlock instead of repairing it.
        raise OSError(_FENCE_REFUSAL)
    descriptor = os.open(
        _lock_path(directory=directory, repository=repository),
        os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW,
        0o600,
    )
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_uid not in {0, os.geteuid()}:
            raise OSError(_FENCE_REFUSAL)
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        try:
            # Older stores created 0644 empty locks. Converge only the owned
            # inode while holding it; never replace or truncate a live lock.
            os.fchmod(descriptor, 0o600)
            with _registered_fence(
                descriptor=descriptor, directory=directory, repository=repository
            ) as fence:
                yield fence
        finally:
            fcntl.flock(descriptor, fcntl.LOCK_UN)
    finally:
        os.close(descriptor)
