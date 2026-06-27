"""Outside-in test for `livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py`.

Per `livespec/SPECIFICATION/contracts.md` §"Doctor cross-boundary
invariants" → §"`primary-checkout-commit-refuse-hook-installed`": every
livespec-governed primary checkout MUST install `.git/hooks/pre-commit`,
`.git/hooks/pre-push`, AND `.git/hooks/commit-msg` hooks whose body is
the canonical livespec commit-refuse body. As of zs22.7.9.5 the verifier
is STRICT BYTE-IDENTITY against
`livespec_dev_tooling.install_commit_refuse_hooks.CANONICAL_HOOK_BODY`
(the single source) — the retired loose substring fingerprint, which
also accepted the legacy `git rev-parse --show-toplevel` body during the
fleet migration, is gone. The check fires `fail` (exit 4) when any hook
is missing, non-executable, or byte-different — INCLUDING a body that
would have satisfied the old loose fingerprint (the load-bearing
regression below).

A second arm fails on any vendored hook-source copy
(`git-hook-wrapper.sh` / `livespec-commit-refuse-hook.sh`) in the repo
tree, carving out `templates/` (the template-source domain of
zs22.7.9.3) and `.git/`.

A third arm (zs22.7.9.3) guards the worktree-discipline pack
(`dev-tooling/worktree-lib.sh` / `dev-tooling/branch-protection.sh`)
against drift from the single `install_worktree_pack` package source: the
pack is OPTIONAL (absent entirely → skip), but once any script is present
both MUST be present and byte-identical, else `worktree_pack_body_mismatch`
/ `worktree_pack_file_missing` (exit 4).

The check inspects the common-dir hooks directory (via `git rev-parse
--git-common-dir`), shared by every worktree, so it passes equally from
the primary and from any secondary worktree once the canonical hooks are
installed at the primary.
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

from livespec_dev_tooling.install_commit_refuse_hooks import CANONICAL_HOOK_BODY
from livespec_dev_tooling.install_worktree_pack import (
    CANONICAL_BRANCH_PROTECTION_BODY,
    CANONICAL_WORKTREE_LIB_BODY,
)

__all__: list[str] = []


# The pack's installed basenames paired with their canonical bodies — the
# fixture mirror of the verifier's `_WORKTREE_PACK_FILES`.
_WORKTREE_PACK_EXPECTED: tuple[tuple[str, str], ...] = (
    ("worktree-lib.sh", CANONICAL_WORKTREE_LIB_BODY),
    ("branch-protection.sh", CANONICAL_BRANCH_PROTECTION_BODY),
)


def _install_canonical_worktree_pack(*, repo_root: Path) -> None:
    """Write both canonical pack scripts under `<repo_root>/dev-tooling/`."""
    pack_dir = repo_root / "dev-tooling"
    pack_dir.mkdir(parents=True, exist_ok=True)
    for name, body in _WORKTREE_PACK_EXPECTED:
        _ = (pack_dir / name).write_text(body, encoding="utf-8")


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


_HOOK_NAMES: tuple[str, ...] = ("pre-commit", "pre-push", "commit-msg")


# A legacy body that PASSES the retired loose substring fingerprint
# (marker comment + `git rev-parse --show-toplevel` + `exit 1`) but is
# NOT byte-identical to CANONICAL_HOOK_BODY. Under the strict verifier
# this MUST fail — the load-bearing regression that proves the loose
# tolerance is gone.
_LEGACY_LOOSE_BODY = """#!/bin/sh
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

    When tests run as part of a git pre-commit hook (lefthook), git sets
    GIT_DIR/GIT_WORK_TREE/GIT_INDEX_FILE pointing at the surrounding
    repo. Scrubbing the vars confines git to the tmp_path fixture's
    `.git` directory.
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
    pytest-cov's subprocess auto-init works; overrides only PATH when
    `path_override` is given.
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

    When `executable` is True, sets the user-execute bit. Returns the
    absolute hook path.
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
    """Install canonical pre-commit, pre-push AND commit-msg hooks, all executable.

    Each is byte-identical to CANONICAL_HOOK_BODY (the single source the
    strict verifier compares against).
    """
    for hook_name in _HOOK_NAMES:
        _ = _install_hook(
            repo_root=repo_root,
            hook_name=hook_name,
            body=CANONICAL_HOOK_BODY,
            executable=True,
        )


