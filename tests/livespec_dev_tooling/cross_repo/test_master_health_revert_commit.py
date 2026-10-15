"""Tests for `master_health_revert_commit` — the commit the revert step requests.

Plan `red-master-self-healing` (epic `livespec-dev-tooling-zcp5vb`), work-item
`livespec-dev-tooling-7n2itg`.

WHY THIS MODULE EXISTS AT ALL is a negative measurement, and nothing asserted
here is legible without it. `docs/master-health-reconciler.md` section "The
negative verification: a web-flow revert here is UNSIGNED" records that every
revert commit GitHub minted for orchestrator PR #2918 reports
`verification.verified: false` with reason `unsigned`, as do 60 of 60 surveyed
`master` commits across two fleet repositories. The exemption in
`docs/server-side-revert-exemption.md` requires BOTH a signature verifying
against the pinned web-flow trust root AND byte-identity with the reverted
commit's parent, and it FAILS CLOSED — so an unsigned revert of a culprit that
touched product impl `.py` is convicted by `check-red-green-replay`'s
commit-range gate, and revert-by-default heals nothing for the commonest
regression there is.

NEITHER HALF OF THE EXEMPTION IS WEAKENED HERE, and that is the whole point of
the approach: the reconciler stops asking the forge to AUTHOR its revert and
asks the forge to COMMIT a revert the reconciler itself described. The gate
leg of that join — the described commit admitted when signed, refused when not
— lives beside the exemption it exercises, in
`tests/livespec_dev_tooling/checks/test_red_green_replay_revert.py`.
"""

from __future__ import annotations

import ast
import base64
import os
import subprocess
from dataclasses import dataclass, fields
from pathlib import Path

import pytest

# The culprit-path record is reached through the MODULE rather than imported by
# name, and deliberately so: a top-level `from ... import CulpritPath` turns the
# Red leg of the slice that introduces it into a COLLECTION error, which proves
# the name is absent rather than that the behavior is unimplemented. Same reason
# the sibling exemption test keeps its failure type behind `TYPE_CHECKING`.
from livespec_dev_tooling.cross_repo import master_health_revert_commit
from livespec_dev_tooling.cross_repo.master_health_revert_commit import (
    FORGE_COMMIT_MUTATION,
    REVERT_COMMIT_CREDENTIAL,
    RevertCommitRequest,
    revert_commit_request,
)

_PACKAGE = Path(__file__).resolve().parents[3] / "livespec_dev_tooling" / "cross_repo"

# The 2026-10-14 incident's culprit — orchestrator PR #2917's rebase-merge —
# spelled as a full object name, because the lookup line the exemption reads out
# of the commit message is matched against 7-to-40 hex characters and a short
# sha would prove the easy half of that.
_CULPRIT_SHA = "35fea321d4e9c7b5a1f08632d9c4ee17ab095d3c"
_SHORT_CULPRIT = "35fea321d4e9"
# The branch head the revert branch is cut from, and what the mutation is told
# to expect there.
_HEAD_OID = "372f5d3dcb1a4e07f9d2b6538ac1e04d7fb9e215"

# Vars git sets when invoking hooks; inherited by every child and would redirect
# the fixture repo's git calls at the SURROUNDING repository. This suite runs
# UNDER those hooks during the Red-Green-Replay ritual, so scrubbing them is not
# defensive tidiness — without it the fixture reads this checkout.
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

# The three shapes a culprit's diff can take, each with a different correct
# revert, which is why one fixture carries all three: a builder that handled
# only the modified case would pass a fixture holding only the modified case.
_MODIFIED_PATH = "livespec_dev_tooling/supervisor_tick.py"
_PRE_MERGE_BODY = '"""Supervisor tick."""\n\n\ndef run_tick() -> int:\n    return 0\n'
_CULPRIT_BODY = '"""Supervisor tick."""\n\n\ndef run_tick() -> int:\n    return 1\n'
_DELETED_PATH = "livespec_dev_tooling/retired_helper.py"
_DELETED_BODY = '"""Deleted by the culprit; the revert has to bring it back."""\n'
_CREATED_PATH = "livespec_dev_tooling/introduced_helper.py"
_CREATED_BODY = '"""Created by the culprit; the revert has to DELETE it."""\n'
# A non-UTF-8 payload, because the request restores BYTES. A builder that
# round-tripped contents through `str` would corrupt this and still pass every
# text-only fixture.
_BINARY_PATH = "livespec_dev_tooling/fixtures/tick.bin"
_PRE_MERGE_BINARY = b"\x00\x01\xfe\xff pre-merge\n"
_CULPRIT_BINARY = b"\x00\x01\xfe\xff culprit\n"


