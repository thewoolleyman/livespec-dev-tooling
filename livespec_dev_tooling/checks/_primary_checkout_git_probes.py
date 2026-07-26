"""_primary_checkout_git_probes — git rev-parse / git config probes for the hook check.

Extracted from `primary_checkout_commit_refuse_hook_installed.py` so
the parent check stays under the file-LLOC ceiling
(fleet-check-coverage). This sibling carries ONLY the project-agnostic
git-state probes the parent's `main()` sequences: is-inside-work-tree,
is-git-repo-at-all, core-bare-flag, git-common-dir, and
work-tree-root. Each shells out to `git` against a caller-supplied
`cwd`; none reads the parent's constants or the canonical bodies.

The leading underscore in the filename marks this as a private helper
module; its behavior is exercised through the parent check's
subprocess contract and its own mirror-paired test.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

__all__: list[str] = [
    "core_bare_is_true",
    "git_common_dir",
    "is_git_repo_at_all",
    "is_inside_work_tree",
    "sandbox_exempt_is_true",
    "work_tree_root",
]


def is_inside_work_tree(*, cwd: Path) -> bool:
    """Return True when `cwd` is inside a git working tree.

    Uses `git rev-parse --is-inside-work-tree`. The caller invokes this
    only after `is_git_repo_at_all` has confirmed a surrounding repo, so
    the command always exits `0` and prints `true`/`false`; a `false`
    (e.g., cwd is inside the `.git` directory itself, which is a git
    context that is NOT a working tree) — or any non-`true` stdout —
    yields False without a dedicated returncode branch.
    """
    completed = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() == "true"


def is_git_repo_at_all(*, cwd: Path) -> bool:
    """Return True when `cwd` is inside ANY git repository (work tree OR bare).

    Uses `git rev-parse --git-dir`, which exits `0` for both a normal
    working-tree clone and a `core.bare = true` repository. Returns False
    when the command exits non-zero (no surrounding repo). This is the
    discriminator that lets the check distinguish a genuinely-not-a-repo
    directory (skip) from a bare-flag regression (fail).
    """
    completed = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def core_bare_is_true(*, cwd: Path) -> bool:
    """Return True when `git config --get core.bare` resolves to `true`.

    The caller MUST have verified `cwd` is inside a git repository via
    `is_git_repo_at_all` first. When the key is unset, `git config --get
    core.bare` exits non-zero AND prints nothing, so the empty stdout
    compares unequal to `"true"` — git's default `false` yields False here
    without a dedicated returncode branch.
    """
    completed = subprocess.run(
        ["git", "config", "--get", "core.bare"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() == "true"


def sandbox_exempt_is_true(*, cwd: Path) -> bool:
    """Return True when `git config --get livespec.sandboxExempt` resolves to `true`.

    The DECLARED sandbox-exemption marker, set by the Fabro sandbox's prepare
    step and already read by `CANONICAL_HOOK_BODY` in two places (the
    refuse-at-primary arm and the positive-location arm). Reading it here lets
    the pack-presence arm honour the same declaration rather than assert a
    property that cannot hold in a fresh, un-bootstrapped clone.

    Same shape as `core_bare_is_true`: an unset key exits non-zero AND prints
    nothing, so empty stdout compares unequal to `"true"` and yields False
    without a dedicated returncode branch. Only the literal `true` exempts —
    the marker is a declaration, not the mere presence of a key.
    """
    completed = subprocess.run(
        ["git", "config", "--get", "livespec.sandboxExempt"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() == "true"


def git_common_dir(*, cwd: Path) -> Path:
    """Return the absolute path to the `.git` common directory for `cwd`.

    Uses `git rev-parse --git-common-dir`. The caller MUST have verified
    `cwd` is inside a git working tree first; this uses `check=True` so a
    failed invocation raises rather than silently returning a sentinel.
    The common dir is the primary's `.git/` (shared by secondary
    worktrees), so reading `<common-dir>/hooks/` against any worktree
    resolves to the primary's hooks directory.
    """
    completed = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    candidate = Path(completed.stdout.strip())
    if candidate.is_absolute():
        return candidate
    return (cwd / candidate).resolve()


def work_tree_root(*, cwd: Path) -> Path:
    """Return the absolute path to the git work-tree root for `cwd`.

    Uses `git rev-parse --show-toplevel`. The caller MUST have verified
    `cwd` is inside a git working tree first; this uses `check=True` so a
    failed invocation raises. The work-tree root anchors the
    no-vendored-copy scan.
    """
    completed = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(completed.stdout.strip())
