"""Tests for `livespec_dev_tooling/fleet/_snapshot.py` — the per-member tree read.

Hermetic: no `gh` process is spawned and no network is touched. The downloader
seam is a fake that copies a locally built `.tar.gz` to the requested
destination, so every archive shape under test — a stripped root component, a
directory-only archive, a `..` traversal entry, a non-gzip payload — is a REAL
archive read by the real `tarfile` rather than a mock of it.

`tempfile.tempdir` is redirected at `tmp_path` in the tests that care where the
snapshot lands, which is what lets them assert the DIRECTORY LIFECYCLE: a
failed read must leave nothing behind, and a successful one must leave exactly
the extracted tree.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from _gh_railway import lift_gh
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._context import FleetContext, GhResult
from livespec_dev_tooling.fleet._snapshot import (
    DownloadOutcome,
    SnapshotResult,
    SnapshotUnavailable,
    TreeSnapshot,
    default_gh_downloader,
    fetch_snapshot,
    memoized_snapshot,
)

if TYPE_CHECKING:
    import pytest

    from livespec_dev_tooling.fleet._snapshot import DownloadResult, GhDownloader

__all__: list[str] = []


_ROOT_PREFIX = "acme-widget-abc123"
_TARBALL_ARGS = ["api", "repos/acme/widget/tarball/master"]


def write_archive(*, path: Path, files: dict[str, str], directories: tuple[str, ...] = ()) -> None:
    """Build a real `.tar.gz` at `path` holding exactly these entry names."""
    with tarfile.open(path, mode="w:gz") as bundle:
        for name in directories:
            entry = tarfile.TarInfo(name=name)
            entry.type = tarfile.DIRTYPE
            bundle.addfile(entry)
        for name, text in files.items():
            payload = text.encode("utf-8")
            entry = tarfile.TarInfo(name=name)
            entry.size = len(payload)
            bundle.addfile(entry, io.BytesIO(payload))


def make_downloader(
    *,
    archive: Path | None = None,
    returncode: int = 0,
    stderr: str = "",
    calls: list[list[str]] | None = None,
) -> GhDownloader:
    """A `GhDownloader` that copies `archive` to the requested destination."""

    def download(*, args: list[str], dest: Path) -> DownloadResult:
        if calls is not None:
            calls.append(list(args))
        if archive is not None:
            _ = shutil.copyfile(archive, dest)
        # A canned downloader always RAN, whatever it returned, so every
        # response this fake gives is a success carrying its exit code.
        # Invocation-did-not-happen is a separate fake, below.
        return IOSuccess(DownloadOutcome(returncode=returncode, stderr=stderr))

    return download


def fetch(*, download: GhDownloader, ref: str = "master") -> SnapshotResult:
    """`fetch_snapshot` for owner `acme` / repo `widget`."""
    return fetch_snapshot(download=download, owner="acme", repo="widget", ref=ref)


def failure_of(*, result: SnapshotResult) -> SnapshotUnavailable:
    """The `SnapshotUnavailable` carried by a failed result."""
    assert isinstance(result, IOFailure)
    return unsafe_perform_io(result.failure())


def snapshot_of(*, result: SnapshotResult) -> TreeSnapshot:
    """The `TreeSnapshot` carried by a successful result."""
    assert isinstance(result, IOSuccess)
    return unsafe_perform_io(result.unwrap())


def make_recorder(*, recorded: list[dict[str, object]]):
    """A `ReadFailureRecorder` appending each preserved cause to `recorded`."""

    def record(*, operation: str, path: str, returncode: int, kind: str, detail: str) -> None:
        recorded.append(
            {
                "operation": operation,
                "path": path,
                "returncode": returncode,
                "kind": kind,
                "detail": detail,
            }
        )

    return record


def context_for(*, download: GhDownloader, default_branch: str) -> FleetContext:
    """A `FleetContext` whose repo-metadata read answers `default_branch`."""

    def run(*, args: list[str], stdin: str | None = None) -> GhResult:
        assert stdin is None
        assert args == ["api", "repos/acme/widget"]
        return GhResult(
            returncode=0, stdout=json.dumps({"default_branch": default_branch}), stderr=""
        )

    return FleetContext(owner="acme", run_gh=lift_gh(run), download_gh=download)


def test_default_downloader_without_gh_yields_a_failure_value(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """CORRECTED, not updated: this test used to PIN the fabricated sentinel.

    It asserted `outcome.returncode == 127` — the value the seam made up
    for "gh is not installed", which a real `gh` can also return. The
    suite was defending the collapse, so the honest conversion read as a
    regression against it. The failure track carries the distinction now;
    the exhaustive assertions live in the mirror file.
    """

    def fake_which(_name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", fake_which)
    result = default_gh_downloader(args=["api", "x"], dest=tmp_path / "out.tar.gz")
    assert isinstance(result, IOFailure)
    assert "gh CLI not on PATH" in unsafe_perform_io(result.failure()).detail


def test_default_downloader_streams_bytes_to_the_destination(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The payload is BINARY: `gh`'s stdout reaches a `wb` handle, never a `str`."""

    def fake_which(_name: str) -> str | None:
        return "/usr/bin/gh"

    monkeypatch.setattr(shutil, "which", fake_which)
    seen: dict[str, object] = {}

    def fake_run(cmd: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        seen["cmd"] = cmd
        sink = kwargs["stdout"]
        assert isinstance(sink, io.BufferedWriter)
        _ = sink.write(b"\x1f\x8bpayload")
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=b"", stderr=b"warned\n")

    monkeypatch.setattr(subprocess, "run", fake_run)
    dest = tmp_path / "out.tar.gz"
    outcome = default_gh_downloader(args=["api", "repos/acme/widget/tarball/master"], dest=dest)
    assert seen["cmd"] == ["gh", "api", "repos/acme/widget/tarball/master"]
    assert dest.read_bytes() == b"\x1f\x8bpayload"
    assert unsafe_perform_io(outcome.unwrap()) == DownloadOutcome(returncode=0, stderr="warned\n")


