"""Outside-in test for `livespec_dev_tooling/checks/primary_checkout_bare_flag_set.py`.

Per `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary
invariants" → §"`primary-checkout-bare-flag-set`": every
livespec-governed primary checkout MUST have `core.bare = true`
set in its `.git/config`. The check fires `fail` (exit 4) when
the value is absent OR explicitly set to `false`; the invariant
MUST NOT distinguish between the two cases.

The check applies to the PRIMARY checkout only. Secondary
worktrees carry a `.git` file pointing back to the primary; the
check reads `core.bare` via `git config --get core.bare`, which
resolves to the common config (the primary's `.git/config`) by
git's design (`core.bare` is not in the worktree-config-allowed
key set).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = _REPO_ROOT / "livespec_dev_tooling" / "checks" / "primary_checkout_bare_flag_set.py"


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


def _scrubbed_env(*, path_override: str | None = None) -> dict[str, str]:
    """Return a copy of `os.environ` with GIT_* vars removed.

    When tests run as part of a git pre-commit hook (lefthook), git
    sets GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE pointing at the
    surrounding repo. Scrubbing the vars confines git to the
    tmp_path fixture's `.git` directory.
    """
    env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_PASSTHROUGH_VARS}
    if path_override is not None:
        env["PATH"] = path_override
    return env


def _run_check(
    *,
    cwd: Path,
    path_override: str | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run the check script with cwd set to a path.

    Preserves the parent env (incl. COVERAGE_PROCESS_START) so
    pytest-cov's subprocess auto-init works; overrides only PATH
    when `path_override` is given.
    """
    return subprocess.run(
        [sys.executable, str(_CHECK)],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=_scrubbed_env(path_override=path_override),
    )


def _git_init(*, cwd: Path) -> None:
    """Initialize a git repo at `cwd` with local user.name/user.email."""
    env = _scrubbed_env()
    _ = subprocess.run(
        ["git", "init", "--quiet"],
        cwd=str(cwd),
        check=True,
        env=env,
    )
    _ = subprocess.run(
        ["git", "config", "--local", "user.name", "Test User"],
        cwd=str(cwd),
        check=True,
        env=env,
    )
    _ = subprocess.run(
        ["git", "config", "--local", "user.email", "test@example.com"],
        cwd=str(cwd),
        check=True,
        env=env,
    )


def _git_set_core_bare(*, cwd: Path, value: str) -> None:
    """Set `core.bare = <value>` on the repo at `cwd`."""
    _ = subprocess.run(
        ["git", "config", "--local", "core.bare", value],
        cwd=str(cwd),
        check=True,
        env=_scrubbed_env(),
    )


def _git_unset_core_bare(*, cwd: Path) -> None:
    """Unset `core.bare` on the repo at `cwd` (idempotent)."""
    _ = subprocess.run(
        ["git", "config", "--local", "--unset", "core.bare"],
        cwd=str(cwd),
        check=False,
        env=_scrubbed_env(),
    )


def test_passes_when_core_bare_is_true(*, tmp_path: Path) -> None:
    """(a) exit 0 when `core.bare = true` is set on the primary checkout."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _git_set_core_bare(cwd=project_root, value="true")

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_fails_when_core_bare_absent(*, tmp_path: Path) -> None:
    """(b) exit 4 when `core.bare` is absent from the primary checkout's config."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _git_unset_core_bare(cwd=project_root)

    result = _run_check(cwd=project_root)
    assert result.returncode == 4
    assert "core.bare" in result.stderr
    assert "is absent or `false`" in result.stderr
    assert "<absent>" in result.stderr


def test_fails_when_core_bare_explicitly_false(*, tmp_path: Path) -> None:
    """(c) exit 4 when `core.bare = false` (same as absent per contract)."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _git_set_core_bare(cwd=project_root, value="false")

    result = _run_check(cwd=project_root)
    assert result.returncode == 4
    assert "is absent or `false`" in result.stderr
    # The observed value carries the explicit `false` (not `<absent>`).
    assert "false" in result.stderr


def test_skipped_when_not_a_git_repo(*, tmp_path: Path) -> None:
    """exit 0 (skipped) when cwd is not inside a git working tree."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    # No `git init` — cwd is a bare directory.

    result = _run_check(cwd=project_root)
    assert result.returncode == 0
    assert "not inside a git working tree" in result.stderr


def test_skipped_when_git_unavailable(*, tmp_path: Path) -> None:
    """exit 0 (skipped) when `git` is not on PATH."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    # Empty PATH → `shutil.which("git")` returns None.
    result = _run_check(cwd=project_root, path_override="")
    assert result.returncode == 0
    assert "git not on PATH" in result.stderr


def test_passes_with_secondary_worktrees(*, tmp_path: Path) -> None:
    """exit 0 when primary has `core.bare = true` and secondary worktrees exist.

    The invariant reads only the primary `.git/config`; secondary
    worktrees carry a standalone `.git` FILE pointing back to the
    primary and are not inspected. This test creates a primary
    with `core.bare = true` plus a secondary worktree and confirms
    the check still passes against either checkout's cwd.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    seed = project_root / "seed.md"
    _ = seed.write_text("# seed\n", encoding="utf-8")
    env = _scrubbed_env()
    _ = subprocess.run(
        ["git", "add", "seed.md"],
        cwd=str(project_root),
        check=True,
        env=env,
    )
    _ = subprocess.run(
        ["git", "commit", "--quiet", "-m", "fixture commit"],
        cwd=str(project_root),
        check=True,
        env=env,
    )
    _ = subprocess.run(
        ["git", "branch", "feature/wip"],
        cwd=str(project_root),
        check=True,
        env=env,
    )
    wt_path = tmp_path / "wt-feature"
    _ = subprocess.run(
        ["git", "worktree", "add", str(wt_path), "feature/wip"],
        cwd=str(project_root),
        check=True,
        env=env,
    )
    _git_set_core_bare(cwd=project_root, value="true")

    # From the primary checkout: pass.
    result_primary = _run_check(cwd=project_root)
    assert result_primary.returncode == 0, result_primary.stderr
    # From the secondary worktree: also pass — `git config --get
    # core.bare` resolves to the primary's `.git/config` by git's
    # design.
    result_secondary = _run_check(cwd=wt_path)
    assert result_secondary.returncode == 0, result_secondary.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly via importlib (covers __name__ != "__main__" branch)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "primary_checkout_bare_flag_set_for_import_test",
        str(_CHECK),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert callable(module.main)


def test_module_re_import_with_vendor_in_sys_path() -> None:
    """Re-importing when _VENDOR_DIR is already on sys.path covers the False branch."""
    import importlib.util

    spec1 = importlib.util.spec_from_file_location(
        "primary_checkout_bare_flag_set_first_import",
        str(_CHECK),
    )
    assert spec1 is not None and spec1.loader is not None
    module1 = importlib.util.module_from_spec(spec1)
    spec1.loader.exec_module(module1)
    spec2 = importlib.util.spec_from_file_location(
        "primary_checkout_bare_flag_set_second_import",
        str(_CHECK),
    )
    assert spec2 is not None and spec2.loader is not None
    module2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(module2)
    assert callable(module2.main)
