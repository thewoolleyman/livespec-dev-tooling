"""Outside-in test for `livespec_dev_tooling/install_commit_refuse_hooks.py`.

The installer writes the canonical livespec commit-refuse hook body to
the primary checkout's shared `.git/hooks/{pre-commit,pre-push,commit-msg}`,
each executable, resolving the target via `git rev-parse --git-common-dir`
so it lands in the PRIMARY's shared hooks dir even when invoked from a
linked worktree.

The installed body is the STRUCTURAL, armed-on-install commit-refuse
hook (per `livespec/SPECIFICATION/non-functional-requirements.md`
section "Primary-checkout commit-refuse hook" and section "Worktree root and mise
trust"). It enforces a POSITIVE-LOCATION allow-list:

- a PRIMARY checkout (git-dir == git-common-dir) refuses, UNLESS
  `livespec.sandboxExempt=true`, in which case it delegates;
- a TOOLING-INTERNAL worktree under the repository's git dir (beads'
  own `.git/beads-worktrees/*` sync worktrees) delegates;
- a SANCTIONED worktree under `$HOME/.worktrees` delegates;
- ANY OTHER linked worktree — nested inside a clone, or a peer of it —
  is REFUSED. A linked worktree no longer delegates merely by virtue of
  being linked; its LOCATION decides.

The installer also OWNS THE WHOLE hooks directory, not just the three
names it writes: after installing them it sweeps the same directory and
deletes every other executable that reaches lefthook without the
canonical `unset GIT_DIR …` line — lefthook's stock `call_lefthook`
wrappers, which `lefthook install` leaves behind for every hook name it
has ever been asked to manage (livespec-dev-tooling-x2ju4a).

The body also carries the FACTORY-PROVENANCE gate
(livespec-dev-tooling-pxsr7w), AND-ed in front of the Red-Green-Replay
logic the lefthook delegation runs: at `commit-msg` — where the message
file exists — it reads the `livespec.factoryRunId` marker and hands the
decision to `livespec_dev_tooling.factory_provenance_gate`. It fires in a
WORKTREE as well as at a declared-exempt sandbox, because hand-cranking
happens in host worktrees and every refuse branch above it has already
exited for the locations that may not commit at all. Only the gate's own
exit code 9 refuses; every other code falls through, so a defective gate
cannot become a fleet-wide commit outage.

The installer is exercised IN-PROCESS (`main()` with
`monkeypatch.chdir`) — no Python subprocess spawn (this test is not on
the `subprocess_spawn_allowlist`). The installed hook body itself is
exercised by invoking the script via `sh` (a shell, not a Python child),
with a stub `mise` on PATH standing in for both mise-mediated calls — the
lefthook delegation and the gate — so each terminates deterministically
and the stub's exit code is the gate's verdict.
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


# lefthook's stock wrapper, abridged to the shape that makes it a hazard: it
# reaches `lefthook` (so it IS an entry point), it dispatches `lefthook run
# <name>` with no `--no-auto-install`, and it never clears the GIT_DIR family
# git injects into a hook firing inside a linked worktree. The real article is
# ~70 lines of interpreter-hunting `elif`s; none of them change the verdict.
_STOCK_LEFTHOOK_WRAPPER = """#!/bin/sh

if [ "$LEFTHOOK" = "0" ]; then
  exit 0
fi

call_lefthook()
{
  if test -n "$LEFTHOOK_BIN"
  then
    "$LEFTHOOK_BIN" "$@"
  elif lefthook -h >/dev/null 2>&1
  then
    lefthook "$@"
  else
    echo "Can't find lefthook in PATH"
  fi
}

