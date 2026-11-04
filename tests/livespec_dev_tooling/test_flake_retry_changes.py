"""The flake-retry change set is computable in the depth-1 checkouts CI actually makes.

`actions/checkout` fetches one commit. A master push then has no `HEAD^`, and a
pull request has no default-branch ref at all, so the change set used to read as
unknown and no failing test was ever retried (livespec-dev-tooling-bejgoo).
"""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

_GIT_IDENTITY = ("-c", "user.email=flake@example.invalid", "-c", "user.name=flake")
_RETRY = {"reruns": 3, "reruns_delay": 60}


def _git(*, repo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *_GIT_IDENTITY, *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _commit(*, repo: Path, files: dict[str, str], message: str) -> str:
    for name, text in files.items():
        _ = (repo / name).write_text(text, encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", message])
    return _git(repo=repo, args=["rev-parse", "HEAD"])


def _origin(*, root: Path) -> Path:
    origin = root / "origin"
    origin.mkdir()
    _git(repo=origin, args=["init", "-q", "-b", "master", "."])
    _ = _commit(
        repo=origin,
        files={
            "app.py": "VALUE = 1\n",
            "test_touched.py": "import app\n",
            "test_untouched.py": "X = 1\n",
        },
        message="base",
    )
    return origin


def _depth_one_checkout(*, root: Path, origin: Path, sha: str, ref: str) -> Path:
    """Reproduce `actions/checkout` at its default `fetch-depth: 1`."""
    work = root / "work"
    work.mkdir()
    _git(repo=work, args=["init", "-q", "."])
    _git(repo=work, args=["remote", "add", "origin", origin.as_uri()])
    _git(repo=work, args=["fetch", "-q", "--depth=1", "origin", f"+{sha}:{ref}"])
    _git(repo=work, args=["checkout", "-q", "--force", "-B", "master", ref])
    return work


def _items(*, root: Path, added: dict[str, list[object]]) -> list[pytest.Item]:
    return [
        cast(
            pytest.Item,
            SimpleNamespace(path=root / name, add_marker=added.setdefault(name, []).append),
        )
        for name in ("test_touched.py", "test_untouched.py")
    ]


@pytest.mark.integration
def test_a_depth_one_master_push_checkout_retries_only_tests_outside_the_commit(
    *, tmp_path: Path
) -> None:
    """HEAD equals origin/master and has no parent locally, yet its own commit is the change set."""
    plugin = importlib.import_module("livespec_dev_tooling.flake_retry")
    origin = _origin(root=tmp_path)
    pushed = _commit(
        repo=origin, files={"app.py": "VALUE = 2\n", "NOTES.md": "docs\n"}, message="push"
    )
    work = _depth_one_checkout(
        root=tmp_path, origin=origin, sha=pushed, ref="refs/remotes/origin/master"
    )

    assert plugin.change_paths(repo_root=work) == {Path("app.py"), Path("NOTES.md")}

    added: dict[str, list[object]] = {}
    plugin.mark_untouched_tests(root=work, items=_items(root=work, added=added))
    markers = cast(list[pytest.MarkDecorator], added["test_untouched.py"])
    assert [marker.kwargs for marker in markers] == [_RETRY]
    assert added["test_touched.py"] == []
