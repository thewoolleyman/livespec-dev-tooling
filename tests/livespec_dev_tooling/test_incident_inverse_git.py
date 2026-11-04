"""Real Git attribute isolation for safe complete incident inverses."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

import livespec_dev_tooling.incident_inverse as inverse

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_incident_inverse import _commit, _git
from test_incident_inverse import history as history_fixture


@pytest.fixture
def history(tmp_path):
    return history_fixture.__wrapped__(tmp_path)


@pytest.mark.parametrize("location", ["tracked", "source-info"])
@pytest.mark.parametrize("driver", ["union", "configured", "text"])
def test_merge_attributes_cannot_resolve_real_overlap_or_run_driver(
    history, tmp_path, driver, location
):
    repo, scope, _ = history
    marker = tmp_path / "unexpected-driver"
    attributes = repo / (".gitattributes" if location == "tracked" else ".git/info/attributes")
    attributes.write_text(f"shared.txt merge={driver}\n")
    (repo / "shared.txt").write_text(
        (repo / "shared.txt").read_text().replace("incident first\n", "later conflicting\n")
    )
    current = _commit(repo, "later overlap with candidate merge attribute")
    _git(repo, "config", "merge.configured.driver", f"touch {marker}")
    _git(repo, "config", "merge.text.driver", f"touch {marker}")
    result = inverse.plan_incident_inverse(repo_root=repo, scope=scope, expected_head=current)
    assert not marker.exists(), "inverse construction executed repository merge driver"
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "rollback-conflict"


def test_merge_attributes_cannot_discard_disjoint_later_edit(history, tmp_path):
    repo, scope, original = history
    marker = tmp_path / "unexpected-driver"
    (repo / ".gitattributes").write_text("* merge=configured\n")
    (repo / "shared.txt").write_text(
        (repo / "shared.txt").read_text().replace("line 45\n", "later unrelated\n")
    )
    current = _commit(repo, "later unrelated edit with candidate driver")
    _git(repo, "config", "merge.configured.driver", f"touch {marker}")
    result = inverse.plan_incident_inverse(repo_root=repo, scope=scope, expected_head=current)
    assert not marker.exists()
    assert isinstance(result, IOSuccess)
    plan = unsafe_perform_io(result.unwrap())
    assert _git(repo, "show", plan.tree_sha + ":shared.txt").decode() == original.replace(
        "line 45\n", "later unrelated\n"
    )


def test_isolated_inverse_uses_linked_worktree_shared_object_store(history, tmp_path):
    repo, scope, original = history
    worktree = tmp_path / "linked"
    _git(repo, "worktree", "add", "--detach", str(worktree), scope.merge_sha)
    result = inverse.plan_incident_inverse(
        repo_root=worktree, scope=scope, expected_head=scope.merge_sha
    )
    assert isinstance(result, IOSuccess)
    plan = unsafe_perform_io(result.unwrap())
    assert _git(repo, "show", plan.tree_sha + ":shared.txt").decode() == original
    assert _git(worktree, "status", "--porcelain") == b""


def test_isolated_inverse_preserves_sha256_object_format(tmp_path, monkeypatch):
    import test_incident_inverse as scenarios

    def git(*args, **kwargs):
        return _git(*args, *(("--object-format=sha256",) if args[1] == "init" else ()), **kwargs)

    monkeypatch.setattr(scenarios, "_git", git)
    repo, scope, original = history_fixture.__wrapped__(tmp_path)
    assert len(scope.merge_sha) == 64
    result = inverse.plan_incident_inverse(
        repo_root=repo, scope=scope, expected_head=scope.merge_sha
    )
    assert isinstance(result, IOSuccess)
    plan = unsafe_perform_io(result.unwrap())
    assert len(plan.tree_sha) == 64
    assert _git(repo, "show", plan.tree_sha + ":shared.txt").decode() == original


def test_isolated_inverse_refuses_a_true_binary_overlap(history):
    repo, scope, _ = history
    (repo / "old.bin").write_bytes(b"\x00later conflicting binary\xff")
    (repo / ".gitattributes").write_text("old.bin merge=union\n")
    current = _commit(repo, "later binary overlap")
    result = inverse.plan_incident_inverse(repo_root=repo, scope=scope, expected_head=current)
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "rollback-conflict"
