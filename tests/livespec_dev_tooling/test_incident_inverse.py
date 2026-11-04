"""Real Git multi-commit inverse and scoped controller receipt scenarios."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import replace

import pytest
from returns.io import IOFailure, IOSuccess
from returns.unsafe import unsafe_perform_io

import livespec_dev_tooling.incident_inverse as inverse
from livespec_dev_tooling._incident_inverse_types import (
    InversePublishResult,
    LandedIncident,
)
from livespec_dev_tooling._incident_observer_types import (
    LeafCompletion,
    ObserverRegistration,
    RecoveryIntent,
)

# EXPEDITED_INCIDENT_RESPONSE flag: livespec-dev-tooling-lgfo3v


def _git(repo, *args, data=None):
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("GIT_", "COV_CORE_", "COVERAGE_"))
    }
    environment.update(
        GIT_AUTHOR_NAME="Inverse fixture",
        GIT_AUTHOR_EMAIL="inverse@example.invalid",
        GIT_COMMITTER_NAME="Inverse fixture",
        GIT_COMMITTER_EMAIL="inverse@example.invalid",
    )
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        input=data,
        capture_output=True,
        check=True,
        env=environment,
    ).stdout


def _commit(repo, message):
    _git(repo, "add", "--all")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD").decode().strip()


@pytest.fixture
def history(tmp_path):
    repo = tmp_path / "repository"
    repo.mkdir()
    _git(repo, "init", "-b", "master")
    text = "\n".join(f"line {number}" for number in range(50)) + "\n"
    (repo / "shared.txt").write_text(text)
    (repo / "old.bin").write_bytes(b"\x00before\xff")
    (repo / "removed.txt").write_text("restore me\n")
    before = _commit(repo, "base")
    (repo / "shared.txt").write_text(text.replace("line 2\n", "incident first\n"))
    (repo / "old.bin").write_bytes(b"\x00incident\xff")
    (repo / "removed.txt").unlink()
    first = _commit(repo, "incident first")
    (repo / "shared.txt").write_text(
        (repo / "shared.txt").read_text().replace("line 5\n", "incident second\n")
    )
    (repo / "introduced.txt").write_text("incident added\n")
    (repo / "script.sh").write_text("#!/bin/sh\nexit 0\n")
    (repo / "script.sh").chmod(0o755)
    merged = _commit(repo, "incident second")
    patch = _git(
        repo,
        "diff",
        "--binary",
        "--full-index",
        "--no-ext-diff",
        "--no-textconv",
        before,
        merged,
        "--",
    )
    scope = LandedIncident(
        repository="owner/repo",
        pr_number=71,
        original_base_sha=before,
        original_head_sha=merged,
        before_sha=before,
        merge_sha=merged,
        landed_commits=(first, merged),
        landed_trees=tuple(
            _git(repo, "rev-parse", commit + "^{tree}").decode().strip()
            for commit in (first, merged)
        ),
        patch_sha256=hashlib.sha256(patch).hexdigest(),
        changed_paths=("introduced.txt", "old.bin", "removed.txt", "script.sh", "shared.txt"),
        authority_sha256=hashlib.sha256(b"canonical receipt").hexdigest(),
    )
    return repo, scope, text


def _intent(scope):
    registration = ObserverRegistration(
        repository=scope.repository,
        incident_item_id="incident-1",
        attempt_id="attempt-1",
        operation_id="operation-1",
        generation=2,
        owner="controller-owner",
        phase="repair",
        head_sha=scope.merge_sha,
        run_id=81,
        required_jobs=("tests",),
        controller_release="v1.2.3",
        controller_revision="f" * 40,
        candidate_revision=scope.original_head_sha,
        authority_receipt=b"canonical receipt",
    )
    completion = LeafCompletion(
        delivery_id="event-1",
        repository=scope.repository,
        head_sha=scope.merge_sha,
        branch="master",
        run_id=81,
        job_id=82,
        job_name="tests",
        conclusion="failure",
    )
    return RecoveryIntent(
        action_id="exact-action-1", registration=registration, completion=completion
    )


class Forge:
    def __init__(self, *, repo, scope):
        self.repo, self.scope = repo, scope
        self.receipt = None
        self.authorized = True
        self.requests = []
        self.conflicts = []
        self.result = "committed"
        self.movement = None
        self.available_scope = True
        self.keep_receipt = True

    def landed_incident(self, *, intent):
        assert intent.action_id
        return self.scope if self.available_scope else None

    def authorize_inverse(self, *, intent, scope):
        return self.authorized and scope == self.scope and bool(intent.action_id)

    def read_master_head(self, *, repository, branch):
        assert repository == self.scope.repository
        return _git(self.repo, "rev-parse", branch).decode().strip()

    def read_exact_receipt(self, *, intent):
        assert intent.action_id
        return self.receipt

    def publish_inverse(self, *, request):
        self.requests.append(request)
        if self.movement:
            self.movement()
        if (
            self.read_master_head(repository=request.plan.scope.repository, branch="master")
            != request.plan.expected_head
        ):
            return InversePublishResult(status="head-moved")
        if self.result != "committed":
            return InversePublishResult(status=self.result)
        commit = (
            _git(
                self.repo,
                "commit-tree",
                request.plan.tree_sha,
                "-p",
                request.plan.expected_head,
                data=request.message.encode(),
            )
            .decode()
            .strip()
        )
        _git(self.repo, "update-ref", "refs/heads/master", commit, request.plan.expected_head)
        if self.keep_receipt:
            self.receipt = "merge:" + commit + ":action:" + request.intent.action_id
        return InversePublishResult(
            status="committed", merge_sha=commit, tree_sha=request.plan.tree_sha
        )

    def record_conflict(self, *, request):
        self.conflicts.append(request)
        self.receipt = request.receipt if self.keep_receipt else None
        return self.receipt


def test_complete_inverse_preserves_later_same_file_edit_binary_mode_and_worktree(history):
    repo, scope, text = history
    (repo / "shared.txt").write_text(
        (repo / "shared.txt").read_text().replace("line 45\n", "later unrelated\n")
    )
    (repo / "later.txt").write_text("keep later\n")
    current = _commit(repo, "later unrelated edit")
    # Neither the checked-out files nor the user's staged/untracked bytes may be used as the inverse index.
    (repo / "shared.txt").write_text("uncommitted user work\n")
    _git(repo, "add", "shared.txt")
    original_index = _git(repo, "write-tree")
    (repo / "untracked.txt").write_text("untracked\n")
    result = inverse.plan_incident_inverse(repo_root=repo, scope=scope, expected_head=current)
    assert isinstance(result, IOSuccess), result
    plan = unsafe_perform_io(result.unwrap())
    assert _git(repo, "show", plan.tree_sha + ":shared.txt").decode() == text.replace(
        "line 45\n", "later unrelated\n"
    )
    assert _git(repo, "show", plan.tree_sha + ":old.bin") == b"\x00before\xff"
    assert _git(repo, "show", plan.tree_sha + ":removed.txt") == b"restore me\n"
    assert _git(repo, "show", plan.tree_sha + ":later.txt") == b"keep later\n"
    assert _git(repo, "ls-tree", plan.tree_sha, "introduced.txt", "script.sh") == b""
    assert plan.expected_head == current and plan.inverse_patch
    assert _git(repo, "write-tree") == original_index
    assert (repo / "shared.txt").read_text() == "uncommitted user work\n"
    assert (repo / "untracked.txt").read_text() == "untracked\n"


def test_genuine_overlap_is_a_named_conflict_and_never_overwrites_later_change(history):
    repo, scope, _ = history
    (repo / "shared.txt").write_text(
        (repo / "shared.txt").read_text().replace("incident first", "later overlapping")
    )
    current = _commit(repo, "conflicting later edit")
    result = inverse.plan_incident_inverse(repo_root=repo, scope=scope, expected_head=current)
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "rollback-conflict"
    assert "later overlapping" in (repo / "shared.txt").read_text()


@pytest.mark.parametrize(
    "change",
    [
        {"landed_commits": ()},
        {"landed_trees": ()},
        {"landed_commits": ("a" * 40,)},
        {"landed_trees": ("a" * 40, "b" * 40)},
        {"patch_sha256": "0" * 64},
        {"changed_paths": ("shared.txt",)},
        {"before_sha": "--help"},
        {"merge_sha": "a" * 40},
        {"original_head_sha": "bad"},
        {"landed_commits": ("a" * 40, "b" * 40)},
        {"authority_sha256": "bad"},
    ],
)
def test_incomplete_or_unbound_scope_never_produces_an_inverse(history, change):
    repo, scope, _ = history
    result = inverse.plan_incident_inverse(
        repo_root=repo, scope=replace(scope, **change), expected_head=scope.merge_sha
    )
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "invalid-incident-scope"


def test_non_descendant_head_is_refused(history):
    repo, scope, _ = history
    result = inverse.plan_incident_inverse(
        repo_root=repo, scope=scope, expected_head=scope.before_sha
    )
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "invalid-incident-scope"


def test_successful_recovery_scoped_cas_and_restart_reads_exact_receipt(history):
    repo, scope, text = history
    forge = Forge(repo=repo, scope=scope)
    intent = _intent(scope)
    result = inverse.recover_incident_inverse(repo_root=repo, intent=intent, forge=forge)
    assert isinstance(result, IOSuccess), result
    assert unsafe_perform_io(result.unwrap()).status == "reverted"
    assert _git(repo, "show", "master:shared.txt").decode() == text
    assert len(forge.requests) == 1
    assert forge.requests[0].intent.action_id == intent.action_id
    assert "exact-action-1" in forge.requests[0].message
    # Recovery after a response loss has the same immutable operation, even when the source is unavailable.
    forge.available_scope = False
    replay = inverse.recover_incident_inverse(
        repo_root=repo / "missing", intent=intent, forge=forge
    )
    assert isinstance(replay, IOSuccess)
    assert unsafe_perform_io(replay.unwrap()).status == "recovered"
    assert unsafe_perform_io(replay.unwrap()).receipt == forge.receipt
    assert len(forge.requests) == 1


def test_expected_head_movement_recomputes_without_losing_new_commit(history):
    repo, scope, text = history
    forge = Forge(repo=repo, scope=scope)

    def move_once():
        forge.movement = None
        (repo / "concurrent.txt").write_text("concurrent work\n")
        _commit(repo, "concurrent master advance")

    forge.movement = move_once
    result = inverse.recover_incident_inverse(repo_root=repo, intent=_intent(scope), forge=forge)
    assert isinstance(result, IOSuccess), result
    assert len(forge.requests) == 2
    assert forge.requests[0].plan.expected_head != forge.requests[1].plan.expected_head
    assert _git(repo, "show", "master:shared.txt").decode() == text
    assert _git(repo, "show", "master:concurrent.txt") == b"concurrent work\n"


def test_repeated_definite_cas_movement_is_bounded(history):
    repo, scope, _ = history
    forge = Forge(repo=repo, scope=scope)
    forge.result = "head-moved"
    result = inverse.recover_incident_inverse(repo_root=repo, intent=_intent(scope), forge=forge)
    assert isinstance(result, IOSuccess)
    assert unsafe_perform_io(result.unwrap()).status == "pending"
    assert len(forge.requests) == 3


@pytest.mark.parametrize("status", ["unknown", "refused", "bogus"])
def test_ambiguous_or_refused_effect_does_not_retry(history, status):
    repo, scope, _ = history
    forge = Forge(repo=repo, scope=scope)
    forge.result = status
    result = inverse.recover_incident_inverse(repo_root=repo, intent=_intent(scope), forge=forge)
    assert isinstance(result, IOSuccess)
    assert unsafe_perform_io(result.unwrap()).status == "pending"
    assert len(forge.requests) == 1


def test_committed_response_without_exact_action_receipt_stays_pending(history):
    repo, scope, _ = history
    forge = Forge(repo=repo, scope=scope)
    forge.keep_receipt = False
    result = inverse.recover_incident_inverse(repo_root=repo, intent=_intent(scope), forge=forge)
    assert isinstance(result, IOSuccess)
    assert unsafe_perform_io(result.unwrap()).status == "pending"
    assert len(forge.requests) == 1


@pytest.mark.parametrize("keep_receipt", [True, False])
def test_conflict_is_owned_and_requires_durable_receipt(history, keep_receipt):
    repo, scope, _ = history
    (repo / "shared.txt").write_text(
        (repo / "shared.txt").read_text().replace("incident first", "overlap")
    )
    _commit(repo, "overlap")
    forge = Forge(repo=repo, scope=scope)
    forge.keep_receipt = keep_receipt
    result = inverse.recover_incident_inverse(repo_root=repo, intent=_intent(scope), forge=forge)
    assert isinstance(result, IOSuccess)
    outcome = unsafe_perform_io(result.unwrap())
    assert outcome.status == ("rollback-conflict" if keep_receipt else "pending")
    assert not forge.requests and len(forge.conflicts) == 1
    assert "controller-owner" in forge.conflicts[0].receipt
    assert forge.conflicts[0].intent.action_id == "exact-action-1"


@pytest.mark.parametrize(
    "change",
    [{"authority_sha256": "0" * 64}, {"repository": "other/repo"}, {"merge_sha": "a" * 40}],
)
def test_recovery_rejects_scope_not_bound_to_retained_observer_authority(history, change):
    repo, scope, _ = history
    forge = Forge(repo=repo, scope=replace(scope, **change))
    result = inverse.recover_incident_inverse(repo_root=repo, intent=_intent(scope), forge=forge)
    assert isinstance(result, IOFailure)
    assert unsafe_perform_io(result.failure()).code == "inverse-authority-refused"
    assert not forge.requests


@pytest.mark.parametrize("case", ["unauthorized", "scope-unavailable"])
def test_unavailable_or_unprovisioned_principal_never_publishes(history, case):
    repo, scope, _ = history
    forge = Forge(repo=repo, scope=scope)
    forge.authorized = case != "unauthorized"
    forge.available_scope = case != "scope-unavailable"
    result = inverse.recover_incident_inverse(repo_root=repo, intent=_intent(scope), forge=forge)
    assert isinstance(result, IOFailure)
    assert not forge.requests


def test_observer_callback_returns_receipt_only_after_exact_effect(history):
    repo, scope, _ = history
    forge = Forge(repo=repo, scope=scope)
    callback = inverse.observer_inverse_callback(repo_root=repo, forge=forge)
    assert callback(_intent(scope)) == forge.receipt
    assert forge.receipt and len(forge.requests) == 1
    forge.receipt = None
    forge.authorized = False
    assert callback(_intent(scope)) is None