def test_passes_when_all_three_canonical_installed(*, tmp_path: Path) -> None:
    """(a) exit 0 when all three hooks carry the byte-identical canonical body."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_fails_when_legacy_loose_body_byte_differs(*, tmp_path: Path) -> None:
    """(b) exit 4 when hooks carry the legacy body that PASSED the old loose fingerprint.

    Load-bearing regression: the legacy `git rev-parse --show-toplevel`
    body satisfies the retired substring fingerprint but is NOT
    byte-identical to CANONICAL_HOOK_BODY, so the strict verifier MUST
    fail it with `body_mismatch`.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    for hook_name in _HOOK_NAMES:
        _ = _install_hook(
            repo_root=project_root,
            hook_name=hook_name,
            body=_LEGACY_LOOSE_BODY,
            executable=True,
        )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "body_mismatch" in result.stderr
    assert "pre-commit" in result.stderr


def test_fails_when_canonical_plus_trailing_byte_differs(*, tmp_path: Path) -> None:
    """(c) exit 4 when a hook is canonical + one extra trailing byte (pure byte-identity).

    The body carries every canonical substring (it is a superset of the
    structural fingerprint), so it would survive a substring check — but
    a single appended byte breaks byte-identity, which the strict
    verifier rejects.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    # Overwrite one hook with canonical-plus-a-trailing-space.
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-push",
        body=CANONICAL_HOOK_BODY + " ",
        executable=True,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "body_mismatch" in result.stderr
    assert "pre-push" in result.stderr


def test_fails_when_commit_msg_missing(*, tmp_path: Path) -> None:
    """(d) exit 4 when commit-msg is missing but pre-commit and pre-push are canonical.

    The third hook (commit-msg) is now part of the required set; omitting
    it is a `missing` failure that the prior two-hook check would have
    silently passed.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-commit",
        body=CANONICAL_HOOK_BODY,
        executable=True,
    )
    _ = _install_hook(
        repo_root=project_root,
        hook_name="pre-push",
        body=CANONICAL_HOOK_BODY,
        executable=True,
    )
    # commit-msg deliberately not installed.

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "commit-msg" in result.stderr
    assert "missing" in result.stderr


def test_fails_when_a_hook_not_executable(*, tmp_path: Path) -> None:
    """(e) exit 4 when a hook has the canonical body but lacks the execute bit."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    # Strip the execute bit from commit-msg (canonical body, not executable).
    _ = _install_hook(
        repo_root=project_root,
        hook_name="commit-msg",
        body=CANONICAL_HOOK_BODY,
        executable=False,
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "commit-msg" in result.stderr
    assert "not_executable" in result.stderr


def test_fails_when_vendored_copy_present(*, tmp_path: Path) -> None:
    """(f) exit 4 when a vendored hook-source copy exists outside the carve-outs.

    All three hooks are canonical, so the ONLY failure is the vendored
    `git-hook-wrapper.sh` at the repo root — proving the no-vendored-copy
    arm fires independently of the byte-identity arm.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    vendored = project_root / "git-hook-wrapper.sh"
    _ = vendored.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "vendored_copy_present" in result.stderr
    assert "git-hook-wrapper.sh" in result.stderr


