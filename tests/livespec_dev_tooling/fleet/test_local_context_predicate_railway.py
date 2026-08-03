"""`LocalContext.dir_present` / `file_present` — the local PREDICATE seam.

The `file_text` seam moved local file READS off `Path.read_text()`. The same
absence remained for PREDICATES: `reconcile_beads_dir_perms` and
`reconcile_beads_metadata_present` still called `Path.is_dir()` / `Path.is_file()`
DIRECTLY, which livespec's ratified rendering-boundary condition 1 refuses, and
which RAISES.

**PROBED BEFORE BEING FIXED, on the 3.10 floor:** both predicates raise
`PermissionError` under an unreadable parent, because `pathlib`'s ignored-errno
set is `(ENOENT, ENOTDIR, EBADF, ELOOP)` and omits `EACCES`. Neither row had an
`except` anywhere, so it was UNCAUGHT — the same class as
`livespec-dev-tooling-a6et`, one unit later.

⛔ **AND THE REACHABILITY IS MANUFACTURED BY THIS FLEET ITSELF:**
`reconcile_beads_dir_perms` chmods `.beads` to `700`, so any process running as a
non-owner then takes the raise on `.beads/metadata.json`.

The split is the fleet's standing rule, unchanged: **a path that is ABSENT is an
ANSWER; one that CANNOT BE STATTED is a FAILURE.** Absence travels the success
track as `False`, so a row keeps reporting exactly as before; unstattability
travels the failure track, so a row reports can't-read instead of aborting the
whole reconcile partway through.

⚠️ **`chmod 000` PROVES NOTHING HERE — THIS SUITE RUNS AS ROOT**, the same
constraint `test_local_context_file_railway.py` records. Unstattability is spelled
as `ENAMETOOLONG`, which raises for root exactly as it does for anyone else. The
`ENOTDIR` case is asserted BESIDE it as a negative control: it must stay an
ANSWER, because a seam that turned every awkward path into a failure would make
every row skip and would look like a fix.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks._io_boundary_verbs import _UNRESOLVED_RECEIVER_IO_VERBS
from livespec_dev_tooling.fleet._local_context import (
    FILE_UNREADABLE,
    FileNotRead,
    LocalContext,
    PathKindOutcome,
)

__all__: list[str] = []


def _never_run(*, args: list[str], cwd: Path | None = None) -> object:
    """A command seam that must never be reached by a PREDICATE probe."""
    raise AssertionError(f"the predicate seam must not spawn a command: {args} (cwd={cwd})")


def _ctx(*, checkout: Path) -> LocalContext:
    return LocalContext(checkout=checkout, home=checkout, run=_never_run)  # pyright: ignore[reportArgumentType]


def _answer(*, outcome: PathKindOutcome) -> bool:
    """Unwrap a SUCCESS answer, failing loudly if the seam took the failure track.

    A bare `== IOSuccess(True)` would read the same but says nothing when the
    seam fails: the assertion reports two opaque containers. This names which
    half went wrong.
    """
    assert isinstance(outcome, IOSuccess), f"expected an answer, got a failure: {outcome!r}"
    return unsafe_perform_io(outcome.unwrap())


def test_a_present_directory_is_an_answer(*, tmp_path: Path) -> None:
    """The ordinary success path: it is there, and that is a value not a failure."""
    (tmp_path / "beads").mkdir()
    assert _answer(outcome=_ctx(checkout=tmp_path).dir_present(path=tmp_path / "beads"))


def test_an_absent_directory_is_an_answer_not_a_failure(*, tmp_path: Path) -> None:
    """ABSENT travels the SUCCESS track — the whole point of the split.

    A row asking "is there a `.beads`?" gets `False` and skips exactly as it did
    before the seam. If absence were a failure every clean checkout would report
    can't-read, which is the fix over-reaching rather than working.
    """
    assert not _answer(outcome=_ctx(checkout=tmp_path).dir_present(path=tmp_path / "absent"))


def test_a_path_under_a_non_directory_is_still_an_answer(*, tmp_path: Path) -> None:
    """THE NEGATIVE CONTROL, and it is what keeps the seam from over-catching.

    `ENOTDIR` is in `pathlib`'s ignored-errno set, so the primitive itself answers
    `False` rather than raising. The seam must not convert that into a failure:
    one that turned every awkward path into a skip would make every row skip and
    would still look like a fix.
    """
    _ = (tmp_path / "plain.txt").write_text("x", encoding="utf-8")
    ctx = _ctx(checkout=tmp_path)
    assert not _answer(outcome=ctx.dir_present(path=tmp_path / "plain.txt" / "child"))
    assert not _answer(outcome=ctx.file_present(path=tmp_path / "plain.txt" / "child"))


def test_an_unstattable_path_is_a_failure(*, tmp_path: Path) -> None:
    """UNSTATTABLE travels the FAILURE track, carrying the path and the kind.

    Spelled `ENAMETOOLONG` because this suite runs as ROOT and a permission
    denial would not raise here — the constraint the file-read seam's suite
    records. The production case is `EACCES`, which `pathlib` likewise does not
    ignore, so the same `except OSError` arm carries both.
    """
    unstattable = tmp_path / ("x" * 300)
    outcome = _ctx(checkout=tmp_path).dir_present(path=unstattable)

    assert isinstance(outcome, IOFailure)
    failure = unsafe_perform_io(outcome.failure())
    assert isinstance(failure, FileNotRead)
    assert failure.path == unstattable
    assert failure.kind == FILE_UNREADABLE


def test_file_present_makes_the_same_three_way_split(*, tmp_path: Path) -> None:
    """The file predicate mirrors the directory one — present, absent, unstattable."""
    _ = (tmp_path / "metadata.json").write_text("{}", encoding="utf-8")
    ctx = _ctx(checkout=tmp_path)

    assert _answer(outcome=ctx.file_present(path=tmp_path / "metadata.json"))
    assert not _answer(outcome=ctx.file_present(path=tmp_path / "absent.json"))
    assert isinstance(ctx.file_present(path=tmp_path / ("y" * 300)), IOFailure)


def test_a_directory_is_not_a_file_and_a_file_is_not_a_directory(*, tmp_path: Path) -> None:
    """The two seams answer DIFFERENT questions, asserted so one cannot alias the other."""
    (tmp_path / "dir").mkdir()
    _ = (tmp_path / "file").write_text("x", encoding="utf-8")
    ctx = _ctx(checkout=tmp_path)

    assert not _answer(outcome=ctx.dir_present(path=tmp_path / "file"))
    assert not _answer(outcome=ctx.file_present(path=tmp_path / "dir"))


def test_the_seam_names_are_outside_the_unresolved_receiver_verb_set() -> None:
    """⛔ THE MECHANICAL BOUND, PINNED — renaming these seams silently un-fixes the rows.

    A caller reaches a seam through `ctx`, a PARAMETER, so the receiver resolves
    to nothing and `_no_expected_failure_mode` has only the VERB left to judge.
    `is_dir`, `is_file` and `exists` are all IN `_UNRESOLVED_RECEIVER_IO_VERBS`,
    so a seam named after the primitive it wraps would leave every caller
    convicted exactly as before and **the fix would look done while changing
    nothing** — measured for `read_text` when the file seam was built.

    This test exists so that trap is caught by a red test rather than by
    re-measuring the offender list.
    """
    assert "dir_present" not in _UNRESOLVED_RECEIVER_IO_VERBS
    assert "file_present" not in _UNRESOLVED_RECEIVER_IO_VERBS
    assert {"is_dir", "is_file", "exists"} <= _UNRESOLVED_RECEIVER_IO_VERBS


def test_the_command_seam_guard_really_raises(*, tmp_path: Path) -> None:
    """The guard every test above relies on, exercised rather than assumed.

    Each test passes `_never_run` as the command seam, so a predicate that
    quietly shelled out would be caught. That guarantee is worth exactly as much
    as the guard actually raising — an assumption this asserts rather than
    inherits, the same way the file seam's suite does.
    """
    with pytest.raises(AssertionError, match="must not spawn a command"):
        _ = _never_run(args=["git", "status"], cwd=tmp_path)
