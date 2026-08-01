"""`is_docs_only_change` puts its undecidable outcomes on the `IOResult` railway.

Row 1 of the `OPEN` table in `plan/rop-railway-enforcement/qndn-75-triage.md`,
and the first unblocked offender of `livespec-dev-tooling-8o8e.9`. The `bool`
it returned fused a VERDICT with a NON-READ: a checkout `git` cannot read the
object out of, and a revision that does not parse, both answered `False` — the
same answer a real source change gives — while `git` missing from PATH did not
answer at all and raised `OSError` out of a function annotated `bool`.

The load-bearing pair is
`test_a_checkout_git_cannot_read_is_undecidable` beside
`test_a_revision_without_the_path_answers_false`: both were `False` before,
and they are on OPPOSITE tracks now. The second is the ruling this unit turns
on — `git` was asked whether a blob exists, it looked, and there is none, so
"not a docs-only change" is a verdict it ANSWERED rather than one the function
assumed.
"""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks._docs_only_change import is_docs_only_change

if TYPE_CHECKING:
    from pathlib import Path

_REL = "pkg/mod.py"

_ORIGINAL = '''"""Module docstring."""


def answer() -> int:
    # An inline comment.
    return 41 + 1
'''

_DOCS_ONLY_EDIT = '''"""Module docstring, reworded."""


def answer() -> int:
    """A docstring that was not here before."""
    # A different inline comment.
    return 41 + 1
'''

_REAL_EDIT = '''"""Module docstring."""


def answer() -> int:
    # An inline comment.
    return 40 + 2
'''

_UNPARSEABLE = "def answer( -> int:\n"


def _git(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run `git` hermetically: no global config, no ambient `GIT_*` inheritance."""
    # S603/S607: argv is a fixed list (literal git binary + test-controlled
    # args); bare `git` is the canonical invocation per system PATH.
    return subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={"HOME": str(cwd), "GIT_CONFIG_GLOBAL": "/dev/null", "PATH": "/usr/bin:/bin"},
    )


@pytest.fixture(autouse=True)
def _no_ambient_git_env(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Drop every inherited `GIT_*` var for the duration of each test.

    The module under test deliberately does NOT scrub them — reading
    `GIT_INDEX_FILE` is how the commit-time caller sees the index of the
    commit in progress. That makes the suite's own environment
    load-bearing: run under a git hook, an inherited `GIT_DIR` would point
    "not a repository" at the hook's repository instead, and the
    `repository-unreadable` test would pass for the wrong reason.
    """
    for name in [key for key in os.environ if key.startswith("GIT_")]:
        monkeypatch.delenv(name, raising=False)


def _repo_with_committed(*, tmp_path: Path, body: str) -> Path:
    """Init a repo at `tmp_path` and commit `body` at `_REL`."""
    _git(cwd=tmp_path, args=["init", "-q"])
    (tmp_path / "pkg").mkdir()
    (tmp_path / _REL).write_text(body, encoding="utf-8")
    _git(cwd=tmp_path, args=["add", _REL])
    _git(cwd=tmp_path, args=["-c", "user.email=t@e", "-c", "user.name=T", "commit", "-qm", "base"])
    return tmp_path


def _stage(*, tmp_path: Path, body: str) -> None:
    (tmp_path / _REL).write_text(body, encoding="utf-8")
    _git(cwd=tmp_path, args=["add", _REL])


def test_a_comment_and_docstring_only_edit_answers_true(*, tmp_path: Path) -> None:
    """The carve-out's happy path survives the conversion: `IOSuccess(True)`."""
    _repo_with_committed(tmp_path=tmp_path, body=_ORIGINAL)
    _stage(tmp_path=tmp_path, body=_DOCS_ONLY_EDIT)

    decided = is_docs_only_change(before=f"HEAD:{_REL}", after=f":{_REL}", cwd=tmp_path)

    assert isinstance(decided, IOSuccess)
    assert unsafe_perform_io(decided.unwrap()) is True


def test_a_real_source_change_answers_false(*, tmp_path: Path) -> None:
    """A logical edit is a VERDICT, and it stays on the success track."""
    _repo_with_committed(tmp_path=tmp_path, body=_ORIGINAL)
    _stage(tmp_path=tmp_path, body=_REAL_EDIT)

    decided = is_docs_only_change(before=f"HEAD:{_REL}", after=f":{_REL}", cwd=tmp_path)

    assert isinstance(decided, IOSuccess)
    assert unsafe_perform_io(decided.unwrap()) is False


def test_a_revision_without_the_path_answers_false(*, tmp_path: Path) -> None:
    """A NEW file is an answer, not a failure — `git` looked and there is no blob.

    This is the ruling the unit turns on. `HEAD` does not carry the path, so
    no comment-only edit can relate the two revisions and `False` is a
    verdict `git` produced. Contrast `test_a_checkout_git_cannot_read_is_undecidable`,
    which was the SAME `False` before this conversion.
    """
    _repo_with_committed(tmp_path=tmp_path, body=_ORIGINAL)
    (tmp_path / "pkg" / "fresh.py").write_text(_ORIGINAL, encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "pkg/fresh.py"])

    decided = is_docs_only_change(before="HEAD:pkg/fresh.py", after=":pkg/fresh.py", cwd=tmp_path)

    assert isinstance(decided, IOSuccess)
    assert unsafe_perform_io(decided.unwrap()) is False


