"""Outside-in test for `livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py`.

Per `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary
invariants" → §"`primary-checkout-commit-refuse-hook-installed`":
every livespec-governed primary checkout MUST install
`.git/hooks/pre-commit` AND `.git/hooks/pre-push` hooks whose body
matches the canonical livespec commit-refuse fingerprint. The check
fires `fail` (exit 4) when either hook is missing, non-executable,
or contains a non-canonical body. The contract does not distinguish
between the failure modes at the structural level — all three flavors
fire equally; all three are corrected by the same bootstrap step.

The hook is a no-op at secondary worktrees because
`git rev-parse --show-toplevel` returns the worktree's path there
(not the primary's). The check itself inspects the common-dir
hooks directory (via `git rev-parse --git-common-dir`) which is
shared by every worktree, so the check passes equally from the
primary and from any secondary worktree once the hooks are
installed at the primary.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECK = (
    _REPO_ROOT
    / "livespec_dev_tooling"
    / "checks"
    / "primary_checkout_commit_refuse_hook_installed.py"
)


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


_CANONICAL_HOOK_BODY = """#!/bin/sh
# livespec commit-refuse hook — refuses commits/pushes at the primary checkout.
# No-op at worktrees because git rev-parse --show-toplevel returns the worktree path there.
primary_path="$(git config --get livespec.primaryPath || true)"
toplevel="$(git rev-parse --show-toplevel)"
if [ -n "$primary_path" ] && [ "$toplevel" = "$primary_path" ]; then
  echo "livespec: refusing commit/push at primary checkout ($toplevel); use a worktree" >&2
  exit 1
fi
exit 0
"""


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


def _install_hook(*, repo_root: Path, hook_name: str, body: str, executable: bool) -> Path:
    """Install a hook file at `<repo_root>/.git/hooks/<hook_name>` with `body`.

    When `executable` is True, sets the user-execute bit. Returns
    the absolute hook path.
    """
    hooks_dir = repo_root / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook_path = hooks_dir / hook_name
    _ = hook_path.write_text(body, encoding="utf-8")
    if executable:
        current_mode = hook_path.stat().st_mode
        hook_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    else:
        # Remove every execute bit so `os.access(..., os.X_OK)` returns False.
        current_mode = hook_path.stat().st_mode
        hook_path.chmod(current_mode & ~(stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
    return hook_path


def _install_canonical_hooks(*, repo_root: Path) -> None:
    """Install canonical pre-commit AND pre-push hooks, both executable."""
    _ = _install_hook(
        repo_root=repo_root,
        hook_name="pre-commit",
        body=_CANONICAL_HOOK_BODY,
        executable=True,
    )
    _ = _install_hook(
        repo_root=repo_root,
        hook_name="pre-push",
        body=_CANONICAL_HOOK_BODY,
        executable=True,
    )


def test_passes_when_both_hooks_installed_canonically(*, tmp_path: Path) -> None:
    """(a) exit 0 when both pre-commit and pre-push carry the canonical body."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_fails_when_both_hooks_missing(*, tmp_path: Path) -> None:
    """(b) exit 4 when neither hook file exists."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    # No hook install.

    result = _run_check(cwd=project_root)
    assert result.returncode == 4
    assert "pre-commit" in result.stderr
    assert "pre-push" in result.stderr
    assert "missing" in result.stderr


def test_fails_when_only_pre_commit_missing(*, tmp_path: Path) -> None:
    """(c) exit 4 when pre-commit is missing but pre-push is canonical."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-push",
        body=_CANONICAL_HOOK_BODY,
        executable=True,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4
    assert "pre-commit" in result.stderr
    assert "missing" in result.stderr


def test_fails_when_only_pre_push_missing(*, tmp_path: Path) -> None:
    """(d) exit 4 when pre-push is missing but pre-commit is canonical."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-commit",
        body=_CANONICAL_HOOK_BODY,
        executable=True,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4
    assert "pre-push" in result.stderr
    assert "missing" in result.stderr


def test_fails_when_pre_commit_not_executable(*, tmp_path: Path) -> None:
    """(e) exit 4 when pre-commit has canonical body but lacks the execute bit."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-commit",
        body=_CANONICAL_HOOK_BODY,
        executable=False,
    )
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-push",
        body=_CANONICAL_HOOK_BODY,
        executable=True,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4
    assert "pre-commit" in result.stderr
    assert "not_executable" in result.stderr


def test_fails_when_pre_push_not_executable(*, tmp_path: Path) -> None:
    """(f) exit 4 when pre-push has canonical body but lacks the execute bit."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-commit",
        body=_CANONICAL_HOOK_BODY,
        executable=True,
    )
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-push",
        body=_CANONICAL_HOOK_BODY,
        executable=False,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4
    assert "pre-push" in result.stderr
    assert "not_executable" in result.stderr


def test_fails_when_pre_commit_body_non_canonical(*, tmp_path: Path) -> None:
    """(g) exit 4 when pre-commit is executable but body lacks the canonical fingerprint."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    # Body looks vaguely shell-shaped but lacks every canonical marker.
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-commit",
        body="#!/bin/sh\necho 'custom hook'\nexit 0\n",
        executable=True,
    )
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-push",
        body=_CANONICAL_HOOK_BODY,
        executable=True,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4
    assert "pre-commit" in result.stderr
    assert "non_canonical_body" in result.stderr