call_lefthook run "prepare-commit-msg" "$@"
"""


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


def _init_primary_with_worktree_at(*, tmp_path: Path, worktree: Path) -> Path:
    """Create a primary checkout and add a linked worktree at `worktree`."""
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    seed = primary / "seed.md"
    _ = seed.write_text("# seed\n", encoding="utf-8")
    _run_git(args=["add", "seed.md"], cwd=primary)
    _run_git(args=["commit", "--quiet", "-m", "fixture commit"], cwd=primary)
    _run_git(args=["branch", "feature/wip"], cwd=primary)
    worktree.parent.mkdir(parents=True, exist_ok=True)
    _run_git(args=["worktree", "add", str(worktree), "feature/wip"], cwd=primary)
    return primary


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

    The stub stands in for BOTH mise-mediated invocations the body makes:
    the `exec mise exec -- lefthook run ...` delegation and the
    `mise exec -- uv run ... factory_provenance_gate` call before it. It
    records its argv (when `MISE_CAPTURE_FILE` is set) and exits 0, so a
    hook that reaches either terminates cleanly without actually running
    mise, lefthook, or an interpreter.

    `MISE_STUB_EXIT` overrides that exit code, which is how the
    factory-provenance gate's verdict is driven: the hook reaches the gate
    only through this stub, so the stub IS the gate from the body's point
    of view.
    """
    bin_dir.mkdir(parents=True, exist_ok=True)
    mise = bin_dir / "mise"
    _ = mise.write_text(
        "#!/bin/sh\n"
        'if [ -n "$MISE_CAPTURE_FILE" ]; then printf \'%s\\n\' "$*" >> "$MISE_CAPTURE_FILE"; fi\n'
        'exit "${MISE_STUB_EXIT:-0}"\n',
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
    home: Path | None = None,
    stub_exit: int | None = None,
) -> subprocess.CompletedProcess[str]:
    """Invoke an installed hook script via `sh` with the stub mise on PATH.

    `home` overrides `$HOME` so a test can control the sanctioned worktree root
    (`<home>/.worktrees`) the hook derives, matching `_rows_local._worktree_root`.
    `stub_exit` drives the stub mise's exit code, which is the
    factory-provenance gate's verdict as the hook body sees it.
    """
    env = dict(os.environ)
    env["PATH"] = f"{fakebin}{os.pathsep}{env.get('PATH', '')}"
    if home is not None:
        env["HOME"] = str(home)
    if capture_file is not None:
        env["MISE_CAPTURE_FILE"] = str(capture_file)
    if stub_exit is not None:
        env["MISE_STUB_EXIT"] = str(stub_exit)
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
    """(b) a SANCTIONED worktree (under `$HOME/.worktrees`) delegates, not refuses.

    Being a linked worktree is not sufficient — location decides. See the
    nested/peer tests for the refusing cases.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    home = tmp_path / "home"
    worktree = home / ".worktrees" / "project" / "feature-wip"
    primary = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    monkeypatch.chdir(primary)
    assert main() == 0
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    hook = primary / ".git" / "hooks" / "pre-commit"

    result = _run_installed_hook(hook_path=hook, cwd=worktree, fakebin=fakebin, home=home)

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
    home = tmp_path / "home"
    worktree = home / ".worktrees" / "project" / "feature-wip"
    primary = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
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
        home=home,
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


def test_installed_hook_refuses_nested_worktree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worktree NESTED inside the primary's working tree is refused (clause 1)."""
    _scrub_git_env(monkeypatch=monkeypatch)
    home = tmp_path / "home"
    primary = tmp_path / "project"
    worktree = primary / ".claude" / "worktrees" / "nested"
    primary_created = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    monkeypatch.chdir(primary_created)
    assert main() == 0
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    hook = primary_created / ".git" / "hooks" / "pre-commit"

    result = _run_installed_hook(hook_path=hook, cwd=worktree, fakebin=fakebin, home=home)

    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "refusing" in result.stderr


def test_installed_hook_refuses_peer_worktree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PEER worktree — outside the clone, outside `~/.worktrees` — is refused.

    This is the case the specification names explicitly and the case a
    nested-only rule misses entirely.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    home = tmp_path / "home"
    worktree = tmp_path / "project-peer"
    primary = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    monkeypatch.chdir(primary)
    assert main() == 0
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    hook = primary / ".git" / "hooks" / "pre-commit"

    result = _run_installed_hook(hook_path=hook, cwd=worktree, fakebin=fakebin, home=home)

    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "refusing" in result.stderr


