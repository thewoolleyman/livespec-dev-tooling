"""Delegated pre-commit aggregate decisions."""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).parents[2] / "livespec_dev_tooling" / "pre_commit_delegate.py"

_REPO_ROOT = Path(__file__).parents[2]

__all__: list[str] = []


def _module() -> object:
    """Import the seam only after the Red assertion has run."""
    assert _MODULE_PATH.is_file()
    return importlib.import_module("livespec_dev_tooling.pre_commit_delegate")


def test_an_absent_pre_commit_opt_in_runs_locally(*, tmp_path: Path) -> None:
    """A repository must explicitly opt in before its pre-commit gate delegates."""
    module = _module()

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.reason == "delegated_pre_commit is not enabled"


def test_an_unreadable_gates_kubeconfig_runs_the_pre_commit_gate_locally(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An opted-in repository without the host credential retains its local gate."""
    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: False)

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.reason == "gates kubeconfig is not readable"


def test_a_credentialed_pre_commit_delegates_the_staged_tree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Job receives a commit wrapping the index tree and its check recipe."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GATE_PASSED, GateVerdict

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )
    request = GateRunRequest(
        repo_root=tmp_path,
        mirror_url="mirror",
        manifest="manifest",
        gate_ref="refs/gates/tree",
    )
    captured: dict[str, object] = {}

    def build(**kwargs: object) -> object:
        captured.update(kwargs)
        return Success(request)

    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "gate_remote_request", build)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "b" * 40)
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(
            state=GATE_PASSED,
            detail="the Job passed",
            token_written=True,
            job_name="gate-pre-commit-1",
            tree_hash="a" * 40,
        ),
    )

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert captured["tree_hash"] == "a" * 40
    assert captured["check_suite"] == ("check-pre-commit-gated-tree",)
    assert verdict.local is False
    assert verdict.job_name == "gate-pre-commit-1"
    assert verdict.tree_hash == "a" * 40
    assert verdict.exit_status == 0


@pytest.mark.parametrize(
    "remote",
    [
        {"state": "NO_VERDICT", "tree_hash": None},
        {"state": "PASSED", "tree_hash": "b" * 40},
    ],
)
def test_an_absent_or_wrong_tree_cluster_outcome_gates_locally(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, remote: dict[str, str | None]
) -> None:
    """Only a verdict naming the staged tree may keep the local aggregate out."""
    from returns.result import Success

    from livespec_dev_tooling.gate_remote_client import GateRunRequest
    from livespec_dev_tooling.gate_remote_verdict import GateVerdict

    module = _module()
    _ = (tmp_path / "pyproject.toml").write_text(
        "[tool.livespec_dev_tooling]\ndelegated_pre_commit = true\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "gates_kubeconfig_readable", lambda: True)
    monkeypatch.setattr(module, "_staged_tree_hash", lambda **_kwargs: "a" * 40)
    monkeypatch.setattr(module, "_staged_commit", lambda **_kwargs: "b" * 40)
    monkeypatch.setattr(module, "resolve_renderer", lambda **_kwargs: Path("renderer"))
    monkeypatch.setattr(
        module,
        "gate_remote_request",
        lambda **_kwargs: Success(
            GateRunRequest(
                repo_root=tmp_path,
                mirror_url="mirror",
                manifest="manifest",
                gate_ref="refs/gates/tree",
            )
        ),
    )
    monkeypatch.setattr(
        module,
        "run_gated_push",
        lambda **_kwargs: GateVerdict(
            state=remote["state"],
            detail="the cluster could not provide the staged-tree verdict",
            token_written=False,
            tree_hash=remote["tree_hash"],
        ),
    )

    verdict = module.run_pre_commit(repo_root=tmp_path)

    assert verdict.local is True
    assert verdict.exit_status is None
    assert verdict.tree_hash == "a" * 40


def _git(*, cwd: Path, args: list[str]) -> str:
    """Run one git command in a throwaway repository and return its stdout."""
    env = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("GIT_") or key == "GIT_CONFIG_NOSYSTEM"
    }
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t.invalid", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def test_the_gated_tree_recipe_restores_the_staged_index_before_the_aggregate(
    *, tmp_path: Path
) -> None:
    """The Job's clean checkout must present the aggregate the hook's staged-tree state.

    The gate Job checks out the staged-tree commit, where `git diff --cached` is empty, so
    the hook's empty-staged short-circuit would pass without running a member. The gated-tree
    recipe rewinds HEAD to the commit's parent while keeping the index and working tree, so
    the unchanged aggregate sees the same staged files and the same `HEAD` the hook saw.
    """
    scripts = tmp_path / "scripts" / "just"
    scripts.mkdir(parents=True)
    recipe = _REPO_ROOT / "scripts" / "just" / "check-pre-commit-gated-tree.sh"
    assert recipe.is_file()
    _ = shutil.copy(recipe, scripts / recipe.name)
    seen = tmp_path / "seen.txt"
    stub = scripts / "check-pre-commit.sh"
    _ = stub.write_text(
        "#!/usr/bin/env bash\n"
        f'{{ git rev-parse HEAD; git diff --cached --name-only; }} > "{seen}"\n'
        "exit 7\n",
        encoding="utf-8",
    )
    stub.chmod(0o755)
    _git(cwd=tmp_path, args=["init", "-q", "-b", "main"])
    _ = (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "base.txt", "scripts"])
    _git(cwd=tmp_path, args=["commit", "-q", "-m", "base"])
    parent = _git(cwd=tmp_path, args=["rev-parse", "HEAD"])
    _ = (tmp_path / "staged.txt").write_text("staged\n", encoding="utf-8")
    _git(cwd=tmp_path, args=["add", "staged.txt"])
    tree = _git(cwd=tmp_path, args=["write-tree"])
    commit = _git(cwd=tmp_path, args=["commit-tree", tree, "-p", parent, "-m", "staged"])
    _git(cwd=tmp_path, args=["reset", "-q", "--hard", commit])

    ran = subprocess.run(
        ["bash", str(scripts / recipe.name)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert ran.returncode == 7
    assert seen.read_text(encoding="utf-8").split() == [parent, "staged.txt"]
    assert _git(cwd=tmp_path, args=["write-tree"]) == tree