def test_fails_when_pre_push_body_non_canonical(*, tmp_path: Path) -> None:
    """(h) exit 4 when pre-push is executable but body lacks the canonical fingerprint."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-commit",
        body=_CANONICAL_HOOK_BODY,
        executable=True,
    )
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-push",
        body="#!/bin/sh\necho 'custom push hook'\nexit 0\n",
        executable=True,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4
    assert "pre-push" in result.stderr
    assert "non_canonical_body" in result.stderr


def test_fails_when_pre_commit_body_empty(*, tmp_path: Path) -> None:
    """(i) exit 4 when pre-commit is executable but the body is empty (covers empty-file case)."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-commit",
        body="",
        executable=True,
    )
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-push",
        body=_CANONICAL_HOOK_BODY,
        executable=True,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4
    assert "pre-commit" in result.stderr
    assert "non_canonical_body" in result.stderr


def test_passes_with_tolerant_body_variant(*, tmp_path: Path) -> None:
    """(j) exit 0 when the body carries the marker + toplevel + exit 1 substrings with portable-shell rewrites.

    The fingerprint is substring-based, not exact-equality, so a
    semantically-equivalent body with rearranged whitespace and
    extra diagnostic echoes is still accepted.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    tolerant_body = (
        "#!/bin/sh\n"
        "# livespec commit-refuse hook (portable variant)\n"
        "set -e\n"
        'PRIMARY="$(git config --get livespec.primaryPath || true)"\n'
        'TOP="$(git rev-parse --show-toplevel)"\n'
        'if [ "$TOP" = "$PRIMARY" ]; then\n'
        '  echo "livespec: refusing at primary" >&2\n'
        "  exit 1\n"
        "fi\n"
        "exit 0\n"
    )
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-commit",
        body=tolerant_body,
        executable=True,
    )
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-push",
        body=tolerant_body,
        executable=True,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_passes_with_secondary_worktrees(*, tmp_path: Path) -> None:
    """(k) exit 0 when invoked from a secondary worktree (common-dir hooks resolve to primary).

    The check reads `<git-common-dir>/hooks/{pre-commit,pre-push}`,
    and the common dir is shared by every worktree, so a check
    invoked from a worktree resolves to the primary's hooks
    directory and passes when the primary is set up correctly.
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
    _install_canonical_hooks(repo_root=project_root)

    # From the primary checkout: pass.
    result_primary = _run_check(cwd=project_root)
    assert result_primary.returncode == 0, result_primary.stderr
    # From the secondary worktree: also pass — the common-dir
    # hooks resolve to the primary's `.git/hooks/`.
    result_secondary = _run_check(cwd=wt_path)
    assert result_secondary.returncode == 0, result_secondary.stderr


def test_skipped_when_not_a_git_repo(*, tmp_path: Path) -> None:
    """(l) exit 0 (skipped) when cwd is not a git repository at all."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    # No `git init` — cwd is a bare directory (no surrounding repo).

    result = _run_check(cwd=project_root)
    assert result.returncode == 0
    assert "not a git repository" in result.stderr


def test_fails_when_core_bare_set(*, tmp_path: Path) -> None:
    """(l2) exit 4 (fail) when the repo has `core.bare = true` (legacy bare-flag regression).

    Realizes the MAY in `livespec/SPECIFICATION/contracts.md`
    §"`primary-checkout-commit-refuse-hook-installed`": the doctor
    invariant MAY surface a `fail` when `core.bare = true` is set on
    the primary, to catch the eliminated legacy bare-flag state. A
    bare repo is a git repo that is NOT a work tree, so the prior
    work-tree-only skip silently passed it; the dedicated branch
    fires `fail` with the `core_bare_set` failure_mode instead.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    env = _scrubbed_env()
    _ = subprocess.run(
        ["git", "config", "core.bare", "true"],
        cwd=str(project_root),
        check=True,
        env=env,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "core_bare_set" in result.stderr
    assert "core.bare" in result.stderr


def test_skipped_when_git_repo_but_not_a_work_tree(*, tmp_path: Path) -> None:
    """(l3) exit 0 (skipped) when cwd is a git repo but NOT inside a work tree.

    A non-bare git repo whose cwd is inside the `.git` directory is a
    git context (`git rev-parse --git-dir` exits 0) that is NOT a
    working tree (`git rev-parse --is-inside-work-tree` is `false`).
    With `core.bare` unset (git's default `false`), the check falls
    through the bare-flag fail branch to the work-tree skip.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    git_dir = project_root / ".git"

    result = _run_check(cwd=git_dir)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "not inside a git working tree" in result.stderr


def test_skipped_when_git_unavailable(*, tmp_path: Path) -> None:
    """(m) exit 0 (skipped) when `git` is not on PATH."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    # Empty PATH → `shutil.which("git")` returns None.
    result = _run_check(cwd=project_root, path_override="")
    assert result.returncode == 0
    assert "git not on PATH" in result.stderr


def test_module_importable_without_running_main() -> None:
    """The check module imports cleanly via importlib (covers __name__ != "__main__" branch)."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "primary_checkout_commit_refuse_hook_installed_for_import_test",
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
        "primary_checkout_commit_refuse_hook_installed_first_import",
        str(_CHECK),
    )
    assert spec1 is not None and spec1.loader is not None
    module1 = importlib.util.module_from_spec(spec1)
    spec1.loader.exec_module(module1)
    spec2 = importlib.util.spec_from_file_location(
        "primary_checkout_commit_refuse_hook_installed_second_import",
        str(_CHECK),
    )
    assert spec2 is not None and spec2.loader is not None
    module2 = importlib.util.module_from_spec(spec2)
    spec2.loader.exec_module(module2)
    assert callable(module2.main)