@dataclass(frozen=True, kw_only=True)
class _CulpritRepo:
    """A recorded forge state: one culprit commit, and the paths it changed."""

    path: Path
    culprit_sha: str
    changed_paths: tuple[str, ...]


@pytest.fixture(autouse=True)
def _scrub_git_hook_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)


def _git(*, cwd: Path, args: list[str]) -> subprocess.CompletedProcess[bytes]:
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, check=False, env=env)


def _culprit_repo(*, tmp_path: Path) -> _CulpritRepo:
    """A branch whose head merge modified, deleted and created product paths.

    Built as a real repository rather than a hand-written record because the
    claim under test is about BYTES: the recording below reads the culprit's
    parent out of git exactly as the reusable workflow reads it out of the
    forge, so nothing in the test invents the state it then checks.
    """
    repo = tmp_path / "fleet-member"
    for path, body in ((_MODIFIED_PATH, _PRE_MERGE_BODY), (_DELETED_PATH, _DELETED_BODY)):
        (repo / path).parent.mkdir(parents=True, exist_ok=True)
        (repo / path).write_text(body, encoding="utf-8")
    (repo / _BINARY_PATH).parent.mkdir(parents=True, exist_ok=True)
    (repo / _BINARY_PATH).write_bytes(_PRE_MERGE_BINARY)
    _ = _git(cwd=repo.parent, args=["init", "-q", str(repo)])
    for key, value in (("user.email", "test@example.com"), ("user.name", "Test")):
        _ = _git(cwd=repo, args=["config", key, value])
    _ = _git(cwd=repo, args=["add", "-A"])
    _ = _git(cwd=repo, args=["commit", "-qm", "chore: the green parent"])

    (repo / _MODIFIED_PATH).write_text(_CULPRIT_BODY, encoding="utf-8")
    (repo / _DELETED_PATH).unlink()
    (repo / _CREATED_PATH).write_text(_CREATED_BODY, encoding="utf-8")
    (repo / _BINARY_PATH).write_bytes(_CULPRIT_BINARY)
    _ = _git(cwd=repo, args=["add", "-A"])
    _ = _git(cwd=repo, args=["commit", "-qm", "feat: the culprit merge"])
    culprit = _git(cwd=repo, args=["rev-parse", "HEAD"]).stdout.decode().strip()
    listed = _git(
        cwd=repo,
        args=["diff-tree", "--no-commit-id", "--name-only", "-r", culprit],
    )
    return _CulpritRepo(
        path=repo,
        culprit_sha=culprit,
        changed_paths=tuple(sorted(listed.stdout.decode().split())),
    )


def _blob_at(*, repo: _CulpritRepo, revision: str, path: str) -> bytes | None:
    """The bytes `path` held at `revision`, or `None` when it held nothing there."""
    shown = _git(cwd=repo.path, args=["show", f"{revision}:{path}"])
    return shown.stdout if shown.returncode == 0 else None


def _recorded_culprit_paths(
    *, repo: _CulpritRepo
) -> tuple[master_health_revert_commit.CulpritPath, ...]:
    """The record the workflow gathers once the step says to open a revert.

    One entry per path the culprit changed, carrying the bytes the culprit's
    PARENT held there — and `None` where the parent held nothing, which is the
    only way a path the culprit CREATED is told apart from one it changed.
    """
    return tuple(
        master_health_revert_commit.CulpritPath(
            path=path,
            parent_contents=_blob_at(repo=repo, revision=f"{repo.culprit_sha}^", path=path),
        )
        for path in repo.changed_paths
    )


def _apply_file_changes(*, request: RevertCommitRequest, root: Path) -> None:
    """Materialize the mutation's `fileChanges` the way the forge would commit them."""
    for addition in request.additions:
        target = root / addition.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(base64.b64decode(addition.contents))
    for deleted in request.deletions:
        (root / deleted).unlink()


