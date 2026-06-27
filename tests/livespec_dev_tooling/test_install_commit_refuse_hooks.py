"""Outside-in test for `livespec_dev_tooling/install_commit_refuse_hooks.py`.

The installer writes the canonical livespec commit-refuse hook body to
the primary checkout's shared `.git/hooks/{pre-commit,pre-push,commit-msg}`,
each executable, resolving the target via `git rev-parse --git-common-dir`
so it lands in the PRIMARY's shared hooks dir even when invoked from a
linked worktree.

The installed body is the STRUCTURAL, armed-on-install commit-refuse
hook (per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Primary-checkout commit-refuse hook"): it refuses when the
repository's git-dir equals its git-common-dir (the structural
signature of a primary checkout), UNLESS `livespec.sandboxExempt=true`.
At a linked worktree the two differ, so the hook delegates to lefthook.

The installer is exercised IN-PROCESS (`main()` with
`monkeypatch.chdir`) — no Python subprocess spawn (this test is not on
the `subprocess_spawn_allowlist`). The installed hook body itself is
exercised by invoking the script via `sh` (a shell, not a Python child),
with a stub `mise` on PATH standing in for the lefthook delegation so
the delegate branch terminates deterministically.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

from livespec_dev_tooling.install_commit_refuse_hooks import (
    CANONICAL_HOOK_BODY,
    main,
)

__all__: list[str] = []


_HOOK_NAMES: tuple[str, ...] = ("pre-commit", "pre-push", "commit-msg")

# git sets these in a hook's environment when it fires inside a worktree;
# when this suite runs under a lefthook pre-commit they also leak in from
# the surrounding repo. Scrubbing them confines every git invocation
# (in-process and via the installed hook) to the tmp_path fixture.
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


def _make_fake_mise(*, bin_dir: Path) -> Path:
    """Write an executable stub `mise` into `bin_dir`; return `bin_dir`.

    The stub stands in for the hook's `exec mise exec -- lefthook run ...`
    delegation: it records its argv (when `MISE_CAPTURE_FILE` is set) and
    exits 0, so a hook that reaches the delegate branch terminates
    cleanly without actually running mise/lefthook.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    mise = bin_dir / "mise"
    _ = mise.write_text(
        "#!/bin/sh\n"
        'if [ -n "$MISE_CAPTURE_FILE" ]; then printf \'%s\\n\' "$*" >> "$MISE_CAPTURE_FILE"; fi\n'
        "exit 0\n",
        encoding="utf-8",
    )
    current_mode = mise.stat().st_mode
    mise.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return bin_dir


