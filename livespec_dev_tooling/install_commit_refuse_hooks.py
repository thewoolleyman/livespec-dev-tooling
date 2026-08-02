"""install_commit_refuse_hooks — install the canonical livespec commit-refuse hook.

Writes the canonical commit-refuse hook body to the primary checkout's
shared hooks directory at `<git-common-dir>/hooks/pre-commit`,
`<git-common-dir>/hooks/pre-push`, AND `<git-common-dir>/hooks/commit-msg`,
each made executable. Resolving the target via `git rev-parse
--git-common-dir` means the install lands in the PRIMARY's shared hooks
directory even when invoked from a linked worktree (every worktree's
hook firing reads that same shared directory).

Structural mechanism (armed on install): the installed body refuses the
operation whenever the repository's git-dir equals its git-common-dir —
the structural signature of a real primary checkout (a linked worktree's
git-dir is `<common-dir>/worktrees/<name>`, which differs).

POSITIVE-LOCATION mechanism (per `livespec/SPECIFICATION/
non-functional-requirements.md` section "Worktree root and mise trust"): being a
linked worktree is NOT sufficient to proceed. The body additionally
enforces an allow-list — a worktree under the repository's git dir
(tooling-internal, e.g. beads' `.git/beads-worktrees/*`) or under
`$HOME/.worktrees` delegates; anything else is refused. That single
allow-list satisfies both clauses of the invariant: whatever sits inside a
clone is by construction not under the sanctioned root, so "never inside a
clone" needs no separate nested-path test.

HONEST LIMIT: git has no `pre-worktree-add` hook, so location enforcement
fires at the first COMMIT, after the offending directory already exists.
It cannot prevent creation. What it converts is a silent, long-lived
violation into an immediate, actionable refusal — that is the whole of the
promise, and it should not be overstated.

This RETIRES
the older `livespec.primaryPath` git-config mechanism: there is no config
to set and so no fail-open window between clone and arming step. The
single declared opt-out is the `livespec.sandboxExempt=true` git config,
read inside the hook body (the Exemption slot of the Conformance
Pattern's concern #1 Worktree-discipline, per
`livespec/SPECIFICATION/non-functional-requirements.md`
section "Conformance Pattern").

The canonical body ships as the module-level `CANONICAL_HOOK_BODY`
string constant in THIS module so it travels in the wheel: only the
`livespec_dev_tooling/` package is packaged, with no `data/` resource
directory, so embedding the body as a Python string is the wheel-safe
carrier (no package-data config, no data-file resource). This module is
the SINGLE source of truth for the canonical body: `just bootstrap`, the
`just install-commit-refuse-hooks` recipe, and CI all install it by
invoking this installer, so there is no second copy to drift. The
structural body it ships differs from the retired
`git rev-parse --show-toplevel` / `livespec.primaryPath` legacy body
(no longer carried in the repo); the verifier still ACCEPTS that legacy
body so a repo that has not re-bootstrapped stays green during the fleet
migration.

CLI:
    python -m livespec_dev_tooling.install_commit_refuse_hooks
        Install (or idempotently re-install) the canonical hook at the
        primary checkout's shared hooks directory. Exits 0 on success.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stdout.write` / `sys.stderr.write`.
"""

from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "CANONICAL_HOOK_BODY",
    "install_hooks",
    "main",
]


