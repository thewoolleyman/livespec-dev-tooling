"""primary_checkout_commit_refuse_hook_installed — verify commit-refuse hook at primary.

Universal mechanical check ported from livespec's doctor-static
phase. Per `livespec/SPECIFICATION/contracts.md` §"Doctor
cross-boundary invariants" → §"`primary-checkout-commit-refuse-hook-installed`"
and `livespec/SPECIFICATION/non-functional-requirements.md`
§"Primary-checkout commit-refuse hook", every livespec-governed
primary checkout MUST install `.git/hooks/pre-commit`,
`.git/hooks/pre-push`, AND `.git/hooks/commit-msg` hooks whose body
refuses to run when invoked at the primary checkout. The hook is a
no-op at secondary worktrees: the canonical body detects the primary
STRUCTURALLY (refuse when `git rev-parse --git-dir` equals
`git rev-parse --git-common-dir`; a worktree's git-dir differs), so it
is armed on install with no `livespec.primaryPath` arming step to miss.

Verification is STRICT BYTE-IDENTITY (zs22.7.9.5). Each of the three
installed hooks MUST be byte-identical to the single canonical body
`livespec_dev_tooling.install_commit_refuse_hooks.CANONICAL_HOOK_BODY`
(imported here — this module is NOT a second copy of the body). The
prior loose substring-fingerprint logic, which also accepted the
retired `git rev-parse --show-toplevel` / `livespec.primaryPath` legacy
body during the fleet migration, is gone: the fleet converged on the
from-package install in zs22.7.9.1, so the legacy-body migration
tolerance is obsolete and a fail-open hole. Any deviation — a hook
that is missing, non-executable, or whose bytes differ from the
canonical body (including a body that would have satisfied the old
loose fingerprint) — is a FAIL.

A second arm enforces NO VENDORED COPY of the hook source: a file
named `git-hook-wrapper.sh` or `livespec-commit-refuse-hook.sh`
anywhere in the repo tree is a FAIL, because the single source of the
body is the package constant and any tracked-or-untracked shell copy
can drift. The repo's `templates/` tree (the template-source domain of
zs22.7.9.3) and the `.git/` directory are carved out.

A third arm (zs22.7.9.3) guards the worktree-discipline PACK —
`dev-tooling/worktree-lib.sh`, `dev-tooling/branch-protection.sh`,
`dev-tooling/worktree.just` (the worktree-lifecycle recipe fragment,
added zs22.7.9 W2c/.4), and `dev-tooling/branch-protection.just` (the
branch-protection recipe fragment, added zs22 jzpx) — which the companion
`install_worktree_pack` installer ships from the SAME single package source
(its `CANONICAL_WORKTREE_LIB_BODY` / `CANONICAL_BRANCH_PROTECTION_BODY` /
`CANONICAL_WORKTREE_JUST_BODY` / `CANONICAL_BRANCH_PROTECTION_JUST_BODY`
constants, imported here). Both the
hook and the pack are facets of Conformance-Pattern concern #1
(Worktree-discipline), so the pack's byte-identity guard rides this
existing slug rather than a NEW canonical check slug — adding a new
`checks/<slug>.py` would force fleet-wide
`check-aggregate-completeness` re-wiring across every consumer, which
this arm deliberately avoids. Unlike the MANDATORY hooks, the pack is
OPTIONAL per repo: a repo that installs NO pack file legitimately
lacks it and is SKIPPED. But once a repo installs ANY pack file, ALL
of them MUST be present and byte-identical to the canonical bodies — a
drifted file is a `worktree_pack_body_mismatch` FAIL and an absent
sibling of a present file is a `worktree_pack_file_missing` FAIL (a
partial/drifted install).

The contract supersedes the v091-v094 `core.bare = true` mechanism
(see `primary_checkout_bare_flag_set.py` in earlier releases). The
bare-flag mechanism caused stale-on-disk-read failures at primaries
that the hook mechanism does not.

Inputs are project-agnostic: the check reads the three hooks under the
current working directory's git common dir and scans the work-tree
root (`git rev-parse --show-toplevel`). No `[tool.livespec_dev_tooling]`
role keys are consumed (per the sibling spec's §"Shared check
inventory" partition criterion — this check is layout-independent).

Exit codes:
- `0` — pass. All three hooks exist, are executable, and are
  byte-identical to `CANONICAL_HOOK_BODY`, AND no vendored hook-source
  copy exists outside the `templates/` / `.git/` carve-outs, AND the
  worktree-discipline pack is either absent (legitimately not installed)
  or fully present and byte-identical to its canonical bodies.
- `0` — skipped (cwd is not a git repository at all, or `git` is
  unavailable, or cwd is a git repository but not inside a work tree).
  Skipped is `0` so the check is a no-op in those environments rather
  than a false positive. There is deliberately NO "hooks absent → skip"
  branch: absence is a FAIL, not a skip (that would re-open the
  fail-open hole this check closes). ⛔ AND "git is unavailable" means
  `shutil.which` finds no git AT ALL — a git that IS on PATH and does
  not answer is `git_probe_failed` below, not a skip. Those two used to
  be the same exit until the probes went on the railway
  (livespec-dev-tooling-qndn).
- `4` — fail. A git probe did not answer (`failure_mode`
  `git_probe_failed`): `git` on PATH but unexecutable, a `rev-parse`
  exiting non-zero against the caller's own precondition, an unreadable
  config. The narration carries the probe name, the exact argv and the
  cwd so the operator can rerun it. Every state this check reports rests
  on those probes, so an unanswered one is a verdict the check cannot
  compute — and it must not be spelled the same as "nothing to check".
- `4` — fail. Any of the three hooks is missing, non-executable, or
  byte-different from `CANONICAL_HOOK_BODY`; OR a vendored hook-source
  copy exists outside the carve-outs; OR an installed worktree-pack
  file (`dev-tooling/worktree-lib.sh` / `dev-tooling/branch-protection.sh` /
  `dev-tooling/worktree.just` / `dev-tooling/branch-protection.just`) has
  drifted (`worktree_pack_body_mismatch`) or is partially installed
  (`worktree_pack_file_missing`). Corrective
  action: run
  `just install-commit-refuse-hooks` and/or `just install-worktree-pack`
  (the from-package installers that are the single source of each body),
  and delete any vendored copy. The narration names the specific failure
  mode + offending path for diagnostic clarity.
- `4` — fail. The repo IS a git repository but has `core.bare = true`
  set (`failure_mode` `core_bare_set`). This is the eliminated legacy
  bare-flag state (the v091-v094 mechanism the commit-refuse hook
  superseded): a bare repo is a git repo that is NOT a work tree, so
  the work-tree skip below would silently pass it. This realizes the
  MAY in `livespec/SPECIFICATION/contracts.md`
  §"`primary-checkout-commit-refuse-hook-installed`". The corrective
  action is to unset the flag and repopulate the working tree.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
# Make the script's own directory importable so the sibling `_*` git-probe
# module resolves both under `python3 <path>` and the importlib test path.
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

# Sibling `_*` git-probe module (fleet-check-coverage LLOC split). The leading
# underscore marks it a private helper rather than a check entry point; imported
# after the `_SCRIPT_DIR` sys.path insert above. Every probe returns `IOResult`
# since livespec-dev-tooling-qndn, so this module owns the decision each
# unanswered probe used to make silently.
from _primary_checkout_git_probes import (  # noqa: E402  — sibling private import
    GitProbeFailed,
    core_bare_is_true,
    git_common_dir,
    is_git_repo_at_all,
    is_inside_work_tree,
    sandbox_exempt_is_true,
    work_tree_root,
)

# Sibling `_*` worktree-pack module — the third arm, split out when this file
# crossed its 250-LLOC hard ceiling, exactly as `_primary_checkout_git_probes`
# was. It owns the config-policy read, the byte-identity comparison, and the
# discoverability assertion; this module owns the narration.
from _primary_checkout_worktree_pack import (  # noqa: E402  — sibling private import
    inspect_worktree_pack,
    pack_failure_hint,
    pack_failure_path,
)
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

# The canonical body is the SINGLE source of truth, shipped as a module
# constant in the installer so it travels in the wheel. The check imports
# it (rather than carrying a second copy) so byte-identity is verified
# against the exact bytes the installer writes — there is no drift seam.
from livespec_dev_tooling.install_commit_refuse_hooks import (  # noqa: E402
    CANONICAL_HOOK_BODY,
)

__all__: list[str] = []


_CHECK_ID = "primary_checkout_commit_refuse_hook_installed"
_FAIL_EXIT = 4

# All three hooks the from-package installer writes; each MUST be present
# and byte-identical to CANONICAL_HOOK_BODY.
_HOOK_NAMES: tuple[str, ...] = ("pre-commit", "pre-push", "commit-msg")

# No-vendored-copy arm: a shell copy of the hook source under either of
# these names is a drift seam (the package constant is the single source).
_VENDORED_COPY_NAMES: tuple[str, ...] = (
    "git-hook-wrapper.sh",
    "livespec-commit-refuse-hook.sh",
)

# Path components carved out of the no-vendored-copy scan. `templates/` is
# the template-source domain (zs22.7.9.3 ships a hook copy there as a
# template artifact, not an installed/vendored copy); `.git/` is git's own
# internal tree (the installed hooks live there under their own names).
_VENDORED_COPY_CARVE_OUT_PARTS: frozenset[str] = frozenset({"templates", ".git"})

# Failure-mode value for the legacy bare-flag regression — emitted on the
# dedicated `core.bare = true` fail branch (distinct from the per-hook
# `missing` / `not_executable` / `body_mismatch` modes and the
# `vendored_copy_present` mode).
_CORE_BARE_FAILURE_MODE = "core_bare_set"
_VENDORED_COPY_FAILURE_MODE = "vendored_copy_present"
# A git probe that did not ANSWER — distinct from every mode above, which are
# all things the check successfully OBSERVED.
_GIT_PROBE_FAILURE_MODE = "git_probe_failed"

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
_GIT_PROBE_REMEDY = (
    "a git probe this check depends on did not answer; rerun the reported "
    "`argv` from the reported `cwd` to see git's own diagnostic. Every "
    "verdict below rests on those probes, so an unanswered one is a result "
    "the check cannot compute — it is reported rather than collapsed onto "
    "`not a git repository`, which is a SKIP and would be a pass this run "
    "never earned"
)


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


def _inspect_hook(
    *,
    hook_path: Path,
) -> tuple[bool, str]:
    """Return `(ok, failure_mode)` for a single hook path.

    `ok` is True only when the hook exists as a regular file, is
    executable by the current user, and its body is BYTE-IDENTICAL to
    `CANONICAL_HOOK_BODY`. `failure_mode` is one of:

    - `"missing"` — the hook file is absent or is not a regular file.
    - `"not_executable"` — the hook exists but the executable bit is
      unset for the current user (`os.access(path, os.X_OK)`).
    - `"body_mismatch"` — the hook is executable but its bytes differ
      from `CANONICAL_HOOK_BODY` (covers the empty-file case and any
      body that would have passed the retired loose fingerprint).
    - `""` (empty string) — the hook is correct; paired with `ok=True`.
    """
    if not hook_path.is_file():
        return False, "missing"
    if not os.access(hook_path, os.X_OK):
        return False, "not_executable"
    body = hook_path.read_text(encoding="utf-8")
    if body != CANONICAL_HOOK_BODY:
        return False, "body_mismatch"
    return True, ""


def _find_vendored_hook_copies(*, repo_root: Path) -> list[Path]:
    """Return every vendored hook-source copy under `repo_root`, sorted.

    Scans the work-tree root for files named `git-hook-wrapper.sh` or
    `livespec-commit-refuse-hook.sh`, EXCLUDING any path with a component
    under the `templates/` or `.git/` carve-outs. A match outside the
    carve-outs is a drift seam (a second source of the hook body) and a
    FAIL. Returns an empty list when no offending copy exists.
    """
    found: list[Path] = []
    for name in _VENDORED_COPY_NAMES:
        for candidate in repo_root.rglob(name):
            relative_parts = candidate.relative_to(repo_root).parts
            if any(part in _VENDORED_COPY_CARVE_OUT_PARTS for part in relative_parts):
                continue
            found.append(candidate)
    return sorted(found)


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


def _inspect_work_tree(*, log: structlog.stdlib.BoundLogger, cwd: Path) -> int:
    """The work-tree gate, then the three byte-identity arms.

    One of three functions the conversion split `main` into, at the seams it
    created: `main` gates on "is this a git repo we should check at all",
    THIS gates on "is it a work tree", and `_inspect_installed_state` runs the
    arms. Each probe now carries a failure arm of its own, and each arm is a
    `return`, so the split is what keeps every function inside the
    six-return lint budget rather than an aesthetic preference.
    """
    inside = is_inside_work_tree(cwd=cwd)
    if isinstance(inside, IOFailure):
        return _narrate_probe_failure(log=log, failed=unsafe_perform_io(inside.failure()))
    if not unsafe_perform_io(inside.unwrap()):
        log.info(
            "cwd is not inside a git working tree; skipping check",
            check_id=_CHECK_ID,
            cwd=str(cwd),
        )
        return 0
    return _inspect_installed_state(log=log, cwd=cwd)


def _inspect_installed_state(*, log: structlog.stdlib.BoundLogger, cwd: Path) -> int:
    """The three byte-identity arms, against a resolved common dir and root."""
    common = git_common_dir(cwd=cwd)
    if isinstance(common, IOFailure):
        return _narrate_probe_failure(log=log, failed=unsafe_perform_io(common.failure()))
    root = work_tree_root(cwd=cwd)
    if isinstance(root, IOFailure):
        return _narrate_probe_failure(log=log, failed=unsafe_perform_io(root.failure()))
    # The pack-presence arm honours the DECLARED sandbox exemption, read here
    # (not inside the sibling) so every git probe stays in one module. A fresh
    # sandbox clone cannot carry the gitignored pack; the byte-identity arms
    # still fire there.
    exempt = sandbox_exempt_is_true(cwd=cwd)
    if isinstance(exempt, IOFailure):
        return _narrate_probe_failure(log=log, failed=unsafe_perform_io(exempt.failure()))
    hooks_dir = unsafe_perform_io(common.unwrap()) / "hooks"
    repo_root = unsafe_perform_io(root.unwrap())
    hook_failures: list[tuple[str, str]] = []
    for hook_name in _HOOK_NAMES:
        hook_path = hooks_dir / hook_name
        ok, failure_mode = _inspect_hook(hook_path=hook_path)
        if not ok:
            hook_failures.append((hook_name, failure_mode))
    vendored_copies = _find_vendored_hook_copies(repo_root=repo_root)
    pack_failures = inspect_worktree_pack(
        repo_root=repo_root,
        sandbox_exempt=unsafe_perform_io(exempt.unwrap()),
    )
    if not hook_failures and not vendored_copies and not pack_failures:
        return 0
    _emit_failures(
        log=log,
        hooks_dir=hooks_dir,
        repo_root=repo_root,
        hook_failures=hook_failures,
        vendored_copies=vendored_copies,
        pack_failures=pack_failures,
    )
    return _FAIL_EXIT


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
    is_repo = is_git_repo_at_all(cwd=cwd)
    if isinstance(is_repo, IOFailure):
        return _narrate_probe_failure(log=log, failed=unsafe_perform_io(is_repo.failure()))
    if not unsafe_perform_io(is_repo.unwrap()):
        log.info(
            "cwd is not a git repository; skipping check",
            check_id=_CHECK_ID,
            cwd=str(cwd),
        )
        return 0
    bare = core_bare_is_true(cwd=cwd)
    if isinstance(bare, IOFailure):
        return _narrate_probe_failure(log=log, failed=unsafe_perform_io(bare.failure()))
    if unsafe_perform_io(bare.unwrap()):
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
                "the working tree, then run `just install-commit-refuse-hooks`"
            ),
            path="",
            line=0,
        )
        return _FAIL_EXIT
    return _inspect_work_tree(log=log, cwd=cwd)


if __name__ == "__main__":
    raise SystemExit(main())
