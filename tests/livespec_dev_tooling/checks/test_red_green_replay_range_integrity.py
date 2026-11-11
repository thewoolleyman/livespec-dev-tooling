"""The range gate refuses trailer-only commits and stale recorded test checksums.

`check-red-green-replay`'s commit-range validation judged a commit only by the
PRESENCE of trailer keys in its message, so two factory defects published
commits it accepted: a commit whose whole message is trailers (git runs the
commit-msg hook before its empty-message abort, and the hooks' trailer writers
turned the empty message into a trailer block), and a rebased commit whose
recorded `TDD-Red-Test-File-Checksum` no longer matched its own tree
(work-item livespec-dev-tooling-a4w7qr). Every fixture here is a real git
repository, because the property is about what a commit's own message and tree
hold, which no stand-in can show.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling.checks import red_green_replay

_SUBJECT_CHECK_ID = "red-green-replay-range-trailer-subject"
_CHECKSUM_CHECK_ID = "red-green-replay-range-stale-test-checksum"
_TEST_PATH = "tests/test_x.py"
_TEST_BYTES = b"def test_x() -> None:\n    assert True\n"
_PYPROJECT = (
    "[tool.livespec_dev_tooling]\n"
    'source_trees = ["livespec"]\n'
    'source_tree_prefixes = ["livespec/"]\n'
)
_GIT_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)


@pytest.fixture(autouse=True)
def _confine_children(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every git child on the fixture repo and out of the suite's coverage session."""
    for name in os.environ:
        if (
            name in _GIT_ENV_VARS
            or name == "COVERAGE_PROCESS_START"
            or name.startswith("COV_CORE_")
        ):
            monkeypatch.delenv(name)


def _git(*, repo: Path, args: list[str]) -> str:
    done = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def _init_repo(*, repo: Path) -> None:
    _git(repo=repo, args=["init", "-q"])
    _git(repo=repo, args=["config", "user.email", "test@example.com"])
    _git(repo=repo, args=["config", "user.name", "Test"])
    _git(repo=repo, args=["config", "commit.gpgsign", "false"])
    (repo / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", "chore: base"])
    _git(repo=repo, args=["update-ref", "refs/remotes/origin/master", "HEAD"])


def _commit(*, repo: Path, name: str, message: str) -> str:
    (repo / "docs").mkdir(exist_ok=True)
    (repo / "docs" / name).write_text(f"{name}\n", encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-q", "--cleanup=verbatim", "-m", message])
    return _git(repo=repo, args=["rev-parse", "HEAD"])


def _run_check(
    *, repo: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str]:
    monkeypatch.chdir(repo)
    monkeypatch.setattr(sys, "argv", ["red_green_replay"])
    returncode = red_green_replay.main()
    return returncode, capsys.readouterr().err


def test_range_fails_naming_a_commit_whose_subject_is_a_trailer(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(repo=tmp_path)
    good = _commit(repo=tmp_path, name="a.md", message="docs: a well-formed subject")
    trailer_only = _commit(
        repo=tmp_path,
        name="b.md",
        message=(
            "Factory-Run-Id: c5d75329e0b24a1f8d3a\n"
            "TDD-Suite-Green-Captured-At: 2026-11-10T00:00:00Z\n"
        ),
    )

    returncode, stderr = _run_check(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert returncode == 1
    assert _SUBJECT_CHECK_ID in stderr
    assert trailer_only in stderr
    assert good not in stderr


@pytest.mark.parametrize(
    "subject",
    [
        "fix: a conventional fix",
        "feat!: a breaking feature",
        "chore(spec): revise v182 - a scoped chore",
        "fabro(01M72BRVZPGR5ZHHREAWRBZFH2): dod_gate (success)",
        "Revert: an uppercase revert",
    ],
)
def test_range_accepts_every_conventional_subject(
    *,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    subject: str,
) -> None:
    _init_repo(repo=tmp_path)
    _commit(repo=tmp_path, name="a.md", message=f"{subject}\n\nFactory-Run-Id: c5d75329e0b2\n")

    returncode, stderr = _run_check(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert (returncode, _SUBJECT_CHECK_ID in stderr) == (0, False)


def _checksum(*, content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _recorded_commit(
    *, repo: Path, content: bytes, recorded_for: bytes, test: str = _TEST_PATH
) -> str:
    """Commit `content` at the test path under a message recording the checksum of `recorded_for`."""
    target = repo / _TEST_PATH
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(content)
    _git(repo=repo, args=["add", "-A"])
    message = (
        "fix: record a Red\n\n"
        f"TDD-Red-Test: {test}\n"
        f"TDD-Red-Test-File-Checksum: {_checksum(content=recorded_for)}\n"
    )
    _git(repo=repo, args=["commit", "-q", "-m", message])
    return _git(repo=repo, args=["rev-parse", "HEAD"])


def test_range_fails_naming_the_commit_and_test_file_whose_recorded_checksum_is_stale(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(repo=tmp_path)
    intact = _recorded_commit(repo=tmp_path, content=_TEST_BYTES, recorded_for=_TEST_BYTES)
    stale = _recorded_commit(
        repo=tmp_path, content=_TEST_BYTES + b"# rebased\n", recorded_for=_TEST_BYTES
    )

    returncode, stderr = _run_check(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert returncode == 1
    assert _CHECKSUM_CHECK_ID in stderr
    assert stale in stderr
    assert _TEST_PATH in stderr
    assert intact not in stderr


def test_range_fails_when_the_recorded_test_file_is_absent_from_the_commits_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(repo=tmp_path)
    sha = _recorded_commit(
        repo=tmp_path,
        content=_TEST_BYTES,
        recorded_for=_TEST_BYTES,
        test="tests/test_gone.py::test_x",
    )

    returncode, stderr = _run_check(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert returncode == 1
    assert sha in stderr
    assert "tests/test_gone.py" in stderr


def test_range_passes_when_every_subject_and_recorded_checksum_is_intact(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(repo=tmp_path)
    _recorded_commit(repo=tmp_path, content=_TEST_BYTES, recorded_for=_TEST_BYTES)
    _commit(repo=tmp_path, name="a.md", message="docs: a well-formed subject")

    returncode, stderr = _run_check(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert (returncode, _CHECKSUM_CHECK_ID in stderr, _SUBJECT_CHECK_ID in stderr) == (
        0,
        False,
        False,
    )


def test_range_names_integrity_violations_even_when_an_impl_commit_lacks_trailers(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _init_repo(repo=tmp_path)
    (tmp_path / "livespec").mkdir()
    (tmp_path / "livespec" / "impl.py").write_text("X = 1\n", encoding="utf-8")
    _git(repo=tmp_path, args=["add", "-A"])
    _git(repo=tmp_path, args=["commit", "-q", "-m", "fix: impl without trailers"])
    trailer_only = _commit(
        repo=tmp_path, name="b.md", message="Factory-Run-Id: c5d75329e0b24a1f8d3a\n"
    )
    stale = _recorded_commit(
        repo=tmp_path, content=_TEST_BYTES + b"# rebased\n", recorded_for=_TEST_BYTES
    )

    returncode, stderr = _run_check(repo=tmp_path, monkeypatch=monkeypatch, capsys=capsys)

    assert returncode == 1
    assert "red-green-replay-range-missing-trailers" in stderr
    assert _SUBJECT_CHECK_ID in stderr
    assert trailer_only in stderr
    assert _CHECKSUM_CHECK_ID in stderr
    assert stale in stderr
