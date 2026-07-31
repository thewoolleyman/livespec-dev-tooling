"""_primary_checkout_narration — every finding this check emits, in one place.

Private sibling of `primary_checkout_commit_refuse_hook_installed`, extracted
when putting the check's file reads on the `IOResult` railway pushed the parent
back over its 250-LLOC hard ceiling. It is the fourth such split, after
`_primary_checkout_git_probes`, `_primary_checkout_worktree_pack` and
`_primary_checkout_hook_files`.

⛔ THIS IS NOT A RETREAT FROM "the arms compute, the parent narrates". That
discipline exists so a reader can find every sentence this check can say in ONE
place, and with four arms now feeding it the parent was no longer that place —
it was arms-plus-narration. Here the whole vocabulary sits together: five
failure modes the check OBSERVED, two it could not (`git_probe_failed`,
`hook_unreadable` / `worktree_pack_unreadable`), and the remedy each one routes
to. The arms still narrate nothing.

⛔ AND WHY THE UNREADABLE MODES ARE SEPARATE ROWS RATHER THAN A SHARED ONE.
Every other mode here is a statement about the repository. `hook_unreadable`
and `worktree_pack_unreadable` are statements about this RUN, and the remedy
differs accordingly: the observed modes say "reinstall", these say "fix the
access fault and re-run rather than reinstalling anything". Folding an unread
file into `missing` or `body_mismatch` would produce a grammatical, specific,
actionable sentence about a file nothing read.

Names stay `_`-prefixed and are re-exported through `__all__`: they were
private in the parent, and making them public to satisfy the extraction would
enrol three unconverted functions in the railway universe as brand-new
offenders — the split reporting work it did not do.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from _primary_checkout_worktree_pack import (  # noqa: E402  — sibling private import
    pack_failure_hint,
    pack_failure_path,
)

# ABSOLUTE where the arm imports are bare, so there is exactly ONE
# `CheckInputUnreadable` class object however this module is reached.
from livespec_dev_tooling.checks._primary_checkout_unreadable import (  # noqa: E402
    CheckInputUnreadable,
)

if TYPE_CHECKING:
    from _primary_checkout_git_probes import GitProbeFailed

__all__: list[str] = [
    "_CHECK_ID",
    "_CORE_BARE_FAILURE_MODE",
    "_FAIL_EXIT",
    "_GIT_PROBE_FAILURE_MODE",
    "_HOOK_READ_FAILURE_MODE",
    "_HOOK_REMEDY",
    "_PACK_READ_FAILURE_MODE",
    "_emit_failures",
    "_narrate_probe_failure",
    "_narrate_unreadable_input",
]

_CHECK_ID = "primary_checkout_commit_refuse_hook_installed"
_FAIL_EXIT = 4

_CORE_BARE_FAILURE_MODE = "core_bare_set"
_VENDORED_COPY_FAILURE_MODE = "vendored_copy_present"
# A git probe that did not ANSWER — distinct from every mode above, which are
# all things the check successfully OBSERVED.
_GIT_PROBE_FAILURE_MODE = "git_probe_failed"
# The same distinction on the two arms that read FILES. Emphatically not any
# of the observed modes above: those are statements ABOUT the hook or the
# pack, and reporting an unread file as one of them would hand the operator a
# remedy for a fault never observed.
_HOOK_READ_FAILURE_MODE = "hook_unreadable"
_PACK_READ_FAILURE_MODE = "worktree_pack_unreadable"

_HOOK_REMEDY = (
    "run `just install-commit-refuse-hooks` (the from-package installer "
    "that writes the single canonical body byte-for-byte to "
    "`.git/hooks/pre-commit`, `.git/hooks/pre-push`, and "
    "`.git/hooks/commit-msg`)"
)
_VENDORED_COPY_REMEDY = (
    "delete the vendored hook-source copy; the single source of the hook "
    "body is the `CANONICAL_HOOK_BODY` package constant installed via "
    "`just install-commit-refuse-hooks` — a repo-tracked shell copy can "
    "drift from it"
)
_UNREADABLE_INPUT_REMEDY = (
    "a file this check depends on could not be READ; the reported `path` "
    "names it and `detail` carries the OS diagnostic. This is not a statement "
    "about the hook or the pack — every arm decides drift, absence and "
    "partial installs from the bytes it reads, and it read none here. Fix the "
    "access fault and re-run rather than reinstalling anything"
)
_GIT_PROBE_REMEDY = (
    "a git probe this check depends on did not answer; rerun the reported "
    "`argv` from the reported `cwd` to see git's own diagnostic. Every "
    "verdict below rests on those probes, so an unanswered one is a result "
    "the check cannot compute — it is reported rather than collapsed onto "
    "`not a git repository`, which is a SKIP and would be a pass this run "
    "never earned"
)


def _emit_failures(
    *,
    log: structlog.stdlib.BoundLogger,
    hooks_dir: Path,
    repo_root: Path,
    hook_failures: list[tuple[str, str]],
    vendored_copies: list[Path],
    pack_failures: list[tuple[str, str]],
) -> None:
    """Emit one structured `fail` finding per detected violation.

    Extracted from `main` so each of the three arms (hook byte-identity,
    no-vendored-copy, worktree-pack drift) narrates independently while
    keeping `main`'s cyclomatic complexity within the lint budget.
    """
    for hook_name, failure_mode in hook_failures:
        log.error(
            "primary-checkout-commit-refuse-hook-installed: hook failure",
            check_id=_CHECK_ID,
            status="fail",
            hook=hook_name,
            failure_mode=failure_mode,
            hooks_dir=str(hooks_dir),
            hint=_HOOK_REMEDY,
            path="",
            line=0,
        )
    for copy_path in vendored_copies:
        log.error(
            "primary-checkout-commit-refuse-hook-installed: vendored hook copy present",
            check_id=_CHECK_ID,
            status="fail",
            hook="",
            failure_mode=_VENDORED_COPY_FAILURE_MODE,
            hooks_dir=str(hooks_dir),
            hint=_VENDORED_COPY_REMEDY,
            path=str(copy_path),
            line=0,
        )
    for script_name, failure_mode in pack_failures:
        log.error(
            "primary-checkout-commit-refuse-hook-installed: worktree-pack drift",
            check_id=_CHECK_ID,
            status="fail",
            hook="",
            failure_mode=failure_mode,
            hooks_dir=str(hooks_dir),
            hint=pack_failure_hint(failure_mode=failure_mode),
            path=str(pack_failure_path(repo_root=repo_root, script_name=script_name)),
            line=0,
        )


def _narrate_probe_failure(*, log: structlog.stdlib.BoundLogger, failed: GitProbeFailed) -> int:
    """Report an unanswered git probe as a finding and FAIL — never skip.

    ⛔ Deliberately not exit 0. "`git` is unavailable" is a documented skip and
    this is the other thing: git present and not answering. Before the
    conversion the two were the same value — `is_git_repo_at_all` returned a
    bare `False` either way — so a broken environment took the skip path and
    the run went green having verified nothing.
    """
    log.error(
        "primary-checkout-commit-refuse-hook-installed: git probe failed",
        check_id=_CHECK_ID,
        status="fail",
        hook="",
        failure_mode=_GIT_PROBE_FAILURE_MODE,
        hooks_dir="",
        hint=_GIT_PROBE_REMEDY,
        path="",
        line=0,
        probe=failed.probe,
        argv=failed.argv,
        probe_cwd=failed.cwd,
        detail=failed.detail,
    )
    return _FAIL_EXIT


def _narrate_unreadable_input(
    *, log: structlog.stdlib.BoundLogger, failed: CheckInputUnreadable, failure_mode: str
) -> int:
    """Report a file this check could not READ as its own finding and FAIL.

    Exit 4 rather than a third code, matching `_narrate_probe_failure`: in
    this check a non-answer FAILS, and is told apart from a violation by the
    structured record rather than by the exit status. What must never merge is
    the `failure_mode` — an unread hook narrated as `missing`, or an unread
    pack file as `body_mismatch`, would send the operator to reinstall
    something whose state this run never observed.

    `failure_mode` is the caller's because the arms are actionable in
    different places, exactly as `pack_failure_hint`'s routing already is.
    """
    log.error(
        "primary-checkout-commit-refuse-hook-installed: check input unreadable",
        check_id=_CHECK_ID,
        status="fail",
        hook="",
        failure_mode=failure_mode,
        hooks_dir="",
        hint=_UNREADABLE_INPUT_REMEDY,
        path=failed.path,
        line=0,
        detail=failed.detail,
    )
    return _FAIL_EXIT