# The canonical commit-refuse hook body. Embedded here as the wheel-safe
# carrier (see the module docstring). The body MUST carry the literal
# substrings the doctor invariant fingerprints — `# livespec
# commit-refuse hook`, `git rev-parse --git-common-dir`, and `exit 1`
# (per `livespec/SPECIFICATION/contracts.md`
# section "`primary-checkout-commit-refuse-hook-installed`").
CANONICAL_HOOK_BODY = """#!/bin/sh
# livespec commit-refuse hook — refuses commits/pushes at the primary checkout,
# and delegates to mise-managed lefthook everywhere else.
#
# STRUCTURAL refuse (no livespec.primaryPath arming step): a primary checkout
# has `git rev-parse --git-dir` == `git rev-parse --git-common-dir`; a secondary
# worktree's git-dir is `.git/worktrees/<name>` while its git-common-dir is the
# primary's `.git`, so the two differ and the refuse branch is skipped. The hook
# is therefore ARMED ON INSTALL — there is no config key to set and so no
# fail-open window. This supersedes the livespec.primaryPath mechanism, which
# failed OPEN whenever its arming step was missed (the console-incident root
# cause: an installed-but-unarmed hook reads as protected but silently no-ops).
#
# SANDBOX EXEMPTION: a Fabro sandbox is a fresh FULL clone (structurally a
# primary) that legitimately commits during Red-Green-Replay. Its prepare step
# sets `git config livespec.sandboxExempt true`, an EXPLICIT, DECLARED marker
# this hook reads; with it set the refuse branch is skipped so in-sandbox
# commits proceed (and the lefthook delegation below still fires the RGR gates).
# This is the Exemption slot of the Conformance Pattern's concern #1
# Worktree-discipline (livespec core non-functional-requirements
# §"Conformance Pattern"): a variation point is a marker the hook reads, never
# an incidental fail-open side effect.
#
# The recognized canonical fingerprint (per livespec-dev-tooling's
# primary_checkout_commit_refuse_hook_installed check) is the marker comment
# `# livespec commit-refuse hook` + a `git rev-parse --git-common-dir`
# invocation + an `exit 1` branch. The fingerprint match is substring-based and
# tolerant of portable-shell rewrites; it also still accepts the legacy
# `git rev-parse --show-toplevel` body during the fleet migration.
#
# `--no-auto-install` is critical: lefthook's auto-sync would otherwise back up
# this canonical body to `<name>.old` and replace it with its PATH-searching
# standard wrapper (which silently no-ops in an off-PATH hook shell AND loses
# the refuse-at-primary branch). Disabling the sync attempt eliminates both the
# `sync hooks: ❌` warning noise and the clobber risk.

# git injects GIT_DIR=<gitdir> (plus GIT_INDEX_FILE/GIT_WORK_TREE/GIT_PREFIX)
# into the hook environment when a hook fires inside a worktree. Clear them
# FIRST so BOTH the structural primary detection below AND the lefthook
# delegation resolve the repo from the current working directory (the worktree
# root). Leaving GIT_DIR set also makes lefthook misread the repo as bare and
# write core.bare=true into the shared .git/config, corrupting every checkout
# that shares it (root cause li-iroguc).
unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX

git_dir="$(git rev-parse --git-dir 2>/dev/null || true)"
common_dir="$(git rev-parse --git-common-dir 2>/dev/null || true)"
sandbox_exempt="$(git config --get livespec.sandboxExempt || true)"
if [ -n "$git_dir" ] && [ "$git_dir" = "$common_dir" ] && [ "$sandbox_exempt" != "true" ]; then
  echo "livespec: refusing commit/push at primary checkout; use a worktree" >&2
  exit 1
fi

# POSITIVE-LOCATION enforcement: every worktree lives under the per-user root
# `$HOME/.worktrees/<repo>/<branch>`. This is an ALLOW-LIST, not a nested-path
# test: anything inside a clone is by construction NOT under the sanctioned
# root, so "never inside a clone" falls out for free and no primary-root prefix
# computation is needed.
#
# Two arms allow. (1) TOOLING-INTERNAL: worktrees under the repo's git dir —
# beads' own `.git/beads-worktrees/*` sync worktrees live there by design, and
# refusing them would break the tool that maintains the ledger. (2) SANCTIONED:
# anything under `$HOME/.worktrees`, matching the single definition the
# `worktree-root-mise-trust` obligation row already uses, so the hook and that
# row can never disagree about what "sanctioned" means.
#
# JANITOR CONFIGURATION: orchestrator janitor worktrees under the sanctioned
# root are allowed by arm (2), which is where they live today. Janitors created
# INSIDE a clone's working tree are UNSUPPORTED — the hook sees only a path and
# cannot authenticate janitor identity from it, so any carve-out wide enough to
# admit them would readmit every other in-clone worktree and reopen the
# invariant. Unsupported-with-rationale is the honest answer; a broad bypass is
# not.
#
# `pwd -P` canonicalizes physically so a worktree reached through a symlinked
# path yields the same verdict as its real path.
#
# HONEST LIMIT: git has no `pre-worktree-add` hook, so this fires at the first
# COMMIT — after the offending directory already exists. It cannot prevent
# creation. It converts a silent, long-lived violation into an immediate,
# actionable refusal; that is the whole promise, and it is not more than that.
#
# Skipped entirely when `sandbox_exempt` is true: an exempt primary
# deliberately falls through the arm above, and must not be refused here.
# Named `sanctioned_dir`/`common_abs`, NOT `git_dir`, so the values read at the
# top of this hook are never shadowed.
if [ "$sandbox_exempt" != "true" ]; then
  common_abs="$(cd "$common_dir" 2>/dev/null && pwd -P || true)"
  this_root="$(cd "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null && pwd -P || true)"
  sanctioned_dir="$(cd "$HOME/.worktrees" 2>/dev/null && pwd -P || echo "$HOME/.worktrees")"
  if [ -n "$this_root" ]; then
    case "$this_root/" in
      "$common_abs"/*) ;;
      "$sanctioned_dir"/*) ;;
      *)
        echo "livespec: refusing commit from a worktree outside the sanctioned root" >&2
        echo "  this worktree:  $this_root" >&2
        echo "  sanctioned:     $HOME/.worktrees/<repo>/<branch>" >&2
        sanctioned_hint="$HOME/.worktrees/<repo>/<branch>"
        echo "  to fix:         git worktree move '$this_root' '$sanctioned_hint'" >&2
        exit 1
        ;;
    esac
  fi
fi

# Delegate to lefthook at worktrees (and in declared-exempt sandboxes) so the
# repo's existing pre-commit / pre-push / commit-msg gates fire. The hook-name
# is derived from the basename of $0 so the same script serves every hook.
hook_name="$(basename "$0")"
exec mise exec -- lefthook run --no-auto-install "$hook_name" "$@"
"""