def _run_installed_hook(
    *,
    hook_path: Path,
    cwd: Path,
    fakebin: Path,
    capture_file: Path | None = None,
    extra_args: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Invoke an installed hook script via `sh` with the stub mise on PATH."""
    env = dict(os.environ)
    env["PATH"] = f"{fakebin}{os.pathsep}{env.get('PATH', '')}"
    if capture_file is not None:
        env["MISE_CAPTURE_FILE"] = str(capture_file)
    return subprocess.run(
        ["sh", str(hook_path), *extra_args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def test_main_installs_all_three_hooks_at_primary(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()` writes the canonical body to all three hooks, executable, at the primary."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    rc = main()

    assert rc == 0
    hooks_dir = primary / ".git" / "hooks"
    for name in _HOOK_NAMES:
        hook = hooks_dir / name
        assert hook.is_file(), f"{name} not installed"
        assert os.access(hook, os.X_OK), f"{name} not executable"
        assert hook.read_text(encoding="utf-8") == CANONICAL_HOOK_BODY


def test_main_from_worktree_installs_into_primary_hooks_dir(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invoked from a linked worktree, the install lands in the PRIMARY's shared hooks dir.

    Exercises the absolute-common-dir resolution branch (a worktree's
    `git rev-parse --git-common-dir` returns the primary's `.git`
    absolutely).
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary, worktree = _init_primary_with_worktree(tmp_path=tmp_path)
    monkeypatch.chdir(worktree)

    rc = main()

    assert rc == 0
    primary_hooks = primary / ".git" / "hooks"
    for name in _HOOK_NAMES:
        hook = primary_hooks / name
        assert hook.is_file(), f"{name} not installed into primary hooks dir"
        assert hook.read_text(encoding="utf-8") == CANONICAL_HOOK_BODY


def test_main_is_idempotent(*, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Re-running the installer overwrites with the identical canonical body."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)

    assert main() == 0
    first = (primary / ".git" / "hooks" / "pre-commit").read_text(encoding="utf-8")
    assert main() == 0
    second = (primary / ".git" / "hooks" / "pre-commit").read_text(encoding="utf-8")

    assert first == second == CANONICAL_HOOK_BODY


def test_installed_hook_refuses_at_primary(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(a) the installed hook exits 1 (refuse) when invoked at the primary checkout."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    monkeypatch.chdir(primary)
    assert main() == 0
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    hook = primary / ".git" / "hooks" / "pre-commit"

    result = _run_installed_hook(hook_path=hook, cwd=primary, fakebin=fakebin)

    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "refusing" in result.stderr


def test_installed_hook_delegates_at_worktree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(b) the installed hook does NOT refuse (delegates) when invoked from a worktree."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary, worktree = _init_primary_with_worktree(tmp_path=tmp_path)
    monkeypatch.chdir(primary)
    assert main() == 0
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    hook = primary / ".git" / "hooks" / "pre-commit"

    result = _run_installed_hook(hook_path=hook, cwd=worktree, fakebin=fakebin)

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "refusing" not in result.stderr


def test_installed_hook_sandbox_exempt_bypasses_refuse_at_primary(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """(c) `livespec.sandboxExempt=true` bypasses the refuse branch at the primary."""
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    _run_git(args=["config", "livespec.sandboxExempt", "true"], cwd=primary)
    monkeypatch.chdir(primary)
    assert main() == 0
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    hook = primary / ".git" / "hooks" / "pre-commit"

    result = _run_installed_hook(hook_path=hook, cwd=primary, fakebin=fakebin)

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "refusing" not in result.stderr


def test_installed_commit_msg_hook_forwards_message_file_arg(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The commit-msg hook forwards its commit-message-file path arg to lefthook.

    The red-green-replay commit-msg gate reads the message file as
    argv[1], so the hook's `... commit-msg "$@"` delegation MUST pass it
    through. The stub mise records the forwarded argv.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary, worktree = _init_primary_with_worktree(tmp_path=tmp_path)
    monkeypatch.chdir(primary)
    assert main() == 0
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    capture = tmp_path / "mise-args.txt"
    msg_file = worktree / "COMMIT_EDITMSG_fixture"
    _ = msg_file.write_text("subject line\n", encoding="utf-8")
    hook = primary / ".git" / "hooks" / "commit-msg"

    result = _run_installed_hook(
        hook_path=hook,
        cwd=worktree,
        fakebin=fakebin,
        capture_file=capture,
        extra_args=(str(msg_file),),
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    captured = capture.read_text(encoding="utf-8")
    assert "commit-msg" in captured, captured
    assert str(msg_file) in captured, captured


def test_canonical_body_is_structural() -> None:
    """The canonical body carries the structural fingerprint + exemption marker.

    Locks the shape the verifier
    (`primary_checkout_commit_refuse_hook_installed`) fingerprints: the
    marker comment, the structural `git rev-parse --git-common-dir`
    detection, the `exit 1` refuse branch, and the
    `livespec.sandboxExempt` exemption marker MUST all be present — so a
    future edit cannot silently break verifier recognition or drop the
    declared sandbox exemption. The retired primaryPath arming step's
    executable read (`git config --get livespec.primaryPath`) is gone
    (its name survives only in the explanatory comment describing what
    the structural body supersedes).
    """
    assert "# livespec commit-refuse hook" in CANONICAL_HOOK_BODY
    assert "git rev-parse --git-common-dir" in CANONICAL_HOOK_BODY
    assert "exit 1" in CANONICAL_HOOK_BODY
    assert "livespec.sandboxExempt" in CANONICAL_HOOK_BODY
    assert "git config --get livespec.primaryPath" not in CANONICAL_HOOK_BODY


def test_canonical_body_unsets_git_dir_env_before_lefthook() -> None:
    """The canonical body clears git-injected GIT_DIR env before invoking lefthook (core.bare-flip fix).

    Relocated from livespec core's
    `test_git_hook_wrapper_unsets_git_dir_env_before_lefthook`
    (convergence zs22.7.9, W2b) now that the canonical body is the SINGLE
    source for the hook. The body MUST carry the `unset GIT_DIR
    GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX` line on its own line, and it
    MUST appear BEFORE the `lefthook run --no-auto-install` exec.
    Otherwise lefthook, run with the git-injected GIT_DIR, misreads the
    repo as bare and writes core.bare=true into the shared config,
    corrupting every checkout that shares it (root cause li-iroguc).
    """
    lines = CANONICAL_HOOK_BODY.splitlines()

    unset_line_indices = [
        i
        for i, line in enumerate(lines)
        if line.strip() == "unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX"
    ]
    assert unset_line_indices, (
        "CANONICAL_HOOK_BODY is missing the "
        "'unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX' line; "
        "without it lefthook (run with the git-injected GIT_DIR) writes "
        "core.bare=true to the shared config (li-iroguc)."
    )

    lefthook_exec_indices = [
        i for i, line in enumerate(lines) if "lefthook run --no-auto-install" in line
    ]
    assert lefthook_exec_indices, (
        "CANONICAL_HOOK_BODY is missing the 'lefthook run --no-auto-install' exec line; "
        "the canonical body's dispatch contract is broken."
    )

    assert min(unset_line_indices) < min(lefthook_exec_indices), (
        "CANONICAL_HOOK_BODY has the unset line AFTER the 'lefthook run' exec line; "
        "it must come BEFORE so the env is cleared before lefthook resolves the repo. "
        f"unset at line {min(unset_line_indices) + 1}, "
        f"lefthook exec at line {min(lefthook_exec_indices) + 1}."
    )
