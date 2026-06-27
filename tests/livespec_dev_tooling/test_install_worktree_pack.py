"""Outside-in test for `livespec_dev_tooling/install_worktree_pack.py`.

The installer writes the canonical worktree-discipline pack — the two
executable scripts `worktree-lib.sh` and `branch-protection.sh` plus the
non-executable justfile fragment `worktree.just` — into a governed repo's
`dev-tooling/` directory, resolving the target via `git rev-parse
--show-toplevel` so the pack lands at the work-tree root of wherever the
installer runs (the pack files are TRACKED repo files, committed through the
normal worktree → PR flow). The `.sh` scripts are made executable (the
`worktree-*` recipes invoke them directly); `worktree.just` is `import`ed by
the consumer root justfile, never run directly, so it is installed
non-executable. The canonical bodies ship as wheel-safe package-data
resources read once at import.

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


def test_main_installs_worktree_just_fragment(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` writes `dev-tooling/worktree.just` NON-executable, carrying the four recipes.

    Unlike the two `.sh` scripts, the `worktree.just` recipe fragment is
    `import`ed by the consumer root justfile — never run directly — so it is
    installed without the executable bit. Its body carries the four canonical
    `worktree-*` lifecycle recipe stanzas, each a one-line pass-through onto
    `./dev-tooling/worktree-lib.sh`.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    rc = main()

    assert rc == 0
    fragment = primary / "dev-tooling" / "worktree.just"
    assert fragment.is_file(), "worktree.just not installed"
    assert not os.access(fragment, os.X_OK), "worktree.just must not be executable"
    content = fragment.read_text(encoding="utf-8")
    for recipe in ("worktree-create", "worktree-hydrate", "worktree-land", "worktree-reap"):
        assert recipe in content, f"{recipe} recipe stanza missing from worktree.just"
    assert "./dev-tooling/worktree-lib.sh create" in content


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


def test_canonical_worktree_lib_uses_from_package_hook_phrasing() -> None:
    """The canonical worktree-lib body carries the POST-CONVERGENCE from-package phrasing.

    The fleet's two pre-existing copies had drifted: core's template
    (blob cd21441) still describes the commit-refuse hook as the vendored
    `git-hook-wrapper.sh`, while `livespec-orchestrator-git-jsonl`'s copy
    (blob 94b8034) describes it as "installed from the shared
    livespec_dev_tooling package" — the correct phrasing now that the hook
    installs from-package and the vendored wrapper is retired. The canonical
    package-data body MUST be the from-package one, so it never references a
    file the convergence deletes. This locks that choice against a future
    re-sync from the (still-lagging) core template.
    """
    assert "installed from the shared" in CANONICAL_WORKTREE_LIB_BODY
    assert "livespec_dev_tooling package" in CANONICAL_WORKTREE_LIB_BODY
    assert "git-hook-wrapper.sh" not in CANONICAL_WORKTREE_LIB_BODY


def test_canonical_branch_protection_body_carries_distinctive_markers() -> None:
    """Lock distinctive structural markers of the branch-protection body."""
    assert "branch-protection.sh — the SERVER-SIDE mirror" in CANONICAL_BRANCH_PROTECTION_BODY
    assert "LIVESPEC_BRANCH_PROTECTION_CHECK" in CANONICAL_BRANCH_PROTECTION_BODY
    assert CANONICAL_BRANCH_PROTECTION_BODY.endswith("\n")