def test_a_staged_deletion_answers_false(*, tmp_path: Path) -> None:
    """The mirror case: the AFTER revision is the one missing the path."""
    _repo_with_committed(tmp_path=tmp_path, body=_ORIGINAL)
    _git(cwd=tmp_path, args=["rm", "-q", _REL])

    decided = is_docs_only_change(before=f"HEAD:{_REL}", after=f":{_REL}", cwd=tmp_path)

    assert isinstance(decided, IOSuccess)
    assert unsafe_perform_io(decided.unwrap()) is False


def test_an_unparseable_before_revision_is_undecidable(*, tmp_path: Path) -> None:
    """A committed file that does not compile is named as such, not as a source change."""
    _repo_with_committed(tmp_path=tmp_path, body=_UNPARSEABLE)
    _stage(tmp_path=tmp_path, body=_ORIGINAL)

    decided = is_docs_only_change(before=f"HEAD:{_REL}", after=f":{_REL}", cwd=tmp_path)

    assert isinstance(decided, IOFailure)
    undecidable = unsafe_perform_io(decided.failure())
    assert undecidable.reason == "revision-unparseable"
    assert undecidable.detail == f"HEAD:{_REL}"


def test_an_unparseable_after_revision_is_undecidable(*, tmp_path: Path) -> None:
    """The staged side is read too, so a syntax error there is equally undecidable."""
    _repo_with_committed(tmp_path=tmp_path, body=_ORIGINAL)
    _stage(tmp_path=tmp_path, body=_UNPARSEABLE)

    decided = is_docs_only_change(before=f"HEAD:{_REL}", after=f":{_REL}", cwd=tmp_path)

    assert isinstance(decided, IOFailure)
    undecidable = unsafe_perform_io(decided.failure())
    assert undecidable.reason == "revision-unparseable"
    assert undecidable.detail == f":{_REL}"


def test_a_checkout_git_cannot_read_is_undecidable(*, tmp_path: Path) -> None:
    """A directory that is not a repository is a NON-READ, and says so.

    Before the conversion this returned the same `False` as a real source
    change, so `commit_pairs_source_and_test` told the author "source change
    staged without paired test change" — a definitive verdict about a commit
    it had read nothing of.
    """
    decided = is_docs_only_change(before=f"HEAD:{_REL}", after=f":{_REL}", cwd=tmp_path)

    assert isinstance(decided, IOFailure)
    undecidable = unsafe_perform_io(decided.failure())
    assert undecidable.reason == "repository-unreadable"
    assert "not a git repository" in undecidable.detail


def test_git_absent_from_path_is_undecidable(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git` missing from PATH used to RAISE out of a function annotated `bool`.

    That arm is the one the old docstring's "fail closed" claim never
    covered: it did not fail closed, it propagated an `OSError` to a caller
    typed to receive a boolean.
    """
    _repo_with_committed(tmp_path=tmp_path, body=_ORIGINAL)
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    monkeypatch.setenv("PATH", str(empty_bin))

    decided = is_docs_only_change(before=f"HEAD:{_REL}", after=f":{_REL}", cwd=tmp_path)

    assert isinstance(decided, IOFailure)
    undecidable = unsafe_perform_io(decided.failure())
    assert undecidable.reason == "git-not-run"


def test_a_cwd_that_is_not_a_directory_is_undecidable(*, tmp_path: Path) -> None:
    """The other `OSError` spelling, and it needs no monkeypatching to reach.

    `chmod 000` proves nothing here — this suite runs as root — so
    unreadability is spelled as a FILE where a directory is expected. The
    resulting `NotADirectoryError` is an `OSError` that is NOT a
    `FileNotFoundError`, which matters because absence is the ANSWER arm
    everywhere else in this module.
    """
    not_a_dir = tmp_path / "regular-file"
    not_a_dir.write_text("", encoding="utf-8")

    decided = is_docs_only_change(before=f"HEAD:{_REL}", after=f":{_REL}", cwd=not_a_dir)

    assert isinstance(decided, IOFailure)
    undecidable = unsafe_perform_io(decided.failure())
    assert undecidable.reason == "git-not-run"