def _declared_mutations() -> set[str]:
    """Every forge mutation name a `master_health_*` module DECLARES as a constant.

    Walked as SOURCE over a GLOB — the shape `test_master_health_state` already
    uses for the no-LLM closure — so a sibling slice added later inherits this
    assertion without anyone remembering to extend this file.

    Prose may still NAME `revertPullRequest`, the API this step replaces: a
    design record that cannot name what it rejected is not a record. A DECLARED
    mutation constant may not be it.
    """
    declared: set[str] = set()
    for module in sorted(_PACKAGE.glob("master_health_*.py")):
        for node in ast.parse(module.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
                continue
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if any(name.endswith("_MUTATION") for name in names):
                declared.add(str(node.value.value))
    return declared


def test_the_revert_step_asks_the_forge_to_commit_a_revert_the_reconciler_described() -> None:
    """The operation and the credential, both carried as DATA the transport posts.

    `createCommitOnBranch` is asserted as a LITERAL rather than against the
    module's own constant: a test comparing the request to the constant that
    produced it would pass for any value, including the revert-PR mutation this
    step exists to stop calling.

    The credential is carried for the same reason `ReconcileStep.auto_merge_held`
    is — so a transport reading the request cannot authenticate by omission.
    `GITHUB_TOKEN` is the specific omission that matters: a commit it authors
    triggers no downstream CI, so the revert's own CI would never speak and the
    release step would wait forever on a verdict nothing was going to produce.

    The `This reverts commit` line is asserted as a WHOLE LINE because that is
    what the exemption's lookup is anchored to; a sha mentioned mid-sentence
    names no ancestor to compare against.

    The culprit record is deliberately EMPTY here: the subject is the operation
    and the credential the mutation is posted with, which a culprit's diff has
    no bearing on. What the file changes restore is the next test's subject, and
    it reads a real repository rather than a literal to say it.
    """
    request = revert_commit_request(
        culprit_sha=_CULPRIT_SHA,
        culprit_paths=(),
        target_branch="master",
        expected_head_oid=_HEAD_OID,
    )

    assert request.mutation == "createCommitOnBranch"
    assert request.mutation == FORGE_COMMIT_MUTATION
    assert request.credential == REVERT_COMMIT_CREDENTIAL == "github-app-installation-token"
    assert request.branch == f"master-health/revert-{_SHORT_CULPRIT}"
    assert request.expected_head_oid == _HEAD_OID
    assert f"This reverts commit {_CULPRIT_SHA}." in request.body.splitlines()
    assert _SHORT_CULPRIT in request.headline


def test_the_requested_commit_is_byte_identical_to_the_culprits_parent(*, tmp_path: Path) -> None:
    """The exemption's second half, asked of the request rather than of a revert.

    The field assertion comes FIRST and is not ceremony: a request carrying no
    `fileChanges` at all restores no bytes, so that is the genuine failure the
    slice introducing them starts from, and putting it first keeps the Red an
    assertion rather than an attribute error further down.

    The verdict itself is `git diff --quiet <culprit>^ -- <paths>` against the
    materialized request — the SAME predicate `_red_green_replay_revert`'s
    `_restores_pre_revert_bytes` runs. Three shapes are proven at once because
    each has a different correct revert: a modified path is restored to the
    parent's bytes, a path the culprit DELETED is restored as an addition, and a
    path the culprit CREATED is DELETED rather than emptied — an empty file
    would leave a module behind that no commit ever earned evidence for and
    would differ from the parent at that path.
    """
    declared = {field.name for field in fields(RevertCommitRequest)}
    assert {
        "additions",
        "deletions",
    } <= declared, "the request carries no file changes, so it can restore no bytes at all"

    repo = _culprit_repo(tmp_path=tmp_path)
    request = revert_commit_request(
        culprit_sha=repo.culprit_sha,
        culprit_paths=_recorded_culprit_paths(repo=repo),
        target_branch="master",
        expected_head_oid=repo.culprit_sha,
    )
    _apply_file_changes(request=request, root=repo.path)
    _ = _git(cwd=repo.path, args=["add", "-A"])

    assert request.deletions == (_CREATED_PATH,)
    assert {addition.path for addition in request.additions} == {
        _BINARY_PATH,
        _DELETED_PATH,
        _MODIFIED_PATH,
    }
    restored = _git(
        cwd=repo.path,
        args=[
            "diff",
            "--cached",
            "--quiet",
            f"{repo.culprit_sha}^",
            "--",
            *repo.changed_paths,
        ],
    )
    assert restored.returncode == 0, (
        "the requested revert commit is not byte-identical to the culprit's parent at "
        f"{repo.changed_paths}: {restored.stdout.decode()}"
    )


def test_the_decision_package_declares_one_forge_mutation_and_it_builds_a_commit() -> None:
    """`createCommitOnBranch` is the ONLY forge mutation this package asks for.

    The closure, not the constant: a later slice that reintroduced
    `revertPullRequest` as a declared mutation fails here rather than at a red
    master nobody can heal, because the commits that API mints are unsigned and
    the exemption fails closed on every one of them.
    """
    assert _declared_mutations() == {"createCommitOnBranch"}
