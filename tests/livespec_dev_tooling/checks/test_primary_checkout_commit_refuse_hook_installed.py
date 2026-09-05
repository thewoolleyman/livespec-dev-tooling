"""Outside-in test for `livespec_dev_tooling/checks/primary_checkout_commit_refuse_hook_installed.py`.

Per `livespec/SPECIFICATION/contracts.md` section "Doctor cross-boundary
invariants" → section "`primary-checkout-commit-refuse-hook-installed`": every
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
(`dev-tooling/worktree-lib.sh` / `dev-tooling/branch-protection.sh` /
`dev-tooling/worktree.just`, the worktree-lifecycle recipe fragment added
zs22.7.9 W2c/.4, plus `dev-tooling/branch-protection.just`, the
branch-protection recipe fragment added zs22 jzpx)
against drift from the single `install_worktree_pack` package source: the
pack is OPTIONAL (absent entirely → skip), but once any pack file is
present ALL MUST be present and byte-identical, else
`worktree_pack_body_mismatch` / `worktree_pack_file_missing` (exit 4).

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

import pytest

from livespec_dev_tooling.install_commit_refuse_hooks import CANONICAL_HOOK_BODY
from livespec_dev_tooling.install_worktree_pack import (
    CANONICAL_BRANCH_PROTECTION_BODY,
    CANONICAL_BRANCH_PROTECTION_JUST_BODY,
    CANONICAL_GATE_RUN_BODY,
    CANONICAL_NO_WORKFLOW_EDITS_BODY,
    CANONICAL_WORKTREE_JUST_BODY,
    CANONICAL_WORKTREE_LIB_BODY,
)
from livespec_dev_tooling.install_worktree_pack import main as install_worktree_pack_main

__all__: list[str] = []


# The pack's installed basenames paired with their canonical bodies — the
# fixture mirror of the verifier's `_WORKTREE_PACK_FILES` (the four `.sh`
# scripts plus the two `.just` recipe fragments).
_WORKTREE_PACK_EXPECTED: tuple[tuple[str, str], ...] = (
    ("worktree-lib.sh", CANONICAL_WORKTREE_LIB_BODY),
    ("branch-protection.sh", CANONICAL_BRANCH_PROTECTION_BODY),
    ("gate-run.sh", CANONICAL_GATE_RUN_BODY),
    ("check-no-workflow-edits.sh", CANONICAL_NO_WORKFLOW_EDITS_BODY),
    ("worktree.just", CANONICAL_WORKTREE_JUST_BODY),
    ("branch-protection.just", CANONICAL_BRANCH_PROTECTION_JUST_BODY),
)


def _install_canonical_worktree_pack(*, repo_root: Path) -> None:
    """Write all canonical pack files under `<repo_root>/dev-tooling/`."""
    pack_dir = repo_root / "dev-tooling"
    pack_dir.mkdir(parents=True, exist_ok=True)
    for name, body in _WORKTREE_PACK_EXPECTED:
        _ = (pack_dir / name).write_text(body, encoding="utf-8")


def _write_pack_imports(*, repo_root: Path, omit: str = "") -> None:
    """Write a root `justfile` carrying the pack's two `import?` lines.

    `omit` drops exactly one fragment's import line, which is how the
    discoverability arm is exercised: the pack stays byte-perfect on disk
    while `just --list` loses the corresponding recipes.
    """
    lines = [
        line
        for line in (
            "import? 'dev-tooling/worktree.just'",
            "import? 'dev-tooling/branch-protection.just'",
        )
        if omit not in line or omit == ""
    ]
    _ = (repo_root / "justfile").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_livespec_config(*, repo_root: Path, body: str) -> None:
    """Write `<repo_root>/.livespec.jsonc` verbatim (JSONC, comments allowed)."""
    _ = (repo_root / ".livespec.jsonc").write_text(body, encoding="utf-8")


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


def _declare_sandbox_exempt(*, repo_root: Path, value: str) -> None:
    """Set the local `livespec.sandboxExempt` marker to `value`.

    The same declared git-config marker the Fabro sandbox's prepare step sets
    and `CANONICAL_HOOK_BODY` reads. `value` is written verbatim so a test can
    assert that only the literal `"true"` exempts.
    """
    _ = subprocess.run(
        ["git", "config", "--local", "livespec.sandboxExempt", value],
        cwd=str(repo_root),
        check=True,
        env=_scrubbed_env(),
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
    """(n) exit 0 when every pack file is present, byte-identical, AND imported.

    The `_write_pack_imports` call is load-bearing since the discoverability
    arm landed: a byte-perfect pack that the root justfile does not `import?`
    is invisible to `just --list` and is now its own FAIL.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _install_canonical_worktree_pack(repo_root=project_root)
    _write_pack_imports(repo_root=project_root)

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