def test_passes_when_copy_under_templates(*, tmp_path: Path) -> None:
    """(g) exit 0 when the only hook-source copy lives under templates/ (carve-out).

    The template-source copy under `templates/` is the zs22.7.9.3 domain
    and is NOT a vendored/installed copy, so it is carved out and the
    check passes.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    templates_dir = project_root / "templates" / "hooks"
    templates_dir.mkdir(parents=True)
    carved = templates_dir / "livespec-commit-refuse-hook.sh"
    _ = carved.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_passes_with_secondary_worktrees(*, tmp_path: Path) -> None:
    """(h) exit 0 when invoked from a secondary worktree (common-dir hooks resolve to primary).

    The check reads `<git-common-dir>/hooks/{pre-commit,pre-push,commit-msg}`,
    and the common dir is shared by every worktree, so a check invoked
    from a worktree resolves to the primary's hooks directory and passes
    when the primary is set up correctly. Also exercises the absolute
    common-dir resolution branch.
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

    # From the primary checkout: pass (relative common-dir resolution).
    result_primary = _run_check(cwd=project_root)
    assert result_primary.returncode == 0, result_primary.stderr
    # From the secondary worktree: also pass — the common-dir hooks
    # resolve to the primary's `.git/hooks/` (absolute common-dir).
    result_secondary = _run_check(cwd=wt_path)
    assert result_secondary.returncode == 0, result_secondary.stderr


def test_skipped_when_not_a_git_repo(*, tmp_path: Path) -> None:
    """(i) exit 0 (skipped) when cwd is not a git repository at all."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    # No `git init` — cwd is a bare directory (no surrounding repo).

    result = _run_check(cwd=project_root)
    assert result.returncode == 0
    assert "not a git repository" in result.stderr


def test_fails_when_core_bare_set(*, tmp_path: Path) -> None:
    """(j) exit 4 (fail) when the repo has `core.bare = true` (legacy bare-flag regression)."""
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
    """(k) exit 0 (skipped) when cwd is a git repo but NOT inside a work tree.

    A non-bare git repo whose cwd is inside the `.git` directory is a git
    context (`git rev-parse --git-dir` exits 0) that is NOT a working
    tree (`git rev-parse --is-inside-work-tree` is `false`). With
    `core.bare` unset (git's default `false`), the check falls through
    the bare-flag fail branch to the work-tree skip.
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
    """(l) exit 0 (skipped) when `git` is not on PATH."""
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


def test_passes_when_no_worktree_pack(*, tmp_path: Path) -> None:
    """(m) exit 0 when the worktree pack is absent (it is OPTIONAL per repo).

    Canonical hooks are installed and `dev-tooling/` carries no pack
    scripts; the pack arm SKIPS rather than false-failing a repo that
    legitimately has not installed the pack.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    # A `dev-tooling/` dir with an unrelated file but no pack scripts.
    dev_tooling = project_root / "dev-tooling"
    dev_tooling.mkdir()
    _ = (dev_tooling / "CLAUDE.md").write_text("# unrelated\n", encoding="utf-8")

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_passes_when_worktree_pack_canonical(*, tmp_path: Path) -> None:
    """(n) exit 0 when both pack scripts are present and byte-identical."""
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _install_canonical_worktree_pack(repo_root=project_root)

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_fails_when_worktree_lib_drifts(*, tmp_path: Path) -> None:
    """(o) exit 4 when a present pack script's bytes differ from canonical.

    All three hooks and `branch-protection.sh` are canonical, so the ONLY
    failure is the drifted `worktree-lib.sh` — proving the pack byte-identity
    arm fires independently.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _install_canonical_worktree_pack(repo_root=project_root)
    # Drift one byte of worktree-lib.sh.
    drifted = project_root / "dev-tooling" / "worktree-lib.sh"
    _ = drifted.write_text(CANONICAL_WORKTREE_LIB_BODY + "# drift\n", encoding="utf-8")

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_pack_body_mismatch" in result.stderr
    assert "worktree-lib.sh" in result.stderr


def test_fails_when_worktree_pack_partially_installed(*, tmp_path: Path) -> None:
    """(p) exit 4 when one pack script is present (canonical) but its sibling is absent.

    A present-but-incomplete pack is a partial/drifted install: the missing
    sibling fails as `worktree_pack_file_missing`.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    pack_dir = project_root / "dev-tooling"
    pack_dir.mkdir()
    # Only worktree-lib.sh present (canonical); branch-protection.sh absent.
    _ = (pack_dir / "worktree-lib.sh").write_text(CANONICAL_WORKTREE_LIB_BODY, encoding="utf-8")

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_pack_file_missing" in result.stderr
    assert "branch-protection.sh" in result.stderr
