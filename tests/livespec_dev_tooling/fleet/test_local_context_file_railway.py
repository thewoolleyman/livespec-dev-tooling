"""`LocalContext.file_text` — the local FILE-read seam, on the railway.

`LocalContext` carried `exec` / `exec_in_worktree` — a COMMAND seam — and
nothing for reading a FILE, while `FleetContext` has carried `file_text`
all along. So every local row that needed a file called
`Path.read_text()` / `is_file()` / `exists()` directly, which is exactly
what livespec's ratified rendering-boundary condition 1 refuses, and is
where two live crashes lived (livespec-dev-tooling-a6et).

The split this seam exists to make, and it is the fleet's standing rule:
**a file that is ABSENT is an ANSWER; one that CANNOT BE READ is a
FAILURE.** Absence travels the success track as `None`, so a row keeps
reporting "absent or drifted" exactly as before; unreadability travels
the failure track, so a row reports can't-read instead of aborting the
whole reconcile partway through.

⛔ BOTH EXCEPTION HIERARCHIES ARE ASSERTED, because the two live crashes
were in DIFFERENT ones and a fix spelled `except OSError` catches one and
misses the other: `IsADirectoryError` is an `OSError`, while
`UnicodeDecodeError` is a `ValueError`. `test_undecodable_bytes_are_a_failure`
is the one that a naive `except OSError` would leave red.

⚠️ `chmod 000` proves nothing here — this suite runs as ROOT. Unreadability
is spelled as a DIRECTORY where a file is expected (`IsADirectoryError`),
and undecodability as bytes that are not valid UTF-8.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.fleet._local_context import (
    FILE_UNDECODABLE,
    FILE_UNREADABLE,
    FileNotRead,
    LocalContext,
)

if TYPE_CHECKING:
    import pytest

__all__: list[str] = []


def _never_run(*, args: list[str], cwd: Path | None = None) -> object:
    """A command seam that must never be reached by a FILE read."""
    raise AssertionError(f"the file seam must not spawn a command: {args} (cwd={cwd})")


def _ctx(*, checkout: Path) -> LocalContext:
    return LocalContext(checkout=checkout, home=checkout, run=_never_run)  # pyright: ignore[reportArgumentType]


def test_present_file_reads_as_success(tmp_path: pytest.TempPathFactory | Path) -> None:
    """A readable file answers with its text on the success track."""
    root = Path(str(tmp_path))
    target = root / "present.txt"
    _ = target.write_text("hello", encoding="utf-8")

    outcome = _ctx(checkout=root).file_text(path=target)

    assert isinstance(outcome, IOSuccess)
    assert unsafe_perform_io(outcome.unwrap()) == "hello"


def test_absent_file_is_an_answer_not_a_failure(tmp_path: pytest.TempPathFactory | Path) -> None:
    """ABSENCE IS AN ANSWER — `None` on the SUCCESS track, never a failure.

    This is the half that keeps the consuming rows' behaviour intact: a
    row compares the answer against its canonical body, and an absent
    file must still read as "absent or drifted" rather than as
    "unreadable". Routing absence to the failure track would make
    can't-read the ordinary case and the diagnostics strictly worse.
    """
    root = Path(str(tmp_path))

    outcome = _ctx(checkout=root).file_text(path=root / "nope.txt")

    assert isinstance(outcome, IOSuccess)
    assert unsafe_perform_io(outcome.unwrap()) is None


def test_directory_where_a_file_is_expected_is_a_failure(
    tmp_path: pytest.TempPathFactory | Path,
) -> None:
    """`IsADirectoryError` — an `OSError` — travels the FAILURE track.

    The live shape from `reconcile_livespec_jsonc_complete`, whose
    `exists()` pre-check returns True for a directory and let the
    `read_text()` through to raise uncaught.
    """
    root = Path(str(tmp_path))
    target = root / "adir"
    target.mkdir()

    outcome = _ctx(checkout=root).file_text(path=target)

    assert isinstance(outcome, IOFailure)
    failure = unsafe_perform_io(outcome.failure())
    assert isinstance(failure, FileNotRead)
    assert failure.kind == FILE_UNREADABLE
    assert failure.path == target


def test_undecodable_bytes_are_a_failure(tmp_path: pytest.TempPathFactory | Path) -> None:
    """`UnicodeDecodeError` — a `ValueError`, NOT an `OSError` — also fails.

    ⛔ THIS IS THE ONE A NAIVE `except OSError` LEAVES RED. It is the live
    shape from `assert_worktree_pack`, whose `is_file()` pre-check IS a
    real shield against a directory, so the reachable crash was a regular
    file whose BYTES are not valid UTF-8.
    """
    root = Path(str(tmp_path))
    target = root / "binary.sh"
    _ = target.write_bytes(b"\xff\xfe\x00\x80binary")

    outcome = _ctx(checkout=root).file_text(path=target)

    assert isinstance(outcome, IOFailure)
    failure = unsafe_perform_io(outcome.failure())
    assert isinstance(failure, FileNotRead)
    assert failure.kind == FILE_UNDECODABLE
    assert failure.path == target


def test_the_two_failure_kinds_stay_apart(tmp_path: pytest.TempPathFactory | Path) -> None:
    """The vocabulary is closed and the two kinds are DISTINCT.

    They call for different operator responses — undecodable is corrupt
    CONTENT, unreadable is a PATH or permissions problem — so fusing them
    into one kind would put two meanings in one variant, which is exactly
    what the rendering-boundary clause's condition 3 refuses.
    """
    root = Path(str(tmp_path))
    adir = root / "d"
    adir.mkdir()
    binary = root / "b"
    _ = binary.write_bytes(b"\xff")
    ctx = _ctx(checkout=root)

    kinds = {
        unsafe_perform_io(ctx.file_text(path=p).failure()).kind  # pyright: ignore[reportAttributeAccessIssue]
        for p in (adir, binary)
    }

    assert kinds == {FILE_UNREADABLE, FILE_UNDECODABLE}
