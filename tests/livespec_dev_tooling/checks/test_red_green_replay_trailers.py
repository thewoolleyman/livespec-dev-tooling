"""Mirror-paired test for `livespec_dev_tooling/checks/_red_green_replay_trailers.py`.

The private sibling module carries the git commit-message trailer I/O
extracted from `_red_green_replay_modes.py` at the fleet-check-coverage
LLOC-reduction split: the HEAD-state resolver plus the HEAD readers and
the trailer writer. The functions' end-to-end coverage lives in
`test_red_green_replay.py` (they are exercised outside-in through the
parent supervisor's argv contract); THIS file pins the module surface
and unit-tests the readers and the trailer writer's replace-not-append
contract directly at the module boundary.

THE THREE READERS ARE ON THE `IOResult` RAILWAY (livespec-dev-tooling-qndn,
epic 8o8e) and this file pins the split that conversion exists to make:
git ANSWERING — including answering "no trailer", "no HEAD yet", or "not
a Red" — is `IOSuccess`; git NOT answering is `IOFailure`. Collapsing the
two is the defect. `head_red_awaiting_green` picks WHICH LEG of the
commit ritual runs, and its pre-conversion empty-stdout-on-failure read
as "no Red trailers", routing a Green amend to the suite-green leg: a
fail-WRONG, which stamps the wrong evidence rather than refusing.

⛔ THE UNBORN-HEAD CASE IS PINNED FIRST AND DELIBERATELY. A repository
with no commits is a REAL state — `just bootstrap` installs these hooks
before a new member repo's first commit — and `git log -1` exits 128
there. A conversion that read every non-zero exit as a failure would
refuse that first commit. That test is the guard against "tightening"
this module into a regression.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import structlog
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

from livespec_dev_tooling.checks._red_green_replay_trailers import (
    GitCommandFailed,
    _narrate_git_failure,
    current_head_sha,
    dropped_red_trailers,
    head_red_awaiting_green,
    head_trailer_value,
    write_trailers,
)

if TYPE_CHECKING:
    from collections.abc import Callable

__all__: list[str] = []


# Vars git sets when invoking hooks (lefthook commit-msg / pre-commit). These
# readers take NO cwd argument — they run against the process cwd — so under a
# hook GIT_DIR would point every one of them at the SURROUNDING repo instead
# of the tmp_path fixture the test builds.
_GIT_ENV_PASSTHROUGH_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)

_RED_TRAILERS = "TDD-Red-Test: tests/sample.py\nTDD-Red-Test-File-Checksum: sha256:aaaa\n"
_GREEN_TRAILERS = "TDD-Green-Verified-At: 2026-07-31T00:00:00Z\n"
# A Green-amend body written by `--amend -m` / `--amend -F`: the whole message
# replaced, so the Red block HEAD carries is gone (livespec-dev-tooling-zv78).
_ORPHAN_GREEN_BODY = "feat: green impl\n"

_SHA_LENGTH = 40


@pytest.fixture(autouse=True)
def _scrub_git_hook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)


def _git(*, cwd: Path, args: list[str]) -> None:
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        env={
            "HOME": str(cwd),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
            "PATH": "/usr/bin:/bin",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        },
    )


def _empty_repo(*, tmp_path: Path) -> Path:
    """An initialized repo with NO commits — the unborn-HEAD state."""
    repo = tmp_path / "repo"
    repo.mkdir(parents=True)
    _git(cwd=repo, args=["init", "--quiet", "-b", "work"])
    return repo


def _repo_with_commit(*, tmp_path: Path, message: str) -> Path:
    repo = _empty_repo(tmp_path=tmp_path)
    _git(cwd=repo, args=["commit", "--quiet", "--allow-empty", "-m", message])
    return repo


def _succeeded(result: object) -> object:
    """Unwrap an `IOSuccess`, asserting the railway took the success track."""
    assert isinstance(result, IOSuccess), f"expected IOSuccess; got {result!r}"
    return unsafe_perform_io(result.unwrap())


def _failed(result: object) -> GitCommandFailed:
    """Unwrap an `IOFailure`, asserting the railway took the failure track."""
    assert isinstance(result, IOFailure), f"expected IOFailure; got {result!r}"
    failure = unsafe_perform_io(result.failure())
    assert isinstance(failure, GitCommandFailed)
    return failure


def _refuse_to_run(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every `subprocess.run` raise `OSError`, as an unexecutable git does."""

    def _boom(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise OSError(2, "No such file or directory: 'git'")

    monkeypatch.setattr(subprocess, "run", _boom)


def test_trailer_helpers_are_callable() -> None:
    """The sibling module exposes the HEAD-state resolver, readers, and writer."""
    assert callable(head_red_awaiting_green)
    assert callable(head_trailer_value)
    assert callable(current_head_sha)
    assert callable(dropped_red_trailers)
    assert callable(write_trailers)


def test_head_red_awaiting_green_is_false_in_a_repo_with_no_commits(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ AN UNBORN HEAD IS AN ANSWER, NOT A FAILURE — the regression guard.

    `git log -1` exits 128 in a repo with no commits. Reading that as a
    failure would make the commit-msg hook REFUSE a new repository's very
    first commit, and `just bootstrap` installs these hooks before that
    commit exists. `head_red_awaiting_green` resolves HEAD first
    (`git rev-parse --verify --quiet HEAD`, exit 1 = unresolvable) precisely
    so this stays on the success track: there is no Red commit, so none is
    awaiting a Green.
    """
    monkeypatch.chdir(_empty_repo(tmp_path=tmp_path))
    assert _succeeded(head_red_awaiting_green()) is False


def test_head_red_awaiting_green_true_for_a_red_without_its_green(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_repo_with_commit(tmp_path=tmp_path, message=f"red\n\n{_RED_TRAILERS}"))
    assert _succeeded(head_red_awaiting_green()) is True


def test_head_red_awaiting_green_false_for_a_completed_pair(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A COMPLETED pair also carries Red trailers — presence alone misroutes.

    Work-item livespec-dev-tooling-xn0: keying the Green-amend leg on
    Red-trailer presence sent every fresh product commit atop finished
    history into that leg.
    """
    monkeypatch.chdir(
        _repo_with_commit(tmp_path=tmp_path, message=f"pair\n\n{_RED_TRAILERS}{_GREEN_TRAILERS}")
    )
    assert _succeeded(head_red_awaiting_green()) is False


def test_head_red_awaiting_green_outside_a_repo_is_a_failure_not_false(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not-a-repo is the OTHER non-zero exit, and it is a failure.

    The pre-conversion reader returned False here — identical to "no Red
    trailers" — so the ritual would route to the suite-green leg and stamp
    `TDD-Suite-Green-*` onto a commit whose HEAD it never read.
    """
    monkeypatch.chdir(tmp_path)
    failure = _failed(head_red_awaiting_green())
    assert failure.argv == "git rev-parse --verify --quiet HEAD"
    assert "exit 128" in failure.detail


def test_head_trailer_value_reads_a_present_trailer_and_empties_an_absent_one(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty stays an ANSWER: a commit legitimately carries no such trailer."""
    monkeypatch.chdir(_repo_with_commit(tmp_path=tmp_path, message=f"red\n\n{_RED_TRAILERS}"))
    assert _succeeded(head_trailer_value(key="TDD-Red-Test")) == "tests/sample.py"
    assert _succeeded(head_trailer_value(key="TDD-Green-Verified-At")) == ""


def test_head_trailer_value_outside_a_repo_is_a_failure_not_empty(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'or empty if absent' used to cover a git that never ran; now it does not."""
    monkeypatch.chdir(tmp_path)
    failure = _failed(head_trailer_value(key="TDD-Red-Test"))
    assert failure.argv.startswith("git log -1 --pretty=")
    assert "exit 128" in failure.detail


def test_current_head_sha_returns_the_resolved_sha(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(_repo_with_commit(tmp_path=tmp_path, message="seed"))
    sha = _succeeded(current_head_sha())
    assert isinstance(sha, str)
    assert len(sha) == _SHA_LENGTH, f"expected a full SHA; got {sha!r}"


def test_current_head_sha_outside_a_repo_is_a_failure_not_empty(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The empty string this used to return landed in a `TDD-Green-Parent-Reflog`.

    A failure recorded AS EVIDENCE is strictly worse than a refusal: the
    commit then reads as a completed pair whose parent is unknown.
    """
    monkeypatch.chdir(tmp_path)
    failure = _failed(current_head_sha())
    assert failure.argv == "git rev-parse HEAD"


def test_dropped_red_trailers_is_empty_when_the_amend_carried_the_block(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--amend --no-edit` passes the existing message through — nothing dropped."""
    message = f"red\n\n{_RED_TRAILERS}"
    monkeypatch.chdir(_repo_with_commit(tmp_path=tmp_path, message=message))
    assert _succeeded(dropped_red_trailers(message=message)) == ()


def test_dropped_red_trailers_names_every_line_a_replacing_amend_destroyed(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`--amend -m` / `-F` replace the whole message; each lost Red line is named.

    The diagnostic has to NAME them: the hook cannot re-derive the block (the
    Red pytest run that produced it is gone), so the author's only route back
    is to copy the reported lines forward.
    """
    monkeypatch.chdir(_repo_with_commit(tmp_path=tmp_path, message=f"red\n\n{_RED_TRAILERS}"))
    assert _succeeded(dropped_red_trailers(message=_ORPHAN_GREEN_BODY)) == (
        "TDD-Red-Test: tests/sample.py",
        "TDD-Red-Test-File-Checksum: sha256:aaaa",
    )


def test_dropped_red_trailers_outside_a_repo_is_a_failure_not_nothing_dropped(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⛔ The permissive answer and the unread one must not share a spelling.

    "Nothing was dropped" ADMITS the amend. Folding an unread HEAD onto it
    would admit exactly the half-pair this reader exists to catch, and would
    do it silently — the shape of the defect it was written for.
    """
    monkeypatch.chdir(tmp_path)
    failure = _failed(dropped_red_trailers(message=_ORPHAN_GREEN_BODY))
    assert failure.argv == "git log -1 --format=%B"
    assert "exit 128" in failure.detail


@pytest.mark.parametrize(
    "reader",
    [
        head_red_awaiting_green,
        current_head_sha,
        lambda: head_trailer_value(key="TDD-Red-Test"),
        lambda: dropped_red_trailers(message=_ORPHAN_GREEN_BODY),
    ],
)
def test_every_reader_reports_an_unexecutable_git_as_a_failure(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reader: Callable[[], object]
) -> None:
    """`subprocess.run` raising is the failure no reader could previously express.

    There is no `shutil.which` guard anywhere on this path — the hook is
    invoked BY git, so git existing reads as a given. That assumption is
    exactly what the catch replaces.
    """
    monkeypatch.chdir(tmp_path)
    _refuse_to_run(monkeypatch=monkeypatch)
    failure = _failed(reader())
    assert failure.argv.startswith("git ")
    assert "No such file or directory" in failure.detail


def test_narrate_git_failure_refuses_the_commit_and_names_the_command(
    *, capsys: pytest.CaptureFixture[str]
) -> None:
    """The shared refusal: exit 1, the argv to rerun, and no protocol blame.

    ⛔ Exit 1 rather than 0 is the whole point. Which leg the ritual runs is
    decided by reading HEAD; a read that did not happen cannot choose a leg,
    and stamping evidence the hook could not verify is worse than refusing.
    """
    structlog.configure(
        processors=[structlog.processors.JSONRenderer()],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    rc = _narrate_git_failure(
        log=structlog.get_logger("test"),
        failed=GitCommandFailed(argv="git rev-parse HEAD", detail="exit 128: fatal"),
    )
    assert rc == 1
    stderr = capsys.readouterr().err
    assert '"check_id": "red-green-replay-git-command-failed"' in stderr, stderr
    assert '"argv": "git rev-parse HEAD"' in stderr, stderr
    assert '"detail": "exit 128: fatal"' in stderr, stderr


def test_write_trailers_replaces_existing_keys_does_not_append(*, tmp_path: Path) -> None:
    """`write_trailers` REPLACES existing trailers with the same key, not append.

    Bug surfaced 2026-05-04 during v039 D3 authoring: re-amending
    a Red commit caused the commit-msg hook to call `write_trailers`
    a second time, which appended a NEW set of TDD-Red-* trailers
    instead of replacing the existing set. After three Red
    re-amends the commit message had three duplicate
    `TDD-Red-Test:` trailer lines, three duplicate
    `TDD-Red-Test-File-Checksum:` lines, etc. The Green-mode
    handler's `head_trailer_value(key="TDD-Red-Test")` returned
    a newline-joined string of three identical paths, which
    `Path.cwd() / recorded_test` then turned into a non-existent
    nested-path → FileNotFoundError. Workflow-blocking for any
    Red→Green pair where the Red commit needed re-authoring.

    Fix contract: `write_trailers` MUST use git's
    `--if-exists=replace` mode so that calling it twice with the
    same trailer key removes the prior occurrence and writes a
    fresh single instance. This test pins that behavior by
    constructing a commit-message file with pre-existing
    `TDD-Red-Test-File-Checksum:` trailers (simulating a prior
    write), invoking `write_trailers` with a NEW value for the
    same key, and asserting the resulting file has EXACTLY ONE
    occurrence of that key with the new value.
    """
    msg_path = tmp_path / "COMMIT_EDITMSG"
    msg_path.write_text(
        "feat: red — sample\n"
        "\n"
        "Body explaining the change.\n"
        "\n"
        "TDD-Red-Test: tests/dev-tooling/checks/test_sample.py\n"
        "TDD-Red-Test-File-Checksum: sha256:aaaa\n"
        "TDD-Red-Captured-At: 2026-05-04T01:00:00Z\n",
        encoding="utf-8",
    )

    write_trailers(
        msg_path=msg_path,
        trailers=(
            ("TDD-Red-Test", "tests/dev-tooling/checks/test_sample.py"),
            ("TDD-Red-Test-File-Checksum", "sha256:bbbb"),
            ("TDD-Red-Captured-At", "2026-05-04T02:00:00Z"),
        ),
    )

    final_message = msg_path.read_text(encoding="utf-8")
    test_file_lines = [
        line
        for line in final_message.splitlines()
        if line.startswith("TDD-Red-Test-File-Checksum:")
    ]
    assert len(test_file_lines) == 1, (
        f"write_trailers should REPLACE existing TDD-Red-Test-File-Checksum, "
        f"not append: expected exactly 1 occurrence, got {len(test_file_lines)}: "
        f"{test_file_lines!r}; full message:\n{final_message}"
    )
    assert "sha256:bbbb" in test_file_lines[0], (
        f"the surviving TDD-Red-Test-File-Checksum line should carry the NEW value "
        f"(sha256:bbbb), got: {test_file_lines[0]!r}"
    )
    assert "sha256:aaaa" not in final_message, (
        f"the OLD value (sha256:aaaa) should be GONE after replace, "
        f"but it persists in:\n{final_message}"
    )