_HOOK_NAMES: tuple[str, ...] = ("pre-commit", "pre-push", "commit-msg")


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger("install_commit_refuse_hooks")


def _git_common_dir(*, cwd: Path) -> Path:
    """Return the absolute path to the `.git` common directory for `cwd`.

    Uses `git rev-parse --git-common-dir`. Invoked from a primary the
    command returns `.git` (relative); invoked from a linked worktree it
    returns the primary's `.git` (absolute). Either way this resolves to
    the PRIMARY's shared `.git/`, so the hooks land in the directory that
    every worktree's hook firing reads. Uses `check=True` so a failed
    invocation raises (a bug — the installer is only ever run inside a
    repo) rather than silently returning a sentinel.
    """
    completed = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--git-common-dir"],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    candidate = Path(completed.stdout.strip())
    if candidate.is_absolute():
        return candidate
    return (cwd / candidate).resolve()


def install_hooks(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Install the canonical commit-refuse hook at the primary's hooks dir.

    Writes `CANONICAL_HOOK_BODY` to `<git-common-dir>/hooks/<name>` for
    each of pre-commit, pre-push, and commit-msg, then sets the
    executable bit. Idempotent: re-running overwrites with the identical
    canonical body. Worktree-safe: the common-dir resolution targets the
    primary's shared `.git/hooks/` even when `cwd` is a linked worktree.
    Returns 0 on success.
    """
    hooks_dir = _git_common_dir(cwd=cwd) / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    for hook_name in _HOOK_NAMES:
        hook_path = hooks_dir / hook_name
        _ = hook_path.write_text(CANONICAL_HOOK_BODY, encoding="utf-8")
        current_mode = hook_path.stat().st_mode
        hook_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        log.info(
            "installed canonical commit-refuse hook",
            hook=hook_name,
            path=str(hook_path),
        )
    return 0


def main() -> int:
    log = _configure_logger()
    return install_hooks(cwd=Path.cwd(), log=log)


if __name__ == "__main__":
    raise SystemExit(main())
