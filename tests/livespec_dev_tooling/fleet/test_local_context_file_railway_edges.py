"""Green-leg edges of the local FILE-read seam that the Red file cannot reach.

The Red file (`test_local_context_file_railway.py`) is CHECKSUM-BOUND across
the Red→Green pair, so every branch the conversion ADDS to a consuming row
needs its coverage here instead: the three `RowSkip` arms that turn a
can't-read into a skip rather than an uncaught crash.

⛔ EACH ARM IS ASSERTED AGAINST A NEGATIVE CONTROL IN THE SAME TEST — the
same row, same fixture, readable input — because a skip that fires
unconditionally would satisfy a bare "returns RowSkip" assertion while
having broken the row. The control is what makes the skip credible.

⚠️ Unreadability is spelled as a DIRECTORY where a file is expected
(`IsADirectoryError`), never `chmod 000`: this suite runs as ROOT.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from test_local_context_file_railway import (  # pyright: ignore[reportPrivateUsage]
    _never_run,
)

from livespec_dev_tooling.fleet._context import RowFinding, RowPass, RowSkip
from livespec_dev_tooling.fleet._local_context import LocalContext
from livespec_dev_tooling.fleet._rows_local import (
    _worktree_pack_files,  # pyright: ignore[reportPrivateUsage]
    assert_worktree_pack,
)
from livespec_dev_tooling.fleet._rows_local_jsonc import reconcile_livespec_jsonc_complete

__all__: list[str] = []

_PACK_DIR = "dev-tooling"
_LIVESPEC_JSONC = ".livespec.jsonc"
_HARNESSED = '{"harnesses": {"claude": {"status": "supported"}}}'


def _ctx(*, checkout: Path) -> LocalContext:
    return LocalContext(checkout=checkout, home=checkout, run=_never_run)  # pyright: ignore[reportArgumentType]


def test_the_red_files_command_guard_refuses_to_run(tmp_path: Path) -> None:
    """The Red file's `_never_run` seam raises rather than spawning anything.

    Covered here because it is a GUARD: the Red file's own tests pass
    precisely by never invoking it, so its body is a dead line at Green
    unless something calls it deliberately.
    """
    with pytest.raises(AssertionError, match="must not spawn"):
        _ = _never_run(args=["git", "status"], cwd=tmp_path)


def test_unreadable_pack_file_skips_instead_of_crashing(tmp_path: Path) -> None:
    """An undecodable pack file is a SKIP, where it used to raise uncaught.

    `livespec-dev-tooling-a6et`: `is_file()` IS a real shield against a
    directory, so the reachable crash was a regular file whose BYTES are
    not valid UTF-8 — a `UnicodeDecodeError`, which is a `ValueError` and
    NOT an `OSError`.
    """
    pack = tmp_path / _PACK_DIR
    pack.mkdir()
    for name, body in _worktree_pack_files():
        _ = (pack / name).write_text(body, encoding="utf-8")

    # CONTROL: a fully canonical pack PASSES. Without this the skip below
    # could be firing for any reason at all — an earlier absent file short
    # -circuits the loop long before the corrupted one is ever read.
    assert isinstance(assert_worktree_pack(ctx=_ctx(checkout=tmp_path)), RowPass)

    corrupted = _worktree_pack_files()[0][0]
    _ = (pack / corrupted).write_bytes(b"\xff\xfe\x00\x80")
    outcome = assert_worktree_pack(ctx=_ctx(checkout=tmp_path))

    assert isinstance(outcome, RowSkip)
    assert "unreadable" in outcome.reason
    assert "file_undecodable" in outcome.reason


def test_unreadable_livespec_jsonc_skips_instead_of_crashing(tmp_path: Path) -> None:
    """A `.livespec.jsonc` that is a DIRECTORY is a SKIP, not an uncaught raise.

    The `exists()` pre-check this replaces returned True for a directory,
    so the read went through and raised `IsADirectoryError`.
    """
    # CONTROL: genuinely absent stays a warning-severity FINDING, never a skip.
    absent = reconcile_livespec_jsonc_complete(ctx=_ctx(checkout=tmp_path))
    assert isinstance(absent, RowFinding)

    (tmp_path / _LIVESPEC_JSONC).mkdir()
    outcome = reconcile_livespec_jsonc_complete(ctx=_ctx(checkout=tmp_path))

    assert isinstance(outcome, RowSkip)
    assert "file_unreadable" in outcome.reason


def test_unreadable_beads_config_skips_instead_of_crashing(tmp_path: Path) -> None:
    """The row's SECOND read gets the same treatment as its first.

    Both reads sat behind the same pre-check-pair anti-pattern in one
    function; converting only the first would have left this crash live.
    """
    _ = (tmp_path / _LIVESPEC_JSONC).write_text(_HARNESSED, encoding="utf-8")

    # CONTROL: an ABSENT `.beads/config.yaml` is an ANSWER — the row passes
    # saying the repo is not beads-backed, and must NOT skip.
    not_backed = reconcile_livespec_jsonc_complete(ctx=_ctx(checkout=tmp_path))
    assert isinstance(not_backed, RowPass)
    assert "not beads-backed" in not_backed.note

    beads = tmp_path / ".beads"
    beads.mkdir()
    (beads / "config.yaml").mkdir()
    outcome = reconcile_livespec_jsonc_complete(ctx=_ctx(checkout=tmp_path))

    assert isinstance(outcome, RowSkip)
    assert ".beads/config.yaml unreadable" in outcome.reason