def test_installed_hook_allows_tooling_internal_worktree(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A worktree under the primary's git dir (beads-sync shape) is ALLOWED."""
    _scrub_git_env(monkeypatch=monkeypatch)
    home = tmp_path / "home"
    primary = tmp_path / "project"
    worktree = primary / ".git" / "beads-worktrees" / "beads-sync"
    primary_created = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    monkeypatch.chdir(primary_created)
    assert main() == 0
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    hook = primary_created / ".git" / "hooks" / "pre-commit"

    result = _run_installed_hook(hook_path=hook, cwd=worktree, fakebin=fakebin, home=home)

    assert result.returncode == 0, (result.stdout, result.stderr)
    assert "refusing" not in result.stderr


def test_refusal_remedy_uses_plain_git_and_names_no_recipe() -> None:
    """The refusal remedy must work before slice D wires any `just` recipe.

    B ships BEFORE D, so `just install-worktree-pack` / `just worktree-create`
    name recipes absent from most fleet repos at that moment. The remedy must
    stand on plain git.
    """
    assert "git worktree move" in CANONICAL_HOOK_BODY
    refuse_section = CANONICAL_HOOK_BODY.split("sanctioned root", 1)[-1]
    assert "install-worktree-pack" not in refuse_section
    assert "worktree-create" not in refuse_section


def test_main_removes_a_stock_lefthook_wrapper_it_does_not_install(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The installer owns the WHOLE hooks directory, not just the three names it writes.

    Reproduces the observed defect (livespec-dev-tooling-x2ju4a): on 2026-09-06
    `/data/projects/livespec/.git/hooks/prepare-commit-msg` was still
    lefthook's stock `call_lefthook` wrapper, mtime three months older than the
    canonical hooks beside it. `lefthook install` writes one of those per hook
    name it has ever been asked to manage and nothing removes them, so the
    stale one kept firing on every commit and every cherry-pick — leaking the
    GIT_DIR family git injects inside a linked worktree, and calling `lefthook
    run` without `--no-auto-install`.

    The canonical three are asserted intact in the same test: a sweep that
    removed the very hooks it had just written would satisfy the first
    assertion perfectly.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    hooks_dir = primary / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    stale = hooks_dir / "prepare-commit-msg"
    _ = stale.write_text(_STOCK_LEFTHOOK_WRAPPER, encoding="utf-8")
    stale.chmod(0o755)
    monkeypatch.chdir(primary)

    rc = main()

    assert rc == 0
    assert not stale.exists(), "the stock lefthook wrapper survived the installer"
    for name in _HOOK_NAMES:
        hook = hooks_dir / name
        assert hook.is_file(), f"{name} was swept away by its own installer"
        assert hook.read_text(encoding="utf-8") == CANONICAL_HOOK_BODY


def test_main_keeps_hooks_that_cannot_be_a_lefthook_entry_point(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The sweep removes lefthook entry points, NOT every file in the hooks directory.

    A repo-local hook that never mentions lefthook is somebody's deliberate
    configuration and nothing here has a claim on it. A wrapper without the
    execute bit is inert — git runs a hook only when it is an executable
    regular file — so deleting it would be a mutation with no hazard behind it.
    Both survive, and the sweep is thereby shown to be keyed on the property
    that makes a file dangerous rather than on its being in the way.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    primary = tmp_path / "project"
    _init_repo(repo=primary)
    hooks_dir = primary / ".git" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    unrelated = hooks_dir / "post-commit"
    _ = unrelated.write_text("#!/bin/sh\n# a repo-local hook that delegates to nothing\nexit 0\n")
    unrelated.chmod(0o755)
    inert = hooks_dir / "prepare-commit-msg"
    _ = inert.write_text(_STOCK_LEFTHOOK_WRAPPER, encoding="utf-8")
    inert.chmod(0o644)
    monkeypatch.chdir(primary)

    rc = main()

    assert rc == 0
    assert unrelated.is_file(), "an unrelated repo-local hook was deleted"
    assert inert.is_file(), "a non-executable, non-firing wrapper was deleted"


def test_installed_hook_symlinked_path_yields_identical_verdict(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The SAME sanctioned worktree yields the same verdict via a symlinked path.

    `/data/projects` and `/home/ubuntu/workspace` are the same trees on this
    host, so a worktree can be reached through either. The verdict must not
    depend on which path it was reached through — hence physical
    canonicalization before the prefix comparison. Both invocations must ALLOW.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    real_home = tmp_path / "real-home"
    worktree = real_home / ".worktrees" / "project" / "feature-wip"
    primary = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    monkeypatch.chdir(primary)
    assert main() == 0
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    hook = primary / ".git" / "hooks" / "pre-commit"

    link_home = tmp_path / "linked-home"
    link_home.symlink_to(real_home, target_is_directory=True)
    linked_worktree = link_home / ".worktrees" / "project" / "feature-wip"

    physical = _run_installed_hook(hook_path=hook, cwd=worktree, fakebin=fakebin, home=real_home)
    through_symlink = _run_installed_hook(
        hook_path=hook, cwd=linked_worktree, fakebin=fakebin, home=link_home
    )

    assert physical.returncode == through_symlink.returncode, (
        physical.returncode,
        through_symlink.returncode,
        through_symlink.stderr,
    )
    assert ("refusing" in physical.stderr) == ("refusing" in through_symlink.stderr)
    assert physical.returncode == 0, (physical.stdout, physical.stderr)
    assert "refusing" not in through_symlink.stderr


def _stage_product_py(*, worktree: Path) -> None:
    """Stage a product `.py` in `worktree`, the gate's cheap scope pre-filter."""
    impl = worktree / "pkg" / "impl.py"
    impl.parent.mkdir(parents=True, exist_ok=True)
    _ = impl.write_text("x = 1\n", encoding="utf-8")
    _run_git(args=["add", "pkg/impl.py"], cwd=worktree)


def _captured_lines(*, capture_file: Path) -> list[str]:
    """The stub mise's recorded argv lines, in invocation order."""
    return capture_file.read_text(encoding="utf-8").strip().splitlines()


def test_canonical_body_carries_the_factory_provenance_gate() -> None:
    """The body reads the marker, delegates the scope question, and refuses on 9 alone.

    Locks the four load-bearing pieces of the gate branch: the
    `livespec.factoryRunId` marker read, the delegation to the module
    that owns the `derive_source_prefixes` classification, the
    `Factory-Override` exception the refusal names, and the placement —
    BEFORE the lefthook exec, so the gate is AND-ed in front of the
    Red-Green-Replay logic lefthook runs rather than replacing any of it.
    """
    assert "git config --get livespec.factoryRunId" in CANONICAL_HOOK_BODY
    assert "livespec_dev_tooling.factory_provenance_gate" in CANONICAL_HOOK_BODY
    assert "Factory-Override" in CANONICAL_HOOK_BODY

    lines = CANONICAL_HOOK_BODY.splitlines()
    gate_indices = [i for i, line in enumerate(lines) if "factory_provenance_gate" in line]
    exec_indices = [i for i, line in enumerate(lines) if "lefthook run --no-auto-install" in line]

    assert gate_indices, "CANONICAL_HOOK_BODY no longer invokes the factory-provenance gate"
    assert min(gate_indices) < min(exec_indices), (
        "the factory-provenance gate must run BEFORE the lefthook delegation; "
        f"gate at line {min(gate_indices) + 1}, lefthook exec at line {min(exec_indices) + 1}."
    )


def test_installed_commit_msg_hook_gates_a_worktree_commit(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate fires IN A WORKTREE, not only at the primary checkout.

    Hand-cranking happens in host worktrees, so the worktree path is
    exactly what must be gated — and the pre-existing refuse branches
    deliberately skip it.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    home = tmp_path / "home"
    worktree = home / ".worktrees" / "project" / "feature-wip"
    primary = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    monkeypatch.chdir(primary)
    assert main() == 0
    _stage_product_py(worktree=worktree)
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    capture = tmp_path / "mise-args.txt"
    msg_file = worktree / "COMMIT_EDITMSG_fixture"
    _ = msg_file.write_text("feat: subject line\n", encoding="utf-8")
    hook = primary / ".git" / "hooks" / "commit-msg"

    result = _run_installed_hook(
        hook_path=hook,
        cwd=worktree,
        fakebin=fakebin,
        capture_file=capture,
        extra_args=(str(msg_file),),
        home=home,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    lines = _captured_lines(capture_file=capture)
    assert "livespec_dev_tooling.factory_provenance_gate" in lines[0], lines
    assert str(msg_file) in lines[0], lines
    assert "lefthook run" in lines[1], lines


def test_installed_commit_msg_hook_refuses_on_the_gates_refuse_code(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit code 9 from the gate — and only 9 — turns into a refusal.

    The stub mise IS the gate from the hook's point of view (the hook
    reaches it through `mise exec -- uv run`), so driving the stub's exit
    code drives the branch without a real interpreter.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    home = tmp_path / "home"
    worktree = home / ".worktrees" / "project" / "feature-wip"
    primary = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    monkeypatch.chdir(primary)
    assert main() == 0
    _stage_product_py(worktree=worktree)
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    msg_file = worktree / "COMMIT_EDITMSG_fixture"
    _ = msg_file.write_text("feat: subject line\n", encoding="utf-8")
    hook = primary / ".git" / "hooks" / "commit-msg"

    result = _run_installed_hook(
        hook_path=hook,
        cwd=worktree,
        fakebin=fakebin,
        extra_args=(str(msg_file),),
        home=home,
        stub_exit=9,
    )

    assert result.returncode == 1, (result.stdout, result.stderr)
    assert "refusing" in result.stderr
    assert "Factory-Override" in result.stderr


def test_installed_commit_msg_hook_proceeds_on_any_other_gate_exit(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAIL-OPEN: a gate that crashed, or an unresolvable module, must not block the commit.

    Exit 1 is what `python -m` gives for an unimportable module — the
    shape a worktree whose lock predates the gate produces — and it must
    fall through to the lefthook delegation, not refuse. The delegation
    inherits the same stub exit, which is why the hook's own status is
    the stub's rather than 0.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    home = tmp_path / "home"
    worktree = home / ".worktrees" / "project" / "feature-wip"
    primary = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    monkeypatch.chdir(primary)
    assert main() == 0
    _stage_product_py(worktree=worktree)
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    capture = tmp_path / "mise-args.txt"
    msg_file = worktree / "COMMIT_EDITMSG_fixture"
    _ = msg_file.write_text("feat: subject line\n", encoding="utf-8")
    hook = primary / ".git" / "hooks" / "commit-msg"

    result = _run_installed_hook(
        hook_path=hook,
        cwd=worktree,
        fakebin=fakebin,
        capture_file=capture,
        extra_args=(str(msg_file),),
        home=home,
        stub_exit=1,
    )

    assert "refusing" not in result.stderr, (result.stdout, result.stderr)
    assert "lefthook run" in _captured_lines(capture_file=capture)[1]


def test_installed_commit_msg_hook_skips_the_gate_with_no_python_staged(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit staging no `.py` at all can never be in scope, so the interpreter is skipped."""
    _scrub_git_env(monkeypatch=monkeypatch)
    home = tmp_path / "home"
    worktree = home / ".worktrees" / "project" / "feature-wip"
    primary = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    monkeypatch.chdir(primary)
    assert main() == 0
    note = worktree / "docs" / "note.md"
    note.parent.mkdir(parents=True, exist_ok=True)
    _ = note.write_text("# note\n", encoding="utf-8")
    _run_git(args=["add", "docs/note.md"], cwd=worktree)
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    capture = tmp_path / "mise-args.txt"
    msg_file = worktree / "COMMIT_EDITMSG_fixture"
    _ = msg_file.write_text("docs: subject line\n", encoding="utf-8")
    hook = primary / ".git" / "hooks" / "commit-msg"

    result = _run_installed_hook(
        hook_path=hook,
        cwd=worktree,
        fakebin=fakebin,
        capture_file=capture,
        extra_args=(str(msg_file),),
        home=home,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    lines = _captured_lines(capture_file=capture)
    assert len(lines) == 1, lines
    assert "lefthook run" in lines[0], lines


def test_installed_commit_msg_hook_gates_a_marker_commit_staging_no_python(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A commit made UNDER the marker enters the gate whatever it stages.

    Its provenance is worth recording either way — that is what puts the
    `Factory-Run-Id` trailer on every commit of a factory run, not only
    on the ones carrying product `.py`.
    """
    _scrub_git_env(monkeypatch=monkeypatch)
    home = tmp_path / "home"
    worktree = home / ".worktrees" / "project" / "feature-wip"
    primary = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    _run_git(args=["config", "livespec.factoryRunId", "01M29GFWMRMEB3PYZVYKEG7EE6"], cwd=primary)
    monkeypatch.chdir(primary)
    assert main() == 0
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    capture = tmp_path / "mise-args.txt"
    msg_file = worktree / "COMMIT_EDITMSG_fixture"
    _ = msg_file.write_text("docs: subject line\n", encoding="utf-8")
    hook = primary / ".git" / "hooks" / "commit-msg"

    result = _run_installed_hook(
        hook_path=hook,
        cwd=worktree,
        fakebin=fakebin,
        capture_file=capture,
        extra_args=(str(msg_file),),
        home=home,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    lines = _captured_lines(capture_file=capture)
    assert "livespec_dev_tooling.factory_provenance_gate" in lines[0], lines
    assert "01M29GFWMRMEB3PYZVYKEG7EE6" in lines[0], lines


def test_installed_pre_commit_hook_does_not_invoke_the_gate(
    *, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate is a commit-msg member: at pre-commit there is no message to read."""
    _scrub_git_env(monkeypatch=monkeypatch)
    home = tmp_path / "home"
    worktree = home / ".worktrees" / "project" / "feature-wip"
    primary = _init_primary_with_worktree_at(tmp_path=tmp_path, worktree=worktree)
    monkeypatch.chdir(primary)
    assert main() == 0
    _stage_product_py(worktree=worktree)
    fakebin = _make_fake_mise(bin_dir=tmp_path / "fakebin")
    capture = tmp_path / "mise-args.txt"
    hook = primary / ".git" / "hooks" / "pre-commit"

    result = _run_installed_hook(
        hook_path=hook,
        cwd=worktree,
        fakebin=fakebin,
        capture_file=capture,
        home=home,
    )

    assert result.returncode == 0, (result.stdout, result.stderr)
    lines = _captured_lines(capture_file=capture)
    assert len(lines) == 1, lines
    assert "lefthook run" in lines[0], lines
