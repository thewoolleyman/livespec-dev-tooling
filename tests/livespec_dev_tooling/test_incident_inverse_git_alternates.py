"""A reference clone that borrows another object store is refused by the isolated object view."""

from __future__ import annotations

import sys
from contextlib import ExitStack
from pathlib import Path

import pytest
from returns.io import IOFailure

import livespec_dev_tooling.incident_inverse as inverse
from livespec_dev_tooling._incident_inverse_git import (
    IsolatedGit,
    build_inverse,
    scope_matches_git,
)
from livespec_dev_tooling.incident_git import IncidentGitError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_incident_inverse import _git
from test_incident_inverse import history as history_fixture

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-a3xotn


@pytest.fixture
def history(tmp_path):
    return history_fixture.__wrapped__(tmp_path)


def _borrow(*, repo: Path, name: str, tmp_path: Path) -> Path:
    """Name another store in `repo`'s `objects/info/<name>`; return that file."""
    other = tmp_path / "other-store"
    other.mkdir()
    _git(other, "init")
    _git(other, "hash-object", "-w", "--stdin", data=b"foreign object\n")
    named = repo / ".git" / "objects" / "info" / name
    named.write_text(str(other / ".git" / "objects") + "\n")
    return named


@pytest.mark.parametrize("name", ["alternates", "http-alternates"])
def test_view_refuses_a_clone_naming_another_object_store(history, tmp_path, name):
    repo, _, _ = history
    named = _borrow(repo=repo, name=name, tmp_path=tmp_path)
    with ExitStack() as stack, pytest.raises(IncidentGitError) as refusal:
        stack.enter_context(IsolatedGit.view(root=repo))
    assert str(named) in str(refusal.value)


@pytest.mark.parametrize("name", ["alternates", "http-alternates"])
def test_every_scope_reader_gets_the_refusal_from_the_view_itself(history, tmp_path, name):
    repo, scope, _ = history
    named = _borrow(repo=repo, name=name, tmp_path=tmp_path)
    readers = (
        lambda: scope_matches_git(root=repo, scope=scope, expected_head=scope.merge_sha),
        lambda: build_inverse(root=repo, scope=scope, expected_head=scope.merge_sha),
        lambda: IsolatedGit.patch(root=repo, before=scope.before_sha, merge=scope.merge_sha),
    )
    for reader in readers:
        with pytest.raises(IncidentGitError) as refusal:
            reader()
        assert str(named) in str(refusal.value)
    result = inverse.plan_incident_inverse(
        repo_root=repo, scope=scope, expected_head=scope.merge_sha
    )
    assert isinstance(result, IOFailure)


def test_a_clone_with_no_borrowed_store_is_still_read(history):
    repo, scope, _ = history
    assert scope_matches_git(root=repo, scope=scope, expected_head=scope.merge_sha)
