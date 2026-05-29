"""primary_checkout_commit_refuse_hook_installed — verify commit-refuse hook at primary.

Universal mechanical check ported from livespec's doctor-static
phase. Per `livespec/SPECIFICATION/contracts.md` §"Doctor
cross-boundary invariants" → §"`primary-checkout-commit-refuse-hook-installed`"
and `livespec/SPECIFICATION/non-functional-requirements.md`
§"Primary-checkout commit-refuse hook", every livespec-governed
primary checkout MUST install a `.git/hooks/pre-commit` AND a
`.git/hooks/pre-push` hook whose body refuses to run when invoked
at the primary checkout. The hook is a no-op at secondary
worktrees (whose `git rev-parse --show-toplevel` returns the
worktree's own path, not the primary's).

The contract supersedes the v091-v094 `core.bare = true` mechanism
(see `primary_checkout_bare_flag_set.py` in earlier releases). The
bare-flag mechanism caused stale-on-disk-read failures at primaries
that the hook mechanism does not.

Inputs are project-agnostic: the check reads `.git/hooks/pre-commit`
and `.git/hooks/pre-push` against the current working directory's
git common dir. No `[tool.livespec_dev_tooling]` role keys are
consumed (per the sibling spec's §"Shared check inventory"
partition criterion — this check is layout-independent).

Hook body recognition: the canonical body carries the stable marker
comment string `# livespec commit-refuse hook` AND invokes
`git rev-parse --show-toplevel` AND contains an `exit 1` branch.
The check verifies the presence of all three substrings (tolerant
fingerprint — survives portable-shell variations such as alternate
quoting or whitespace).

Exit codes:
- `0` — pass. Both `.git/hooks/pre-commit` and `.git/hooks/pre-push`
  exist, are executable, and contain the canonical fingerprint.
- `0` — skipped (cwd is not a git repository at all, or `git` is
  unavailable). Skipped is `0` so the check is a no-op in non-git
  environments rather than a false positive.
- `4` — fail. One or both hooks are missing, non-executable, or
  contain a non-canonical body (including the empty-file case).
  Corrective action: run the repo's documented bootstrap step
  (per `non-functional-requirements.md` §"Commit-refuse hook
  bootstrap procedure"), which idempotently installs the hook at
  both paths. The check MUST NOT distinguish at the contract level
  between "missing" and "non-canonical body" — both fire equally;
  both are corrected by the same bootstrap invocation. The narration
  names the specific failure mode for diagnostic clarity.
- `4` — fail. The repo IS a git repository but has `core.bare = true`
  set (`failure_mode` `core_bare_set`). This is the eliminated legacy
  bare-flag state (the v091-v094 mechanism the commit-refuse hook
  superseded): a bare repo is a git repo that is NOT a work tree, so
  the work-tree skip below would silently pass it. This check
  realizes the MAY in `livespec/SPECIFICATION/contracts.md`
  §"`primary-checkout-commit-refuse-hook-installed`" — "The doctor
  invariant MAY additionally surface a `fail` when `core.bare = true`
  is set on the primary, to catch the legacy-state case during the
  transition." The corrective action is to unset the flag and
  repopulate the working tree. This does NOT change the canonical
  upstream invariant (which stays a MAY); dev-tooling's impl chooses
  to realize it.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_CHECK_ID = "primary_checkout_commit_refuse_hook_installed"
_FAIL_EXIT = 4

# Stable marker comment that the canonical hook body MUST carry. Per
# `contracts.md` §"`primary-checkout-commit-refuse-hook-installed`":
# the canonical body is recognized via a marker comment string.
_CANONICAL_MARKER = "# livespec commit-refuse hook"

# Additional canonical fingerprint substrings — the body MUST invoke
# `git rev-parse --show-toplevel` AND contain an `exit 1` branch
# (the refuse-at-primary path). The tolerant fingerprint survives
# portable-shell variations.
_CANONICAL_TOPLEVEL_INVOCATION = "git rev-parse --show-toplevel"
_CANONICAL_REFUSE_EXIT = "exit 1"

_HOOK_NAMES: tuple[str, ...] = ("pre-commit", "pre-push")

# Failure-mode value for the legacy bare-flag regression — emitted on
# the dedicated `core.bare = true` fail branch (distinct from the
# per-hook `missing` / `not_executable` / `non_canonical_body` modes).
_CORE_BARE_FAILURE_MODE = "core_bare_set"


def _configure_logger() -> structlog.stdlib.BoundLogger:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    return structlog.get_logger(_CHECK_ID)


def _is_inside_work_tree(*, cwd: Path) -> bool:
    """Return True when `cwd` is inside a git working tree.

    Uses `git rev-parse --is-inside-work-tree`. The caller invokes
    this only after `_is_git_repo_at_all` has confirmed a surrounding
    repo, so the command always exits `0` and prints `true`/`false`;
    a `false` (e.g., cwd is inside the `.git` directory itself, which
    is a git context that is NOT a working tree) — or any non-`true`
    stdout — yields False without a dedicated returncode branch.
    """
    completed = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() == "true"


def _is_git_repo_at_all(*, cwd: Path) -> bool:
    """Return True when `cwd` is inside ANY git repository (work tree OR bare).

    Uses `git rev-parse --git-dir`, which exits `0` for both a normal
    working-tree clone and a `core.bare = true` repository (a bare repo
    is a git repo that is NOT a work tree). Returns False when the
    command exits non-zero (e.g., the directory has no surrounding
    repo). This is the discriminator that lets the check distinguish a
    genuinely-not-a-repo directory (skip) from a bare-flag regression
    (fail).
    """
    completed = subprocess.run(
        ["git", "rev-parse", "--git-dir"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode == 0


def _core_bare_is_true(*, cwd: Path) -> bool:
    """Return True when `git config --get core.bare` resolves to `true`.

    The caller MUST have verified `cwd` is inside a git repository via
    `_is_git_repo_at_all` first. When the key is unset, `git config
    --get core.bare` exits non-zero AND prints nothing, so the empty
    stdout compares unequal to `"true"` — git's default `false` yields
    False here without a dedicated returncode branch.
    """
    completed = subprocess.run(
        ["git", "config", "--get", "core.bare"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.stdout.strip() == "true"


def _git_common_dir(*, cwd: Path) -> Path:
    """Return the absolute path to the `.git` common directory for `cwd`.

    Uses `git rev-parse --git-common-dir`. The caller MUST have
    verified `cwd` is inside a git working tree via `_is_git_repo`
    first; this function relies on that precondition and uses
    `check=True` so a failed invocation raises rather than silently
    returning a sentinel value. The common dir is the primary's
    `.git/` (shared by secondary worktrees), so reading
    `<common-dir>/hooks/` against any worktree resolves to the
    primary's hooks directory.
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


