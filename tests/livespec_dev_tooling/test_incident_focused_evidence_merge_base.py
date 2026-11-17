"""The focused-evidence changed set is the head's own change, taken from the merge base.

A master commit that lands after the head was cut is not part of the head's change.
The two-dot diff against the attempt base reported it as an inverted change and pulled
its tests into the selection (livespec-dev-tooling-r5dbpp).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from livespec_dev_tooling._incident_focused_scope import changed_paths
from livespec_dev_tooling._incident_focused_types import FocusedScope
from livespec_dev_tooling.incident_git import IncidentGitError

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-r5dbpp


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _commit(root: Path, name: str, text: str) -> str:
    (root / name).parent.mkdir(parents=True, exist_ok=True)
    (root / name).write_text(text)
    _git(root, "add", ".")
    _git(root, "commit", "-qm", name)
    return _git(root, "rev-parse", "HEAD")


def _repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.name", "Fixture")
    _git(tmp_path, "config", "user.email", "fixture@example.org")
    return tmp_path


def _identity(*, base: str, head: str) -> SimpleNamespace:
    return SimpleNamespace(base_sha=base, head_sha=head)


def _scope(root: Path, head: str) -> FocusedScope:
    return FocusedScope(
        tree_hash=_git(root, "rev-parse", f"{head}^{{tree}}"),
        source_prefixes=("src/",),
        test_prefixes=("tests/",),
        related_tests=(),
        prior_paths=(),
    )


def test_a_master_commit_landed_after_the_head_was_cut_is_not_in_the_changed_set(
    tmp_path: Path,
) -> None:
    root = _repo(tmp_path)
    fork = _commit(root, "src/widget.py", "ANSWER = 42\n")
    _git(root, "checkout", "-q", "-b", "incident")
    head = _commit(root, "tests/test_widget.py", "def test_widget():\n    assert True\n")
    _git(root, "checkout", "-q", "main")
    moved = _commit(root, "tests/test_unrelated.py", "def test_unrelated():\n    assert True\n")
    assert fork != moved

    paths = changed_paths(
        repo_root=root, identity=_identity(base=moved, head=head), scope=_scope(root, head)
    )

    assert paths == {"tests/test_widget.py"}


def test_a_base_with_no_merge_base_with_the_head_is_a_named_refusal(tmp_path: Path) -> None:
    root = _repo(tmp_path)
    _commit(root, "src/widget.py", "ANSWER = 42\n")
    _git(root, "checkout", "-q", "--orphan", "other")
    stranger = _commit(root, "tests/test_other.py", "def test_other():\n    assert True\n")
    _git(root, "checkout", "-q", "main")
    head = _git(root, "rev-parse", "HEAD")

    with pytest.raises(IncidentGitError):
        changed_paths(
            repo_root=root,
            identity=_identity(base=stranger, head=head),
            scope=_scope(root, head),
        )
