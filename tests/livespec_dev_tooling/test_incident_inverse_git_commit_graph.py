"""A forged objects/info/commit-graph cannot feed false history to the isolated object view."""

from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

from livespec_dev_tooling._incident_inverse_git import IsolatedGit, scope_matches_git

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_incident_inverse import _git
from test_incident_inverse import history as history_fixture

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-a3xotn


@pytest.fixture
def history(tmp_path):
    return history_fixture.__wrapped__(tmp_path)


def _forge_commit_graph(*, repo: Path, child: str, claimed_parent: str) -> None:
    """Write a real commit-graph, then rewrite `child`'s first parent to `claimed_parent`."""
    _git(repo, "commit-graph", "write", "--reachable")
    graph = repo / ".git" / "objects" / "info" / "commit-graph"
    data = bytearray(graph.read_bytes())
    hash_length = len(child) // 2
    chunk_count = data[6]
    chunks = {}
    for index in range(chunk_count):
        entry = 8 + index * 12
        chunks[bytes(data[entry : entry + 4])] = struct.unpack(">Q", data[entry + 4 : entry + 12])[
            0
        ]
    oids_at = chunks[b"OIDL"]
    commit_count = (chunks[b"CDAT"] - oids_at) // hash_length
    oids = [
        bytes(data[oids_at + position * hash_length : oids_at + (position + 1) * hash_length]).hex()
        for position in range(commit_count)
    ]
    record = chunks[b"CDAT"] + oids.index(child) * (hash_length + 16) + hash_length
    data[record : record + 4] = struct.pack(">I", oids.index(claimed_parent))
    graph.write_bytes(bytes(data))


def _forged_pair(*, repo: Path, scope) -> tuple[str, str]:
    """Forge the merge commit's parent to the base, skipping the first landed commit.

    Git parses a commit it was named directly from the object itself and reads the graph
    only for commits it reaches by walking, so the forged commit sits between a `tip` above
    it and the walk. Returns the tip and a sibling of the merge commit on the first landed
    commit: their true merge base is that first commit, their forged one is the base.
    """
    first = scope.landed_commits[0]
    tree = _git(repo, "rev-parse", scope.merge_sha + "^{tree}").decode().strip()
    tip = _git(repo, "commit-tree", tree, "-p", scope.merge_sha, "-m", "tip").decode().strip()
    sibling = _git(repo, "commit-tree", tree, "-p", first, "-m", "sibling").decode().strip()
    _git(repo, "update-ref", "refs/heads/tip", tip)
    _git(repo, "update-ref", "refs/heads/sibling", sibling)
    _forge_commit_graph(repo=repo, child=scope.merge_sha, claimed_parent=scope.before_sha)
    return tip, sibling


def test_forged_commit_graph_changes_the_unprotected_answer(history):
    repo, scope, _ = history
    tip, sibling = _forged_pair(repo=repo, scope=scope)
    forged = _git(repo, "merge-base", tip, sibling).decode().strip()
    assert forged == scope.before_sha, "the fixture must forge history for the control read"


@pytest.mark.parametrize(
    "args",
    [
        ("merge-base", "{tip}", "{sibling}"),
        ("rev-list", "--parents", "{tip}"),
        ("ls-tree", "-r", "{tip}"),
        ("diff-tree", "-r", "--no-renames", "{tip}"),
    ],
)
def test_isolated_view_answers_as_if_the_clone_had_no_commit_graph(history, args):
    repo, scope, _ = history
    tip, sibling = _forged_pair(repo=repo, scope=scope)
    args = tuple(part.format(tip=tip, sibling=sibling) for part in args)
    with IsolatedGit.view(root=repo) as (administration, objects):
        viewed = IsolatedGit.run(
            root=repo, administration=administration, objects=objects, args=args
        )
    (repo / ".git" / "objects" / "info" / "commit-graph").unlink()
    with IsolatedGit.view(root=repo) as (administration, objects):
        honest = IsolatedGit.run(
            root=repo, administration=administration, objects=objects, args=args
        )
    assert viewed == honest


def test_scope_verification_reads_no_forged_history(history):
    repo, scope, _ = history
    _forged_pair(repo=repo, scope=scope)
    assert scope_matches_git(root=repo, scope=scope, expected_head=scope.merge_sha)
    assert IsolatedGit.patch(root=repo, before=scope.before_sha, merge=scope.merge_sha)
