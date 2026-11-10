"""An empty commit message stays empty through both commit-msg trailer writers.

git runs the commit-msg hook BEFORE its empty-message abort. The two writers
that append trailers with `git interpret-trailers --in-place`
(`factory_provenance_gate._write_run_id_trailer` and
`_red_green_replay_trailers.write_trailers`) therefore turned an aborted empty
message into a commit whose whole message was trailers
(work-item livespec-dev-tooling-a4w7qr). The real-git fixtures here install a
commit-msg hook that drives both writers, so the abort is observed on a real
`git commit` rather than inferred.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling import commit_message
from livespec_dev_tooling.checks import _red_green_replay_trailers

_RUN_ID_KEY = "Factory-Run-Id"
_TRAILERS = (("TDD-Suite-Green-Captured-At", "2026-11-10T00:00:00Z"),)
_GIT_ENV_VARS = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
)
_HOOK = """#!{python}
import sys
from pathlib import Path

sys.path.insert(0, {checks_dir!r})
sys.argv = ["factory_provenance_gate", sys.argv[1], {marker!r}]
from livespec_dev_tooling.factory_provenance_gate import main
from _red_green_replay_trailers import write_trailers

main()
write_trailers(msg_path=Path(sys.argv[1]), trailers=((\"TDD-Red-Test\", \"tests/test_x.py\"),))
"""


@pytest.fixture(autouse=True)
def _confine_children(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every git child on the fixture repo and out of the suite's coverage session.

    An ambient `GIT_DIR` (exported while this repository's own commit hook runs
    the suite) would aim the hook's git calls at the surrounding repository, and
    `COV_CORE_*` would make the child interpreter self-instrument and write data
    files that race the parallel gate.
    """
    for name in os.environ:
        if name in _GIT_ENV_VARS or name.startswith("COV_CORE_"):
            monkeypatch.delenv(name)


def _git(*, repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, check=check, capture_output=True, text=True)


def _hooked_repo(*, repo: Path, marker: str) -> None:
    _git(repo=repo, args=["init", "-q"])
    _git(repo=repo, args=["config", "user.email", "test@example.com"])
    _git(repo=repo, args=["config", "user.name", "Test"])
    _git(repo=repo, args=["config", "commit.gpgsign", "false"])
    (repo / "seed.txt").write_text("seed\n", encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", "chore: seed"])
    checks_dir = Path(_red_green_replay_trailers.__file__).resolve().parent
    hook = repo / ".git" / "hooks" / "commit-msg"
    hook.write_text(
        _HOOK.format(python=sys.executable, checks_dir=str(checks_dir), marker=marker),
        encoding="utf-8",
    )
    hook.chmod(0o755)
    (repo / "change.txt").write_text("change\n", encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])


@pytest.mark.parametrize(
    ("text", "has_content"),
    [
        ("", False),
        ("\n", False),
        ("  \n\t\n", False),
        ("# Please enter the commit message\n#\n", False),
        ("fix: a subject\n", True),
        ("\n\nfix: a subject", True),
        ("# a comment\nfix: a subject\n", True),
    ],
)
def test_has_content_ignores_whitespace_and_comment_lines(*, text: str, has_content: bool) -> None:
    assert commit_message.has_content(text=text) is has_content


@pytest.mark.parametrize("marker", ["", "44c098ed2fb14a319c8d279cf238b735"])
def test_an_empty_message_commit_is_aborted_and_head_is_unchanged(
    *, tmp_path: Path, marker: str
) -> None:
    _hooked_repo(repo=tmp_path, marker=marker)
    head = _git(repo=tmp_path, args=["rev-parse", "HEAD"]).stdout

    attempt = _git(repo=tmp_path, args=["commit", "-m", ""], check=False)

    assert attempt.returncode != 0
    assert _git(repo=tmp_path, args=["rev-parse", "HEAD"]).stdout == head
    assert _git(repo=tmp_path, args=["rev-list", "--count", "HEAD"]).stdout.strip() == "1"


def test_a_real_message_still_receives_the_run_id_and_red_trailers(*, tmp_path: Path) -> None:
    _hooked_repo(repo=tmp_path, marker="44c098ed2fb14a319c8d279cf238b735")

    _git(repo=tmp_path, args=["commit", "-qm", "fix: a real subject"])

    message = _git(repo=tmp_path, args=["log", "-1", "--format=%B"]).stdout
    assert message.startswith("fix: a real subject")
    assert f"{_RUN_ID_KEY}: 44c098ed2fb14a319c8d279cf238b735" in message
    assert "TDD-Red-Test: tests/test_x.py" in message


@pytest.mark.parametrize("original", ["", "\n", "# only a comment\n"])
def test_write_trailers_leaves_a_message_without_content_untouched(
    *, tmp_path: Path, original: str
) -> None:
    message_path = tmp_path / "COMMIT_EDITMSG"
    message_path.write_text(original, encoding="utf-8")

    _red_green_replay_trailers.write_trailers(msg_path=message_path, trailers=_TRAILERS)

    assert message_path.read_text(encoding="utf-8") == original


def test_write_trailers_still_appends_to_a_message_with_content(*, tmp_path: Path) -> None:
    message_path = tmp_path / "COMMIT_EDITMSG"
    message_path.write_text("fix: a subject\n", encoding="utf-8")

    _red_green_replay_trailers.write_trailers(msg_path=message_path, trailers=_TRAILERS)

    assert message_path.read_text(encoding="utf-8").startswith("fix: a subject\n")
    assert "TDD-Suite-Green-Captured-At: 2026-11-10T00:00:00Z" in message_path.read_text(
        encoding="utf-8"
    )
