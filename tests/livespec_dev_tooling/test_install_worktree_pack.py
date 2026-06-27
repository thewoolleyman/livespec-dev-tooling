"""Outside-in test for `livespec_dev_tooling/install_worktree_pack.py`.

The installer writes the two canonical worktree-discipline scripts —
`worktree-lib.sh` and `branch-protection.sh` — into a governed repo's
`dev-tooling/` directory, each executable, resolving the target via
`git rev-parse --show-toplevel` so the pack lands at the work-tree root of
wherever the installer runs (the scripts are TRACKED repo files, committed
through the normal worktree → PR flow). This mirrors
`install_commit_refuse_hooks`, whose body ships as a wheel-safe module-level
string constant rather than a data-file resource.

The installer is exercised IN-PROCESS (`main()` with `monkeypatch.chdir`) —
no Python subprocess spawn (this test is not on the
`subprocess_spawn_allowlist`); the only subprocesses are `git` for repo
setup.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.install_worktree_pack import (
    CANONICAL_BRANCH_PROTECTION_BODY,
    CANONICAL_WORKTREE_LIB_BODY,
    main,
)

__all__: list[str] = []


# The pack's installed basenames paired with their canonical bodies.
_PACK_EXPECTED: tuple[tuple[str, str], ...] = (
    ("worktree-lib.sh", CANONICAL_WORKTREE_LIB_BODY),
    ("branch-protection.sh", CANONICAL_BRANCH_PROTECTION_BODY),
)

# git sets these in a hook's environment when it fires inside a worktree;
# when this suite runs under a lefthook pre-commit they also leak in from
# the surrounding repo. Scrubbing them confines every git invocation to the
# tmp_path fixture.
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


def _scrub_git_env(*, monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove every GIT_* passthrough var from the process environment."""
    for var in _GIT_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _run_git(*, args: list[str], cwd: Path) -> None:
    """Run a git command in `cwd`, raising on failure."""
    _ = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(*, repo: Path) -> None:
    """Initialize a git repo at `repo` with a local identity."""
    repo.mkdir(parents=True, exist_ok=True)
    _run_git(args=["init", "--quiet"], cwd=repo)
    _run_git(args=["config", "--local", "user.name", "Test User"], cwd=repo)
    _run_git(args=["config", "--local", "user.email", "test@example.com"], cwd=repo)


def _init_primary_with_worktree(*, tmp_path: Path) -> tuple[Path, Path]:
    """Create a primary checkout plus one linked worktree; return both paths."""
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    seed = primary / "seed.md"
    _ = seed.write_text("# seed\n", encoding="utf-8")
    _run_git(args=["add", "seed.md"], cwd=primary)
    _run_git(args=["commit", "--quiet", "-m", "fixture commit"], cwd=primary)
    _run_git(args=["branch", "feature/wip"], cwd=primary)
    worktree = tmp_path / "wt-feature"
    _run_git(args=["worktree", "add", str(worktree), "feature/wip"], cwd=primary)
    return primary, worktree


def test_main_installs_both_pack_scripts(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` writes both canonical scripts to `dev-tooling/`, executable and byte-identical."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    rc = main()

    assert rc == 0
    pack_dir = primary / "dev-tooling"
    for name, body in _PACK_EXPECTED:
        script = pack_dir / name
        assert script.is_file(), f"{name} not installed"
        assert os.access(script, os.X_OK), f"{name} not executable"
        assert script.read_text(encoding="utf-8") == body


def test_main_from_worktree_installs_into_that_worktree_root(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invoked from a linked worktree, the pack lands at THAT worktree's `dev-tooling/`.

    Unlike the commit-refuse hooks (which target the shared common dir), the
    pack scripts are tracked files, so `git rev-parse --show-toplevel`
    resolves to the current worktree's own root — the install lands there,
    not in the primary checkout.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary, worktree = _init_primary_with_worktree(tmp_path=tmp_path)
    monkeypatch.chdir(worktree)

    rc = main()

    assert rc == 0
    for name, body in _PACK_EXPECTED:
        installed = worktree / "dev-tooling" / name
        assert installed.is_file(), f"{name} not installed into worktree root"
        assert installed.read_text(encoding="utf-8") == body
        # The primary checkout is untouched (the pack is per-checkout tracked state).
        assert not (primary / "dev-tooling" / name).exists()


def test_main_is_idempotent(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-running the installer overwrites with the identical canonical bodies."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    assert main() == 0
    first = (primary / "dev-tooling" / "worktree-lib.sh").read_text(encoding="utf-8")
    assert main() == 0
    second = (primary / "dev-tooling" / "worktree-lib.sh").read_text(encoding="utf-8")

    assert first == second == CANONICAL_WORKTREE_LIB_BODY


def test_canonical_worktree_lib_body_carries_distinctive_markers() -> None:
    """Lock distinctive structural markers of the worktree-lib body.

    Guards against silent corruption or truncation of the embedded
    constant: the header, the load-bearing primary-vs-linked detection, and
    each of the four lifecycle verbs MUST be present.
    """
    assert "worktree-lib.sh — portable, ecosystem-neutral" in CANONICAL_WORKTREE_LIB_BODY
    assert "git rev-parse --git-common-dir" in CANONICAL_WORKTREE_LIB_BODY
    assert "worktree_is_primary()" in CANONICAL_WORKTREE_LIB_BODY
    assert "worktree_create()" in CANONICAL_WORKTREE_LIB_BODY
    assert "worktree_hydrate()" in CANONICAL_WORKTREE_LIB_BODY
    assert "worktree_land()" in CANONICAL_WORKTREE_LIB_BODY
    assert CANONICAL_WORKTREE_LIB_BODY.endswith("\n")


def test_canonical_branch_protection_body_carries_distinctive_markers() -> None:
    """Lock distinctive structural markers of the branch-protection body."""
    assert "branch-protection.sh — the SERVER-SIDE mirror" in CANONICAL_BRANCH_PROTECTION_BODY
    assert "LIVESPEC_BRANCH_PROTECTION_CHECK" in CANONICAL_BRANCH_PROTECTION_BODY
    assert CANONICAL_BRANCH_PROTECTION_BODY.endswith("\n")