def test_snapshot_strips_the_single_archive_root_component(*, tmp_path: Path) -> None:
    archive = tmp_path / "fixture.tar.gz"
    write_archive(
        path=archive,
        files={
            f"{_ROOT_PREFIX}/pyproject.toml": "[project]\n",
            f"{_ROOT_PREFIX}/pkg/mod.py": "VALUE = 1\n",
        },
        directories=(f"{_ROOT_PREFIX}/", f"{_ROOT_PREFIX}/pkg/"),
    )
    snapshot = snapshot_of(result=fetch(download=make_downloader(archive=archive)))
    assert (snapshot.root / "pyproject.toml").read_text(encoding="utf-8") == "[project]\n"
    assert (snapshot.root / "pkg" / "mod.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert not (snapshot.root / _ROOT_PREFIX).exists()
    assert snapshot.file_count == 2
    assert snapshot.repo == "widget"
    assert snapshot.ref == "master"


def test_snapshot_requests_the_tarball_at_the_given_ref(*, tmp_path: Path) -> None:
    archive = tmp_path / "fixture.tar.gz"
    write_archive(path=archive, files={f"{_ROOT_PREFIX}/a.py": "A = 1\n"})
    calls: list[list[str]] = []
    _ = fetch(download=make_downloader(archive=archive, calls=calls), ref="trunk")
    assert calls == [["api", "repos/acme/widget/tarball/trunk"]]


def test_download_failure_names_the_classified_cause_and_leaves_nothing_behind(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    unavailable = failure_of(
        result=fetch(
            download=make_downloader(returncode=1, stderr="HTTP 403: Resource not accessible")
        )
    )
    assert unavailable.kind == "forbidden"
    assert unavailable.repo == "widget"
    assert unavailable.ref == "master"
    assert unavailable.returncode == 1
    assert "not accessible" in unavailable.detail
    assert list(tmp_path.iterdir()) == []


def test_a_payload_that_is_not_a_gzip_archive_is_a_named_failure(*, tmp_path: Path) -> None:
    not_an_archive = tmp_path / "fixture.tar.gz"
    _ = not_an_archive.write_text("404: Not Found\n", encoding="utf-8")
    unavailable = failure_of(result=fetch(download=make_downloader(archive=not_an_archive)))
    assert unavailable.kind == "malformed_archive"


def test_an_archive_with_no_regular_files_fails_rather_than_reporting_an_empty_tree(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The livespec-dev-tooling-vzwa lesson: an empty read is not an empty repo.

    A directory-only archive is what a broken read looks like — no ref of a
    governed repo archives to zero regular files. Answering `IOSuccess` with an
    empty tree would hand every consumer "this member has no files", and every
    consumer reads that as a PASS.
    """
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    archive = tmp_path / "fixture.tar.gz"
    write_archive(path=archive, files={}, directories=(f"{_ROOT_PREFIX}/",))
    unavailable = failure_of(result=fetch(download=make_downloader(archive=archive)))
    assert unavailable.kind == "empty_archive"
    assert list(tmp_path.iterdir()) == [archive]


def test_a_traversing_entry_is_refused_and_never_written_outside_the_snapshot(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    archive = tmp_path / "fixture.tar.gz"
    write_archive(
        path=archive,
        files={
            f"{_ROOT_PREFIX}/kept.py": "KEPT = 1\n",
            f"{_ROOT_PREFIX}/../escaped.py": "ESCAPED = 1\n",
        },
    )
    snapshot = snapshot_of(result=fetch(download=make_downloader(archive=archive)))
    assert snapshot.file_count == 1
    assert (snapshot.root / "kept.py").exists()
    assert not (snapshot.root.parent / "escaped.py").exists()
    assert not (snapshot.root.parent.parent / "escaped.py").exists()


def test_memoized_snapshot_reads_each_repo_exactly_once(*, tmp_path: Path) -> None:
    archive = tmp_path / "fixture.tar.gz"
    write_archive(path=archive, files={f"{_ROOT_PREFIX}/a.py": "A = 1\n"})
    calls: list[list[str]] = []
    cache: dict[str, SnapshotResult] = {}
    recorded: list[dict[str, object]] = []

    def once() -> SnapshotResult:
        return memoized_snapshot(
            cache=cache,
            download=make_downloader(archive=archive, calls=calls),
            owner="acme",
            repo="widget",
            ref="master",
            record=make_recorder(recorded=recorded),
        )

    first = once()
    second = once()
    assert calls == [_TARBALL_ARGS]
    assert first is second
    assert recorded == []


def test_memoized_snapshot_memoizes_the_failure_track_and_records_it_once(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A member whose archive is unreadable must not be re-read once per row."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    calls: list[list[str]] = []
    cache: dict[str, SnapshotResult] = {}
    recorded: list[dict[str, object]] = []

    def once() -> SnapshotResult:
        return memoized_snapshot(
            cache=cache,
            download=make_downloader(returncode=1, stderr="HTTP 429 rate limit", calls=calls),
            owner="acme",
            repo="widget",
            ref="master",
            record=make_recorder(recorded=recorded),
        )

    first = once()
    second = once()
    assert calls == [_TARBALL_ARGS]
    assert first is second
    assert len(recorded) == 1
    assert recorded[0]["operation"] == "tarball"
    assert recorded[0]["path"] == "widget@master"
    assert recorded[0]["kind"] == "rate_limited"


def test_member_tree_snapshot_pins_the_members_canonical_ref(*, tmp_path: Path) -> None:
    archive = tmp_path / "fixture.tar.gz"
    write_archive(path=archive, files={f"{_ROOT_PREFIX}/a.py": "A = 1\n"})
    calls: list[list[str]] = []
    ctx = context_for(download=make_downloader(archive=archive, calls=calls), default_branch="main")
    first = ctx.member_tree_snapshot(repo="widget")
    second = ctx.member_tree_snapshot(repo="widget")
    assert calls == [["api", "repos/acme/widget/tarball/main"]]
    assert first is second
    assert snapshot_of(result=first).ref == "main"


def test_member_tree_snapshot_preserves_the_cause_on_the_context_read_failures(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    ctx = context_for(
        download=make_downloader(returncode=1, stderr="HTTP 404: Not Found"),
        default_branch="master",
    )
    assert isinstance(ctx.member_tree_snapshot(repo="widget"), IOFailure)
    assert [failure.operation for failure in ctx.read_failures] == ["tarball"]
    assert ctx.read_failures[0].kind == "not_found"
    assert ctx.read_failures[0].path == "widget@master"