def _hook_body_is_canonical(*, body: str) -> bool:
    """Return True when `body` contains every canonical fingerprint substring.

    Tolerant: substring presence (not exact equality) so portable-
    shell rewrites (alternate quoting, extra whitespace, additional
    diagnostic echoes) are accepted as long as the load-bearing
    elements remain.
    """
    return (
        _CANONICAL_MARKER in body
        and _CANONICAL_TOPLEVEL_INVOCATION in body
        and _CANONICAL_REFUSE_EXIT in body
    )


def _inspect_hook(
    *,
    hook_path: Path,
) -> tuple[bool, str]:
    """Return `(ok, failure_mode)` for a single hook path.

    `ok` is True only when the hook exists as a regular file, is
    executable by the current user, and its body matches the
    canonical fingerprint. `failure_mode` is one of:

    - `"missing"` — the hook file is absent or is not a regular file.
    - `"not_executable"` — the hook exists but the executable bit
      is unset for the current user (`os.access(path, os.X_OK)`).
    - `"non_canonical_body"` — the hook is executable but its body
      lacks one or more canonical fingerprint substrings (covers
      the empty-file case too — empty strings trivially miss every
      substring).
    - `""` (empty string) — the hook is correct; paired with
      `ok=True`.
    """
    if not hook_path.is_file():
        return False, "missing"
    if not os.access(hook_path, os.X_OK):
        return False, "not_executable"
    body = hook_path.read_text(encoding="utf-8")
    if not _hook_body_is_canonical(body=body):
        return False, "non_canonical_body"
    return True, ""


def main() -> int:
    log = _configure_logger()
    cwd = Path.cwd()
    if shutil.which("git") is None:
        log.warning(
            "git not on PATH; skipping primary-checkout-commit-refuse-hook-installed check",
            check_id=_CHECK_ID,
            hint="install git or invoke from a shell that exposes git on PATH",
        )
        return 0
    if not _is_git_repo_at_all(cwd=cwd):
        log.info(
            "cwd is not a git repository; skipping check",
            check_id=_CHECK_ID,
            cwd=str(cwd),
        )
        return 0
    if _core_bare_is_true(cwd=cwd):
        log.error(
            "primary-checkout-commit-refuse-hook-installed: hook failure",
            check_id=_CHECK_ID,
            status="fail",
            hook="",
            failure_mode=_CORE_BARE_FAILURE_MODE,
            hooks_dir="",
            hint=(
                "core.bare=true on the primary checkout — legacy bare-flag "
                "state; the commit-refuse-hook mechanism requires a "
                "non-bare working-tree clone. Run `git config --unset "
                "core.bare && git reset --hard origin/master` to repopulate "
                "the working tree, then run the documented bootstrap step "
                "(see livespec/SPECIFICATION/non-functional-requirements.md "
                '§"Commit-refuse hook bootstrap procedure")'
            ),
            path="",
            line=0,
        )
        return _FAIL_EXIT
    if not _is_inside_work_tree(cwd=cwd):
        log.info(
            "cwd is not inside a git working tree; skipping check",
            check_id=_CHECK_ID,
            cwd=str(cwd),
        )
        return 0
    common_dir = _git_common_dir(cwd=cwd)
    hooks_dir = common_dir / "hooks"
    failures: list[tuple[str, str]] = []
    for hook_name in _HOOK_NAMES:
        hook_path = hooks_dir / hook_name
        ok, failure_mode = _inspect_hook(hook_path=hook_path)
        if not ok:
            failures.append((hook_name, failure_mode))
    if not failures:
        return 0
    for hook_name, failure_mode in failures:
        log.error(
            "primary-checkout-commit-refuse-hook-installed: hook failure",
            check_id=_CHECK_ID,
            status="fail",
            hook=hook_name,
            failure_mode=failure_mode,
            hooks_dir=str(hooks_dir),
            hint=(
                "run the repo's documented bootstrap step "
                "(see livespec/SPECIFICATION/non-functional-requirements.md "
                '§"Commit-refuse hook bootstrap procedure") to idempotently '
                "install the canonical commit-refuse hook at both "
                "`.git/hooks/pre-commit` and `.git/hooks/pre-push`"
            ),
            path="",
            line=0,
        )
    return _FAIL_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