def test_fails_when_worktree_just_drifts(*, tmp_path: Path) -> None:
    """(q) exit 4 when the `worktree.just` recipe fragment's bytes differ from canonical.

    All three hooks and both `.sh` scripts are canonical, so the ONLY failure
    is the drifted `worktree.just` — proving the recipe fragment rides the
    same pack byte-identity arm as the scripts.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _install_canonical_worktree_pack(repo_root=project_root)
    # Drift one byte of worktree.just.
    drifted = project_root / "dev-tooling" / "worktree.just"
    _ = drifted.write_text(CANONICAL_WORKTREE_JUST_BODY + "# drift\n", encoding="utf-8")

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_pack_body_mismatch" in result.stderr
    assert "worktree.just" in result.stderr


def test_fails_when_worktree_just_absent_with_scripts_present(*, tmp_path: Path) -> None:
    """(r) exit 4 when both `.sh` scripts are canonical but `worktree.just` is absent.

    Once any pack file is present the whole pack is considered installed, so a
    missing `worktree.just` is a partial install: it fails as
    `worktree_pack_file_missing`.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    pack_dir = project_root / "dev-tooling"
    pack_dir.mkdir()
    # Both `.sh` scripts present (canonical); worktree.just absent.
    _ = (pack_dir / "worktree-lib.sh").write_text(CANONICAL_WORKTREE_LIB_BODY, encoding="utf-8")
    _ = (pack_dir / "branch-protection.sh").write_text(
        CANONICAL_BRANCH_PROTECTION_BODY, encoding="utf-8"
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_pack_file_missing" in result.stderr
    assert "worktree.just" in result.stderr


def test_fails_when_branch_protection_just_drifts(*, tmp_path: Path) -> None:
    """(s) exit 4 when the `branch-protection.just` recipe fragment's bytes drift.

    All three hooks, both `.sh` scripts, and `worktree.just` are canonical, so
    the ONLY failure is the drifted `branch-protection.just` — proving the
    branch-protection recipe fragment rides the same pack byte-identity arm as
    the worktree fragment and the scripts.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _install_canonical_worktree_pack(repo_root=project_root)
    # Drift one byte of branch-protection.just.
    drifted = project_root / "dev-tooling" / "branch-protection.just"
    _ = drifted.write_text(CANONICAL_BRANCH_PROTECTION_JUST_BODY + "# drift\n", encoding="utf-8")

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_pack_body_mismatch" in result.stderr
    assert "branch-protection.just" in result.stderr


def test_fails_when_branch_protection_just_absent_with_others_present(*, tmp_path: Path) -> None:
    """(t) exit 4 when the other three pack files are canonical but `branch-protection.just` is absent.

    Once any pack file is present the whole pack is considered installed, so a
    missing `branch-protection.just` is a partial install: it fails as
    `worktree_pack_file_missing`.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    pack_dir = project_root / "dev-tooling"
    pack_dir.mkdir()
    # The two `.sh` scripts + worktree.just present (canonical); branch-protection.just absent.
    _ = (pack_dir / "worktree-lib.sh").write_text(CANONICAL_WORKTREE_LIB_BODY, encoding="utf-8")
    _ = (pack_dir / "branch-protection.sh").write_text(
        CANONICAL_BRANCH_PROTECTION_BODY, encoding="utf-8"
    )
    _ = (pack_dir / "worktree.just").write_text(CANONICAL_WORKTREE_JUST_BODY, encoding="utf-8")

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_pack_file_missing" in result.stderr
    assert "branch-protection.just" in result.stderr


# ---------------------------------------------------------------
# Config-gated required default (A2) — `worktree_discipline.pack`.
#
# The pack arm used to fail OPEN: no pack file present meant "skip", so the
# repo that fell through the originating incident stayed green. These arms
# make ABSENCE OF THE KEY MEAN `required`, which is the exact point where
# this design diverges from the `harnesses` precedent in
# `checks/plugin_resolution.py` (there, a missing key is itself a FAIL).
# ---------------------------------------------------------------


def test_fails_when_pack_required_by_default_and_absent(*, tmp_path: Path) -> None:
    """(s) exit 4 when `.livespec.jsonc` omits the key and no pack is installed.

    ACCEPTANCE 1. An absent `worktree_discipline` key DEFAULTS to `required`,
    so a governed repo with no pack is a FAIL carrying the remedy — this is
    the fail-open that let the originating incident through.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _write_livespec_config(repo_root=project_root, body='{"template": "livespec"}\n')

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_pack_absent" in result.stderr


def test_skips_when_pack_declared_optional_and_absent(*, tmp_path: Path) -> None:
    """(t) exit 0 when the repo DECLARES `pack: "optional"` and installs none.

    ACCEPTANCE 2. The sanctioned, reviewable opt-out: a repo may decline the
    pack, but only by saying so in tracked config where a reviewer sees it.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _write_livespec_config(
        repo_root=project_root,
        body='{\n  // declared opt-out\n  "worktree_discipline": {"pack": "optional"}\n}\n',
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_fails_when_worktree_discipline_block_malformed(*, tmp_path: Path) -> None:
    """(u) exit 4 when `worktree_discipline` is present but garbled.

    ACCEPTANCE 3. Fail-closed, matching the `harnesses` precedent's malformed
    arm: an unparseable declaration must never read as a silent opt-out.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _install_canonical_worktree_pack(repo_root=project_root)
    _write_pack_imports(repo_root=project_root)
    _write_livespec_config(
        repo_root=project_root,
        body='{"worktree_discipline": "required"}\n',
    )

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_discipline_malformed" in result.stderr


def test_passes_when_key_absent_and_pack_present(*, tmp_path: Path) -> None:
    """(v) exit 0 when the key is absent but the pack IS installed and imported.

    ACCEPTANCE 4 — the arm where this design deliberately diverges from
    `load_harnesses`. There, a missing key is ABSENT/fail-closed and reds the
    repo outright. Here a missing key means `required`, and a repo that
    SATISFIES `required` must pass. Pinned by its own test precisely because
    copying the precedent would silently red every conformant fleet repo.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _install_canonical_worktree_pack(repo_root=project_root)
    _write_pack_imports(repo_root=project_root)
    _write_livespec_config(repo_root=project_root, body='{"template": "livespec"}\n')

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_fails_when_pack_present_but_not_imported(*, tmp_path: Path) -> None:
    """(w) exit 4 when the pack is byte-perfect but an `import?` line is missing.

    ACCEPTANCE 7 — the discoverability arm, and the one that closes steps 1-2
    of the originating causal chain. This exact state PASSED before A2: the
    verifier compared bytes and never asked whether `just --list` could see
    the recipes. The pack below is byte-identical to canonical; only the
    `worktree.just` import is dropped.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _install_canonical_worktree_pack(repo_root=project_root)
    _write_pack_imports(repo_root=project_root, omit="worktree.just")

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_pack_not_imported" in result.stderr
    assert "worktree.just" in result.stderr


def test_skips_pack_arm_when_livespec_jsonc_absent(*, tmp_path: Path) -> None:
    """(x) exit 0 when there is no `.livespec.jsonc` at all and no pack.

    ACCEPTANCE 8 — the STATED choice, not an inherited one. `.livespec.jsonc`
    is what makes a directory governed, so its absence means "not a governed
    repo" and the pack arm cannot be more governed-aware than the file that
    defines governance. This is deliberately NOT a usable opt-out: deleting
    the file from a real fleet repo strips `template` / `spec_root` /
    `harnesses` / `compat` and reds fleet conformance loudly, so it trades a
    silent gap for an unmissable one.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


# ---------------------------------------------------------------
# The DECLARED sandbox exemption reaches the pack-PRESENCE arm.
#
# A Fabro sandbox is a fresh FULL clone that never runs `just bootstrap`, and
# the pack is gitignored by design — so the four pack files CANNOT be present
# there. A2 made an absent pack a FAIL without honouring the exemption slot the
# hook body already reads, which made the assertion unsatisfiable in exactly
# the environment the dispatch gate runs in: every ImplementWorkItem dispatch
# in `livespec-orchestrator-beads-fabro` died at its `verify-commit-refuse-hook`
# setup step, and that repo pinned dev-tooling back to v0.54.19 to recover.
#
# The fix reuses the SAME declared marker `livespec.sandboxExempt`, which
# `CANONICAL_HOOK_BODY` already honours in two places (the refuse-at-primary
# arm and the positive-location arm). It is the Exemption slot of the
# Conformance Pattern's concern #1 Worktree-discipline — a variation point the
# checker reads, never an incidental fail-open.
#
# Only the PRESENCE arm is exempted. A pack that IS installed must still be
# byte-canonical everywhere, so the drift the check exists to catch keeps
# firing inside a sandbox too.
# ---------------------------------------------------------------


def test_skips_pack_absent_arm_when_sandbox_exempt_declared(*, tmp_path: Path) -> None:
    """Exit 0 when the pack is absent in a tree DECLARED `livespec.sandboxExempt`.

    ACCEPTANCE 10. This is the fresh-clone shape the Fabro sandbox runs the
    check in: canonical hooks installed, exemption declared, and the gitignored
    pack necessarily absent because bootstrap has not run. Requiring the pack
    here asserts a property that CANNOT hold, which is a false positive rather
    than a drift signal.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _write_livespec_config(repo_root=project_root, body='{"template": "livespec"}\n')
    _declare_sandbox_exempt(repo_root=project_root, value="true")

    result = _run_check(cwd=project_root)
    assert result.returncode == 0, (
        f"expected exit 0; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_fails_when_pack_absent_and_sandbox_exemption_not_declared(*, tmp_path: Path) -> None:
    """Exit 4 when the marker is present but is NOT `true`.

    ACCEPTANCE 11. The exemption is a DECLARATION, not the mere existence of a
    key: a real primary checkout that never bootstrapped still fails, and its
    `just bootstrap` remedy still works there. Without this arm the fix could
    degrade into a blanket skip and reopen the fail-open A2 closed.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _write_livespec_config(repo_root=project_root, body='{"template": "livespec"}\n')
    _declare_sandbox_exempt(repo_root=project_root, value="false")

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_pack_absent" in result.stderr


def test_fails_when_installed_pack_drifts_even_though_sandbox_exempt(*, tmp_path: Path) -> None:
    """Exit 4 on a DRIFTED pack even in a declared-exempt tree.

    ACCEPTANCE 12 — the injected defect the record names: skipping the whole
    arm whenever a sandbox is exempt would stop detecting real drift, which is
    the check's entire purpose. Only the PRESENCE arm is exempt; byte-identity
    is not.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    _install_canonical_hooks(repo_root=project_root)
    _install_canonical_worktree_pack(repo_root=project_root)
    _write_pack_imports(repo_root=project_root)
    drifted = project_root / "dev-tooling" / "worktree-lib.sh"
    _ = drifted.write_text(CANONICAL_WORKTREE_LIB_BODY + "# drift\n", encoding="utf-8")
    _declare_sandbox_exempt(repo_root=project_root, value="true")

    result = _run_check(cwd=project_root)
    assert result.returncode == 4, (
        f"expected exit 4; got {result.returncode}, "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "worktree_pack_body_mismatch" in result.stderr


# ---------------------------------------------------------------
# C — the installer writes `worktree_discipline.pack` with its default.
#
# C lives in THIS file, beside the A2 arms it documents, because the two are
# one changeset under the single-commit Red-Green-Replay protocol: A2 makes an
# absent key MEAN `required`, and C is what stops that from being folklore. A
# new adopter should read its own `.livespec.jsonc` and SEE the obligation
# rather than infer it from a verifier failure.
#
# The installer is exercised IN-PROCESS via `monkeypatch.chdir` + `main()`,
# matching `tests/livespec_dev_tooling/test_install_worktree_pack.py`; the only
# subprocess here remains `git` for repo setup.
# ---------------------------------------------------------------


def test_installer_writes_worktree_discipline_default_when_key_absent(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ACCEPTANCE 9. The installer adds the key with its default AND a comment."""
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    config = project_root / ".livespec.jsonc"
    _ = config.write_text('{\n  "template": "livespec"\n}\n', encoding="utf-8")
    monkeypatch.chdir(project_root)

    rc = install_worktree_pack_main()

    assert rc == 0
    written = config.read_text(encoding="utf-8")
    assert '"worktree_discipline"' in written
    assert '"pack": "required"' in written
    # The comment is the whole point of C — the key must be self-explaining.
    assert "//" in written
    # Pre-existing content survives.
    assert '"template": "livespec"' in written


def test_installer_leaves_an_existing_worktree_discipline_block_untouched(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A declared `optional` opt-out MUST NOT be silently rewritten to `required`.

    The installer provisions a default for repos that never declared one; it is
    not a policy enforcer. Overwriting a deliberate, reviewed opt-out would make
    the sanctioned escape hatch unusable — and would turn `just bootstrap` into
    a config mutation nobody asked for.
    """
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    config = project_root / ".livespec.jsonc"
    original = '{\n  "worktree_discipline": {"pack": "optional"}\n}\n'
    _ = config.write_text(original, encoding="utf-8")
    monkeypatch.chdir(project_root)

    rc = install_worktree_pack_main()

    assert rc == 0
    assert config.read_text(encoding="utf-8") == original


def test_installer_does_not_create_livespec_jsonc_when_absent(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No `.livespec.jsonc` means a non-governed dir — the installer MUST NOT mint one.

    Pairs with the verifier's `.livespec.jsonc`-absent SKIP arm: both treat the
    file's absence as "not governed" rather than as something to fix. Minting a
    governance file as a side effect of installing recipe fragments would be a
    surprising mutation, and would make the SKIP arm unreachable in practice.
    """
    for var in _GIT_ENV_PASSTHROUGH_VARS:
        monkeypatch.delenv(var, raising=False)
    project_root = tmp_path / "project"
    project_root.mkdir()
    _git_init(cwd=project_root)
    monkeypatch.chdir(project_root)

    rc = install_worktree_pack_main()

    assert rc == 0
    assert not (project_root / ".livespec.jsonc").exists()
    # The pack itself still installed.
    assert (project_root / "dev-tooling" / "worktree-lib.sh").is_file()
