"""_snapshot — one archive read per member instead of one API call per file.

A central-vantage row that must find an IMPORT cannot know which files to read
without reading them, and `FleetContext.file_text` is ONE
`gh api .../contents/<path>` call per file. Measured over the fleet's ~635
first-party `.py` (`livespec-dev-tooling-k76y`): the per-file route costs ~653
reads per run against a 5000/hr App installation pool SHARED by all nine repos'
automation, or ~5877 across a nine-PR release fan-out — 1.2x the entire hourly
budget. `repos/{owner}/{repo}/tarball/{ref}` answers with the whole tree in ONE
request: 9 reads per run, 81 across a fan-out.

The module is imported BY `_context` and imports nothing from it — the same
arrangement `_read_failure` and `_tree_state` have. That is why the downloader
seam reports a `DownloadOutcome` of its own rather than a `GhResult`: taking
`GhResult` would invert the dependency, for a value whose `stdout` field this
path never populates anyway.

AN EMPTY ARCHIVE GOES ON THE FAILURE TRACK, AND THAT IS THE DESIGN DECISION
MOST WORTH KEEPING. `livespec-dev-tooling-vzwa` paid for the sibling of it:
`pkgutil.iter_modules` on a MISSING directory yields no entries rather than
raising, so the surface returned an empty tuple and every consumer read it as
"this repo has nothing" — a PASS. Typing this read `IOResult` while still
answering `IOSuccess` for an archive holding no files would MOVE that sentinel
rather than remove it. No ref of a governed repo archives to zero regular
files, so zero means the read broke.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tarfile
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    BINARY_ABSENT,
    DESTINATION_UNWRITABLE,
    SPAWN_FAILED,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._read_failure import (  # noqa: E402
    classify_gh_failure,
    sanitize_detail,
)

__all__: list[str] = [
    "DownloadOutcome",
    "DownloadResult",
    "GhDownloader",
    "ReadFailureRecorder",
    "SnapshotResult",
    "SnapshotUnavailable",
    "TreeSnapshot",
    "default_gh_downloader",
    "fetch_snapshot",
    "memoized_snapshot",
]


_SNAPSHOT_PREFIX = "livespec-fleet-snapshot-"
_ARCHIVE_NAME = "member.tar.gz"
_TREE_DIRNAME = "tree"
# GitHub wraps every tarball in exactly ONE root component
# (`<owner>-<repo>-<sha>/`), so an entry carrying only that component is the
# root directory itself and names no path inside the repo.
_ROOT_COMPONENTS = 1


@dataclass(frozen=True, kw_only=True)
class DownloadOutcome:
    """Exit status of one binary `gh` read whose payload landed in a file.

    Deliberately NOT `GhResult`: there is no `stdout` to carry, because the
    bytes went to `dest`. A field that could only ever be empty would invite a
    caller to read it as "the payload was empty".
    """

    returncode: int
    stderr: str


DownloadResult = IOResult[DownloadOutcome, InvocationNotPerformed]


class GhDownloader(Protocol):
    """Callable seam for a `gh` read whose stdout is BINARY and lands at `dest`.

    The failure track carries ONLY "the invocation did not happen". A
    `gh` that RAN is a success carrying its exit code as data, however
    that code reads — the seam does not adjudicate what GitHub said.
    """

    def __call__(self, *, args: list[str], dest: Path) -> DownloadResult: ...


class ReadFailureRecorder(Protocol):
    """`FleetContext.record_read_failure`'s shape, taken as a parameter.

    Passed in rather than imported for the reason at the top of this module:
    the diagnostics sink lives on the context, and this module must stay
    importable BY the context.
    """

    def __call__(
        self, *, operation: str, path: str, returncode: int, kind: str, detail: str
    ) -> None: ...


@dataclass(frozen=True, kw_only=True)
class SnapshotUnavailable:
    """A member's tree could not be read as one archive.

    `kind` reuses `classify_gh_failure`'s vocabulary for a transport/HTTP
    failure, and adds `malformed_archive` and `empty_archive` for the two ways
    a 200 response can still fail to be a tree. The three stay apart because a
    rate-limited read is retryable, a malformed payload is a bug or an outage,
    and an empty archive means the read is lying about a repo that has files.
    """

    repo: str
    ref: str
    returncode: int
    kind: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class TreeSnapshot:
    """One member's whole tree at a pinned ref, extracted on local disk.

    `root` IS the repo root — the single component GitHub wraps every tarball
    in is stripped — so every repo-root-relative reader in this library
    (`load_config`, `filter_first_party_py`, `pin_autodiscovery.discover`)
    works against a member unchanged.

    `handle` is the snapshot's LIFETIME rather than part of its value: the
    extracted directory lives exactly as long as the value that names it, and
    `TemporaryDirectory`'s own finalizer removes it when this value is
    collected or the process exits. Holding the stdlib object is what makes
    that true without an `atexit` hook of our own. It is excluded from
    comparison and repr for the same reason — two snapshots of one repo at one
    ref describe the same tree whichever directory each was extracted into.
    """

    repo: str
    ref: str
    root: Path
    file_count: int
    handle: tempfile.TemporaryDirectory[str] = field(compare=False, repr=False)


SnapshotResult = IOResult[TreeSnapshot, SnapshotUnavailable]


def default_gh_downloader(*, args: list[str], dest: Path) -> DownloadResult:
    """Run `gh <args>` streaming stdout BYTES to `dest`; a missing `gh` FAILS.

    Separate from `default_gh_runner` because the payload is BINARY. Capturing
    a gzip stream as text decodes it through a locale codec and hands back a
    corrupted archive that fails later, at extraction, with a diagnostic
    naming the wrong thing.

    This used to answer an absent `gh` with `DownloadOutcome(returncode=127)`
    — a fabricated code a real `gh` can also return, so "never ran" and "ran
    and exited 127" were the same value. It is a failure-track value now, and
    a completed invocation is a success whatever its exit code.
    """
    argv = ("gh", *args)
    if shutil.which("gh") is None:
        return IOFailure(
            InvocationNotPerformed(argv=argv, kind=BINARY_ABSENT, detail="gh CLI not on PATH")
        )
    # Opened in its OWN try, and before the spawn, because `dest.open` and
    # `subprocess.run` both raise `OSError` — folding them into one arm would
    # spell "the disk is unwritable" and "gh could not start" the same way,
    # which is the collapse this conversion exists to remove.
    try:
        sink = dest.open("wb")
    except OSError as unwritable:
        return IOFailure(
            InvocationNotPerformed(argv=argv, kind=DESTINATION_UNWRITABLE, detail=str(unwritable))
        )
    try:
        with sink:
            completed = subprocess.run(list(argv), stdout=sink, stderr=subprocess.PIPE, check=False)
    except OSError as unspawnable:
        return IOFailure(
            InvocationNotPerformed(argv=argv, kind=SPAWN_FAILED, detail=str(unspawnable))
        )
    return IOSuccess(
        DownloadOutcome(
            returncode=completed.returncode,
            stderr=completed.stderr.decode("utf-8", errors="replace"),
        )
    )


def _stripped_path(*, name: str) -> Path | None:
    """The entry path minus the archive's root component, or None to refuse it.

    None means "do not write this entry": either nothing remains after the
    strip (the root directory itself), or the path traverses upward. Refusing
    rather than sanitizing is the point — a rewritten path would still land
    somewhere, and a snapshot quietly holding a file the member does not have
    is worse than one missing a file it does.
    """
    parts = Path(name).parts
    inside = parts[_ROOT_COMPONENTS:]
    if not inside or ".." in inside:
        return None
    return Path(*inside)


def _extract_regular_files(*, archive: Path, destination: Path) -> int:
    """Write the archive's regular files under `destination`; return how many.

    ONLY regular files are written. A symlink, hardlink, device or directory
    entry is skipped rather than reproduced — the snapshot exists to be READ
    as text, and a link is the vector by which an archive reaches outside its
    destination. `tarfile.extractall(filter="data")` is the stdlib spelling of
    the same guard, deliberately not used: it arrived in a 3.10 PATCH release
    and this repo's floor is 3.10 as a MINOR (`SPECIFICATION/constraints.md`
    §"Runtime"), so depending on it would narrow the floor silently.
    """
    extracted = 0
    with tarfile.open(archive, mode="r:gz") as bundle:
        for entry in bundle:
            payload = bundle.extractfile(entry) if entry.isfile() else None
            relative = _stripped_path(name=entry.name)
            if payload is None or relative is None:
                continue
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb") as sink:
                shutil.copyfileobj(payload, sink)
            extracted += 1
    return extracted


def _unavailable(
    *,
    handle: tempfile.TemporaryDirectory[str],
    repo: str,
    ref: str,
    returncode: int,
    kind: str,
    detail: str,
) -> SnapshotResult:
    """Discard the half-built snapshot directory and name the failure."""
    handle.cleanup()
    return IOFailure(
        SnapshotUnavailable(
            repo=repo,
            ref=ref,
            returncode=returncode,
            kind=kind,
            detail=sanitize_detail(text=detail),
        )
    )


def fetch_snapshot(*, download: GhDownloader, owner: str, repo: str, ref: str) -> SnapshotResult:
    """Read `repo`'s whole tree at `ref` in ONE API call, extracted on local disk.

    `IOResult` rather than `Result`: this downloads over the network and writes
    to the filesystem with no seam between it and either, which is what
    livespec v179 member 1 clause (c) sees and is the honest type.

    The archive is deleted once extracted. Keeping it would double the
    snapshot's disk cost for a payload nothing reads twice.
    """
    handle = tempfile.TemporaryDirectory(prefix=_SNAPSHOT_PREFIX)
    workspace = Path(handle.name)
    archive = workspace / _ARCHIVE_NAME
    root = workspace / _TREE_DIRNAME
    root.mkdir()
    downloaded = download(args=["api", f"repos/{owner}/{repo}/tarball/{ref}"], dest=archive)
    if isinstance(downloaded, IOFailure):
        # The invocation never happened, so there is no exit code to report.
        # `returncode=0` beside a `kind` that names the cause is the existing
        # spelling for the two non-transport failures below, and reusing it
        # keeps "gh said no" (a real code) apart from "gh never ran".
        not_performed = unsafe_perform_io(downloaded.failure())
        return _unavailable(
            handle=handle,
            repo=repo,
            ref=ref,
            returncode=0,
            kind=not_performed.kind,
            detail=not_performed.reason,
        )
    outcome = unsafe_perform_io(downloaded.unwrap())
    if outcome.returncode != 0:
        return _unavailable(
            handle=handle,
            repo=repo,
            ref=ref,
            returncode=outcome.returncode,
            kind=classify_gh_failure(stderr=outcome.stderr),
            detail=outcome.stderr,
        )
    try:
        extracted = _extract_regular_files(archive=archive, destination=root)
    except (OSError, tarfile.TarError) as unreadable:
        # NARROW, and both arms are inhabited: `TarError` is a payload that is
        # not a gzip archive (a 200 carrying an HTML error page reaches here),
        # `OSError` is the local write failing partway. Catching neither would
        # propagate a raise through the whole nine-member sweep and kill it
        # partway through one member — the shape `livespec-dev-tooling-9sl0`
        # removed from `pin_autodiscovery.discover`.
        return _unavailable(
            handle=handle,
            repo=repo,
            ref=ref,
            returncode=0,
            kind="malformed_archive",
            detail=str(unreadable),
        )
    if extracted == 0:
        return _unavailable(
            handle=handle,
            repo=repo,
            ref=ref,
            returncode=0,
            kind="empty_archive",
            detail=f"the archive of {repo}@{ref} holds no regular files",
        )
    archive.unlink()
    return IOSuccess(
        TreeSnapshot(repo=repo, ref=ref, root=root, file_count=extracted, handle=handle)
    )


def memoized_snapshot(
    *,
    cache: dict[str, SnapshotResult],
    download: GhDownloader,
    owner: str,
    repo: str,
    ref: str,
    record: ReadFailureRecorder,
) -> SnapshotResult:
    """`fetch_snapshot` for `repo`, computed at most once per run — BOTH tracks.

    Memoizing the FAILURE matters as much as memoizing the success. The row
    this exists for is called once per MEMBER and needs every member's tree, so
    an un-memoized failure turns a 9-call primitive into a 9-calls-per-row one
    against the very pool this design protects.

    The cause is preserved on the same sink every other read uses, so an
    unreadable member reaches its row as a named skip rather than a false pass.
    """
    cached = cache.get(repo)
    if cached is not None:
        return cached
    result = fetch_snapshot(download=download, owner=owner, repo=repo, ref=ref)
    if isinstance(result, IOFailure):
        unavailable = unsafe_perform_io(result.failure())
        record(
            operation="tarball",
            path=f"{repo}@{ref}",
            returncode=unavailable.returncode,
            kind=unavailable.kind,
            detail=unavailable.detail,
        )
    cache[repo] = result
    return result
