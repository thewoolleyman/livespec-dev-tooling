"""The downloader seam's failure track — `livespec-dev-tooling-8o8e` row 36.

`default_gh_downloader` used to answer "the invocation never happened"
with a FABRICATED `DownloadOutcome(returncode=127)`, a success-shaped
record indistinguishable from a real `gh` that genuinely exited 127. It
also let `dest.open("wb")` and `subprocess.run` raise straight through
the seam. Both are now failure-track VALUES.

The success track is unchanged in meaning: a `gh` that RAN carries its
exit code as DATA, whatever that code is. These tests pin that
asymmetry, because collapsing it the other way — reading every non-zero
exit as a failure — is the tightening error this thread has committed
once already.
"""

from __future__ import annotations

import shutil
import subprocess
from typing import TYPE_CHECKING

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._invocation_failure import (
    BINARY_ABSENT,
    DESTINATION_UNWRITABLE,
    SPAWN_FAILED,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._snapshot import DownloadOutcome, default_gh_downloader

if TYPE_CHECKING:
    from pathlib import Path


def _absent_gh(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make `gh` unresolvable REGARDLESS of the host's real PATH.

    Patching `shutil.which` rather than prepending a shim directory: a
    shim only works if it is the WHOLE PATH, and a fixture that a real
    `gh` later on PATH can defeat is a fixture that cannot fail.
    """

    def fake_which(_name: str) -> str | None:
        return None

    monkeypatch.setattr(shutil, "which", fake_which)


def test_absent_gh_is_a_failure_value_not_a_fabricated_127(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A missing binary lands on the FAILURE track, carrying argv."""
    _absent_gh(monkeypatch)
    result = default_gh_downloader(args=["api", "x"], dest=tmp_path / "out.tar.gz")
    assert isinstance(result, IOFailure)
    failure = unsafe_perform_io(result.failure())
    assert isinstance(failure, InvocationNotPerformed)
    assert failure.kind == BINARY_ABSENT
    assert failure.argv == ("gh", "api", "x")


def test_a_gh_that_ran_and_exited_nonzero_is_a_success_carrying_its_code(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An invocation that COMPLETED and ANSWERED is a success whatever it answered."""

    def fake_which(_name: str) -> str | None:
        return "/usr/bin/gh"

    def fake_run(cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        return subprocess.CompletedProcess(args=cmd, returncode=4, stdout=b"", stderr=b"nope\n")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = default_gh_downloader(args=["api", "x"], dest=tmp_path / "out.tar.gz")
    assert isinstance(result, IOSuccess)
    assert unsafe_perform_io(result.unwrap()) == DownloadOutcome(returncode=4, stderr="nope\n")


def test_an_unspawnable_gh_is_a_failure_value_rather_than_a_raise(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """`subprocess.run` raising used to kill the whole nine-member sweep."""

    def fake_which(_name: str) -> str | None:
        return "/usr/bin/gh"

    def fake_run(_cmd: list[str], **_kwargs: object) -> subprocess.CompletedProcess[bytes]:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(shutil, "which", fake_which)
    monkeypatch.setattr(subprocess, "run", fake_run)
    result = default_gh_downloader(args=["api", "x"], dest=tmp_path / "out.tar.gz")
    assert isinstance(result, IOFailure)
    failure = unsafe_perform_io(result.failure())
    assert failure.kind == SPAWN_FAILED
    assert "Permission denied" in failure.detail


def test_an_unwritable_destination_is_a_failure_value(
    *, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The destination is this seam's own failure mode — its payload is a FILE.

    The unwritable destination is a directory that does not exist, which
    fails identically for every user. A `chmod 000` fixture would be a
    LIE when the suite runs as root: every open succeeds, the assertion
    never fires, and the test passes proving nothing.
    """

    def fake_which(_name: str) -> str | None:
        return "/usr/bin/gh"

    monkeypatch.setattr(shutil, "which", fake_which)
    result = default_gh_downloader(args=["api", "x"], dest=tmp_path / "absent-dir" / "out.tar.gz")
    assert isinstance(result, IOFailure)
    failure = unsafe_perform_io(result.failure())
    assert failure.kind == DESTINATION_UNWRITABLE
