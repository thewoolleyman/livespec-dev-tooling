"""Merge-inherited workflow content is never counted as this change's workflow edit.

A factory refresh-repair merges the moved default branch into the publish
branch. When that branch changed `.github/workflows/` since the fork point (as
every fleet pin bump does), the merge STAGES those files relative to the branch
tip. The guard measured staged and on-disk work against HEAD, so it counted
content inherited from the base as the branch's own workflow edit. It refused
every such merge, even on a branch with no workflow change of its own (measured
on bd-ib-yuwftp run 01M6FTF5A9Y8, 2026-11-03). The same blind spot let a
declaration merged in from the base pass as "authored in this change".

These cases pin the corrected rule: pending work is measured against the merge
base the commit being prepared will have. Content the merge inherits from the
base is not an edit. Everything the branch itself changes is still in scope.
Both tiers keep their meaning: a `change=additive` claim is refused when the
BRANCH's own workflow diff modifies a line, and never because of a line the
base modified.

Fixtures mirror `test_check_no_workflow_edits.py`: a throwaway clone of a bare
`origin` whose default branch is `master`, the canonical guard body installed
under `dev-tooling/`, and a scrubbed child environment.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.install_worktree_pack import CANONICAL_NO_WORKFLOW_EDITS_BODY

__all__: list[str] = []

_GUARD_NAME = "check-no-workflow-edits.sh"
_DECLARATION = ".livespec-workflow-edit-exemption"
_WORKFLOW = Path(".github") / "workflows" / "ci.yml"
_PIN_WORKFLOW = Path(".github") / "workflows" / "bump-pin.yml"
_ADDITIVE_DECLARATION = (
    "work_item=livespec-dev-tooling-fy02\n"
    "reason=ratified add-only edit\n"
    "change=additive\n"
    "ci_runtime=no-significant-increase\n"
)
_PLAIN_DECLARATION = "work_item=livespec-dev-tooling-fy02\nreason=an earlier reviewed edit\n"
_GIT_ENV_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_LITERAL_PATHSPECS",
    "GIT_PREFIX",
)
_GUARD_ENV_VARS: tuple[str, ...] = ("GITHUB_ACTIONS", "LIVESPEC_BD_PATH")


def _git(*, args: list[str], cwd: Path) -> None:
    _ = subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


def _write(*, path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(text, encoding="utf-8")


def _commit_all(*, repo: Path, message: str) -> None:
    _git(args=["add", "--all"], cwd=repo)
    _git(args=["commit", "--quiet", "-m", message], cwd=repo)


def _clone_on_feature_branch(*, tmp_path: Path) -> Path:
    """A clone on `feature/wip`, cut from a base that carries two workflow files."""
    remote = tmp_path / "origin.git"
    remote.mkdir()
    _git(args=["init", "--bare", "--quiet", str(remote)], cwd=tmp_path)
    _git(args=["symbolic-ref", "HEAD", "refs/heads/master"], cwd=remote)
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(args=["init", "--quiet", "--initial-branch=master"], cwd=repo)
    _git(args=["config", "--local", "user.name", "Test User"], cwd=repo)
    _git(args=["config", "--local", "user.email", "test@example.com"], cwd=repo)
    _write(path=repo / _WORKFLOW, text="name: ci\non: push\njobs: {}\n")
    _write(path=repo / _PIN_WORKFLOW, text="name: bump\nenv:\n  PIN: v1.0.0\n")
    _write(path=repo / "README.md", text="# fixture\n")
    _write(path=repo / ".gitignore", text="/dev-tooling/\n")
    _commit_all(repo=repo, message="base")
    _git(args=["remote", "add", "origin", str(remote)], cwd=repo)
    _git(args=["push", "--quiet", "-u", "origin", "master"], cwd=repo)
    _git(args=["remote", "set-head", "origin", "--auto"], cwd=repo)
    _git(args=["checkout", "--quiet", "-b", "feature/wip"], cwd=repo)
    script = repo / "dev-tooling" / _GUARD_NAME
    _write(path=script, text=CANONICAL_NO_WORKFLOW_EDITS_BODY)
    script.chmod(0o755)
    return repo


def _advance_master(*, repo: Path, declaration: str | None = None) -> None:
    """Land a pin bump on `origin/master` that MODIFIES a workflow line, as the fleet's bots do."""
    _git(args=["checkout", "--quiet", "master"], cwd=repo)
    _write(path=repo / _PIN_WORKFLOW, text="name: bump\nenv:\n  PIN: v1.1.0\n")
    if declaration is not None:
        _write(path=repo / _DECLARATION, text=declaration)
    _commit_all(repo=repo, message="chore(deps): bump pin")
    _git(args=["push", "--quiet", "origin", "master"], cwd=repo)
    _git(args=["checkout", "--quiet", "feature/wip"], cwd=repo)


def _start_merge_of_master(*, repo: Path) -> None:
    """The refresh-repair moment: origin/master merged and staged, not yet committed."""
    _git(args=["merge", "--quiet", "--no-ff", "--no-commit", "origin/master"], cwd=repo)


