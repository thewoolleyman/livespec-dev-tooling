"""Green-leg edges for the downloader seam's failure track.

A `*_edges.py` sibling rather than more cases in the mirror file: the
mirror is Red-recorded and byte-identity-bound across the Red→Green
pair, so every case discovered while making Green pass lands here.

These cover the branches NO existing test reaches — which is every
branch the conversion added, because the pre-conversion seam had no
failure track for a caller to handle.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from returns.io import IOFailure
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._invocation_failure import (
    BINARY_ABSENT,
    InvocationNotPerformed,
)
from livespec_dev_tooling.fleet._snapshot import (
    DownloadResult,
    SnapshotUnavailable,
    fetch_snapshot,
)

if TYPE_CHECKING:
    from pathlib import Path


def _never_invoked(*, args: list[str], dest: Path) -> DownloadResult:
    """A downloader whose `gh` never ran — the seam's own failure track."""
    _ = dest
    return IOFailure(
        InvocationNotPerformed(argv=("gh", *args), kind=BINARY_ABSENT, detail="gh CLI not on PATH")
    )


def test_a_download_that_never_ran_reaches_the_caller_as_a_named_unavailable() -> None:
    """The VALUE reaches the caller: the kind survives into `SnapshotUnavailable`.

    Without this the conversion would be decorative — the failure would
    be constructed at the seam and dropped one frame up, which is the
    fail-open this epic removes rather than a railway.
    """
    result = fetch_snapshot(download=_never_invoked, owner="acme", repo="widget", ref="master")
    assert isinstance(result, IOFailure)
    unavailable = unsafe_perform_io(result.failure())
    assert isinstance(unavailable, SnapshotUnavailable)
    assert unavailable.kind == BINARY_ABSENT
    assert unavailable.repo == "widget"
    assert unavailable.ref == "master"
    # `returncode` is 0 because there IS no exit code: the process never
    # ran. A fabricated non-zero here would rebuild the very sentinel the
    # conversion removed, one layer up.
    assert unavailable.returncode == 0
    assert "gh CLI not on PATH" in unavailable.detail


def test_the_reason_line_names_the_kind_and_the_program() -> None:
    failure = InvocationNotPerformed(
        argv=("gh", "api", "x"), kind=BINARY_ABSENT, detail="gh CLI not on PATH"
    )
    assert failure.reason == "binary_absent: gh (gh CLI not on PATH)"


def test_the_reason_line_survives_an_empty_argv() -> None:
    """Defensive: a reason that raises would lose the diagnostic it exists to carry."""
    failure = InvocationNotPerformed(argv=(), kind=BINARY_ABSENT, detail="no program")
    assert failure.reason == "binary_absent: <no argv> (no program)"
