"""Every pytest-xdist worker of a session resolves the same flake-retry change set.

Each worker computes the change set during collection, so in a depth-1 checkout they
all run `git fetch --deepen=1` at the same moment and collide on git's shallow lock. A
worker that lost that race read `HEAD^2` as missing and withheld its retries
(livespec-dev-tooling-xfe2po). The interleaving is ordered by a rendezvous around git's
real shallow lock. The wall-clock wait is a liveness guard, not what decides the verdict.
"""

from __future__ import annotations

import importlib
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event

import pytest

_GIT_IDENTITY = ("-c", "user.email=flake@example.invalid", "-c", "user.name=flake")
_LIVENESS_SECONDS = 3.0
_EXPECTED = {Path("app.py")}


def _git(*, repo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", *_GIT_IDENTITY, *args], cwd=repo, check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _commit(*, repo: Path, name: str, text: str, message: str) -> None:
    _ = (repo / name).write_text(text, encoding="utf-8")
    _git(repo=repo, args=["add", "-A"])
    _git(repo=repo, args=["commit", "-qm", message])


def _merge_origin(*, root: Path) -> tuple[Path, str]:
    """An origin whose head is the merge commit GitHub builds for a pull request."""
    origin = root / "origin"
    origin.mkdir()
    _git(repo=origin, args=["init", "-q", "-b", "master", "."])
    _commit(repo=origin, name="app.py", text="VALUE = 1\n", message="base")
    _git(repo=origin, args=["checkout", "-q", "-b", "feature"])
    _commit(repo=origin, name="app.py", text="VALUE = 2\n", message="the pr")
    _git(repo=origin, args=["checkout", "-q", "master"])
    _commit(repo=origin, name="elsewhere.py", text="Y = 1\n", message="master moved on")
    _git(repo=origin, args=["merge", "-q", "--no-ff", "-m", "merge", "feature"])
    return origin, _git(repo=origin, args=["rev-parse", "HEAD"])


def _depth_one_checkout(*, work: Path, origin: Path, sha: str) -> Path:
    """Reproduce `actions/checkout` on a pull request's merge ref at `fetch-depth: 1`."""
    work.mkdir()
    _git(repo=work, args=["init", "-q", "."])
    _git(repo=work, args=["remote", "add", "origin", origin.as_uri()])
    _git(
        repo=work, args=["fetch", "-q", "--depth=1", "origin", f"+{sha}:refs/remotes/pull/1/merge"]
    )
    _git(repo=work, args=["checkout", "-q", "--force", "-B", "master", "refs/remotes/pull/1/merge"])
    return work


def test_a_worker_arriving_during_another_workers_fetch_resolves_the_same_change_set(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first worker's fetch holds git's real shallow lock while the second one arrives."""
    changes = importlib.import_module("livespec_dev_tooling.flake_retry_changes")
    origin, sha = _merge_origin(root=tmp_path)
    work = _depth_one_checkout(work=tmp_path / "work", origin=origin, sha=sha)
    shallow_lock = work / ".git" / "shallow.lock"
    real_runner = changes.default_gate_command_runner
    fetching = Event()
    second_finished = Event()

    def runner(*, argv: list[str], cwd: Path) -> object:
        if "fetch" in argv and not fetching.is_set():
            _ = shallow_lock.write_text("", encoding="utf-8")
            fetching.set()
            _ = second_finished.wait(timeout=_LIVENESS_SECONDS)
            shallow_lock.unlink()
        return real_runner(argv=argv, cwd=cwd)

    monkeypatch.setattr(changes, "default_gate_command_runner", runner)

    def second_worker() -> set[Path] | None:
        _ = fetching.wait(timeout=_LIVENESS_SECONDS)
        resolved = changes.change_paths(repo_root=work)
        second_finished.set()
        return resolved

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(changes.change_paths, repo_root=work)
        second = pool.submit(second_worker)
        resolved = [first.result(), second.result()]

    assert resolved == [_EXPECTED, _EXPECTED]


def test_a_change_set_that_cannot_be_fetched_names_the_fetch_and_its_error(
    *, tmp_path: Path
) -> None:
    changes = importlib.import_module("livespec_dev_tooling.flake_retry_changes")
    origin, sha = _merge_origin(root=tmp_path)
    work = _depth_one_checkout(work=tmp_path / "work", origin=origin, sha=sha)
    _git(repo=work, args=["remote", "set-url", "origin", (tmp_path / "gone").as_uri()])

    resolved = changes.change_paths(repo_root=work)
    reason = changes.withheld_reason()

    assert (resolved, "`git fetch --quiet --deepen=1 origin" in reason, "fatal:" in reason) == (
        None,
        True,
        True,
    )


def test_a_fetch_lock_that_cannot_be_opened_still_resolves_the_change_set(
    *, tmp_path: Path
) -> None:
    changes = importlib.import_module("livespec_dev_tooling.flake_retry_changes")
    origin, sha = _merge_origin(root=tmp_path)
    work = _depth_one_checkout(work=tmp_path / "work", origin=origin, sha=sha)
    (work / ".git" / "livespec-flake-retry-fetch.lock").mkdir()

    assert changes.change_paths(repo_root=work) == _EXPECTED