def _run_guard(*, repo: Path) -> subprocess.CompletedProcess[str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in _GIT_ENV_VARS
        and key not in _GUARD_ENV_VARS
        and key != "COVERAGE_PROCESS_START"
        and not key.startswith("COV_CORE_")
    }
    return subprocess.run(
        ["bash", f"dev-tooling/{_GUARD_NAME}"],
        cwd=str(repo),
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_an_in_progress_merge_of_master_with_no_workflow_change_of_its_own_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Master's staged pin bump is inherited content, not the branch's workflow edit."""
    monkeypatch.chdir(tmp_path)
    repo = _clone_on_feature_branch(tmp_path=tmp_path)
    _write(path=repo / "src.txt", text="the branch's own change\n")
    _commit_all(repo=repo, message="ordinary")
    _advance_master(repo=repo)
    _start_merge_of_master(repo=repo)

    completed = _run_guard(repo=repo)

    assert (completed.returncode, completed.stderr) == (0, "")


def test_a_committed_merge_of_master_with_no_workflow_change_of_its_own_passes(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The control: once the merge is committed, the inherited content is still not an edit."""
    monkeypatch.chdir(tmp_path)
    repo = _clone_on_feature_branch(tmp_path=tmp_path)
    _advance_master(repo=repo)
    _start_merge_of_master(repo=repo)
    _git(args=["commit", "--quiet", "--no-edit"], cwd=repo)

    completed = _run_guard(repo=repo)

    assert (completed.returncode, completed.stderr) == (0, "")


def test_a_merge_still_refuses_the_branch_s_own_undeclared_workflow_edit(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inheriting master's content does not hide what the branch itself changed."""
    monkeypatch.chdir(tmp_path)
    repo = _clone_on_feature_branch(tmp_path=tmp_path)
    workflow = repo / _WORKFLOW
    _write(path=workflow, text=workflow.read_text(encoding="utf-8") + "# the branch's edit\n")
    _commit_all(repo=repo, message="edit workflow")
    _advance_master(repo=repo)
    _start_merge_of_master(repo=repo)

    completed = _run_guard(repo=repo)

    facts = [
        completed.returncode == 1,
        f"  {_WORKFLOW}" in completed.stderr,
        f"  {_PIN_WORKFLOW}" not in completed.stderr,
    ]
    assert all(facts), completed.stderr


def test_a_declaration_merged_in_from_master_is_not_authored_by_this_change(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An exemption that master carries for another change cannot authorize this branch's edit."""
    monkeypatch.chdir(tmp_path)
    repo = _clone_on_feature_branch(tmp_path=tmp_path)
    workflow = repo / _WORKFLOW
    _write(path=workflow, text=workflow.read_text(encoding="utf-8") + "# the branch's edit\n")
    _commit_all(repo=repo, message="edit workflow")
    _advance_master(repo=repo, declaration=_PLAIN_DECLARATION)
    _start_merge_of_master(repo=repo)

    completed = _run_guard(repo=repo)

    facts = [
        completed.returncode == 1,
        "not authored by this change" in completed.stderr,
    ]
    assert all(facts), completed.stderr


def test_an_add_only_branch_edit_stays_additive_across_a_merge_that_modified_master_s_lines(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A line master modified is inherited, so it never refuses the branch's additive claim."""
    monkeypatch.chdir(tmp_path)
    repo = _clone_on_feature_branch(tmp_path=tmp_path)
    workflow = repo / _WORKFLOW
    _write(path=workflow, text=workflow.read_text(encoding="utf-8") + "# an added line\n")
    _write(path=repo / _DECLARATION, text=_ADDITIVE_DECLARATION)
    _commit_all(repo=repo, message="additive workflow edit")
    _advance_master(repo=repo)
    _start_merge_of_master(repo=repo)

    completed = _run_guard(repo=repo)

    facts = [
        completed.returncode == 0,
        "additive tier" in completed.stderr,
        "PIN: v1.0.0" not in completed.stderr,
    ]
    assert all(facts), completed.stderr


def test_a_false_additive_claim_is_still_refused_across_a_merge_naming_only_the_branch_s_line(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The branch's own modified line refuses `change=additive`; master's modified line is not named."""
    monkeypatch.chdir(tmp_path)
    repo = _clone_on_feature_branch(tmp_path=tmp_path)
    workflow = repo / _WORKFLOW
    _write(
        path=workflow,
        text=workflow.read_text(encoding="utf-8").replace("on: push\n", "on: pull_request\n"),
    )
    _write(path=repo / _DECLARATION, text=_ADDITIVE_DECLARATION)
    _commit_all(repo=repo, message="modify workflow under an additive claim")
    _advance_master(repo=repo)
    _start_merge_of_master(repo=repo)

    completed = _run_guard(repo=repo)

    facts = [
        completed.returncode == 1,
        "claims change=additive" in completed.stderr,
        "-on: push" in completed.stderr,
        "PIN: v1.0.0" not in completed.stderr,
    ]
    assert all(facts), completed.stderr
