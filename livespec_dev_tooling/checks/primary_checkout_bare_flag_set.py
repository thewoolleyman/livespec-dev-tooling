"""primary_checkout_bare_flag_set — every primary checkout has `core.bare = true`.

Universal mechanical check ported from livespec's doctor-static
phase. Per `livespec/SPECIFICATION/contracts.md` §"Doctor
cross-boundary invariants" → §"`primary-checkout-bare-flag-set`",
every livespec-governed primary checkout MUST have
`core.bare = true` set in its `.git/config`. Secondary worktrees
carry a standalone `.git` FILE pointing back to the bare repo and
are not inspected (the check reads `core.bare` via
`git config --get`, which by git's design resolves to the common
config, since `core.bare` is not in the worktree-config-allowed
key set).

Inputs are project-agnostic: the check reads `core.bare` against
the current working directory's git common dir. No
`[tool.livespec_dev_tooling]` role keys are consumed (per the
sibling spec's §"Shared check inventory" partition criterion —
this check is layout-independent).

Exit codes:
- `0` — pass. `core.bare = true` is set on the primary checkout.
- `0` — skipped (cwd is not a git repo, or `git` is unavailable).
  Skipped is `0` so the check is a no-op in non-git environments
  rather than a false positive.
- `4` — fail. `core.bare` is absent OR explicitly `false` on the
  primary checkout. Corrective action: `git config core.bare true`
  against the primary checkout. The check MUST NOT distinguish
  between absent and explicit-`false` — both are corrected by the
  same one-line invocation.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


_CHECK_ID = "primary_checkout_bare_flag_set"
_FAIL_EXIT = 4


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


def _is_git_repo(*, cwd: Path) -> bool:
    """Return True when `cwd` is inside a git working tree.

    Uses `git rev-parse --is-inside-work-tree`; returns False when
    the command exits non-zero (e.g., the directory has no
    surrounding repo).
    """
    completed = subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    return completed.stdout.strip() == "true"


def _read_core_bare(*, cwd: Path) -> str | None:
    """Return the `core.bare` config value as a string, or None when absent.

    `git config --get core.bare` exits 1 when the key is unset; we
    surface that as None so the caller treats absent and
    explicit-`false` identically per the cross-boundary invariant.
    """
    completed = subprocess.run(
        ["git", "config", "--get", "core.bare"],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    # `git config --get core.bare` either exits 0 with the bare token
    # (`true` / `false`) or exits 1 when the key is unset. A 0-exit
    # with empty stdout is not a shape git produces for this key, so
    # no defensive empty-stripping is needed.
    return completed.stdout.strip()


def main() -> int:
    log = _configure_logger()
    cwd = Path.cwd()
    if shutil.which("git") is None:
        log.warning(
            "git not on PATH; skipping primary-checkout-bare-flag-set check",
            check_id=_CHECK_ID,
            hint="install git or invoke from a shell that exposes git on PATH",
        )
        return 0
    if not _is_git_repo(cwd=cwd):
        log.info(
            "cwd is not inside a git working tree; skipping check",
            check_id=_CHECK_ID,
            cwd=str(cwd),
        )
        return 0
    raw = _read_core_bare(cwd=cwd)
    if raw == "true":
        return 0
    log.error(
        (
            "primary-checkout-bare-flag-set: `core.bare` is absent or `false` "
            "on the primary checkout's `.git/config`"
        ),
        check_id=_CHECK_ID,
        status="fail",
        observed=raw if raw is not None else "<absent>",
        hint=(
            "run `git config core.bare true` against the primary checkout "
            "(see livespec/SPECIFICATION/non-functional-requirements.md "
            '§"Bare-flag bootstrap procedure")'
        ),
        path="",
        line=0,
    )
    return _FAIL_EXIT


if __name__ == "__main__":
    raise SystemExit(main())
