"""primary_checkout_commit_refuse_hook_installed — verify commit-refuse hook at primary.

Universal mechanical check ported from livespec's doctor-static
phase. Per `livespec/SPECIFICATION/contracts.md` section "Doctor
cross-boundary invariants" → section "`primary-checkout-commit-refuse-hook-installed`"
and `livespec/SPECIFICATION/non-functional-requirements.md`
section "Primary-checkout commit-refuse hook", every livespec-governed
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

A third arm (livespec-dev-tooling-x2ju4a) enforces that the installer
owns EVERY lefthook entry point in the shared hooks directory: any
executable in `<git-common-dir>/hooks/` that invokes lefthook WITHOUT the
canonical `unset GIT_DIR GIT_INDEX_FILE GIT_WORK_TREE GIT_PREFIX` line is
a `foreign_lefthook_wrapper` FAIL naming the file. The byte-identity arm
above only ever looked at three NAMES, so lefthook's stock
`call_lefthook` wrapper under a fourth name was invisible to it — on
2026-09-06 `/data/projects/livespec/.git/hooks/prepare-commit-msg` was
exactly that, mtime three months older than its canonical siblings,
firing on every commit and every cherry-pick, leaking GIT_DIR and calling
`lefthook run` without `--no-auto-install`. The canonical three carry the
unset line by construction and keep passing.

A fourth arm (zs22.7.9.3) guards the worktree-discipline PACK —
`dev-tooling/worktree-lib.sh`, `dev-tooling/branch-protection.sh`,
`dev-tooling/gate-run.sh` (the detached gate runner),
`dev-tooling/check-no-workflow-edits.sh` (the fleet's one workflow-edit
guard, added livespec-dev-tooling-fy02), `dev-tooling/worktree.just` (the
worktree-lifecycle recipe fragment, added zs22.7.9 W2c/.4), and
`dev-tooling/branch-protection.just` (the branch-protection recipe fragment,
added zs22 jzpx) — which the companion `install_worktree_pack` installer
ships from the SAME single package source (its `CANONICAL_WORKTREE_LIB_BODY`
/ `CANONICAL_BRANCH_PROTECTION_BODY` / `CANONICAL_GATE_RUN_BODY` /
`CANONICAL_NO_WORKFLOW_EDITS_BODY` / `CANONICAL_WORKTREE_JUST_BODY` /
`CANONICAL_BRANCH_PROTECTION_JUST_BODY` constants, imported here). Both the
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
role keys are consumed (per the sibling spec's section "Shared check
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
- `4` — fail. A file the worktree-pack arm depends on could not be READ
  (`failure_mode` `worktree_pack_unreadable`): the `.livespec.jsonc`, an
  installed pack file, or the root justfile. The narration carries the
  `path` and the OS `detail`. ⛔ Deliberately its OWN mode rather than
  `worktree_pack_body_mismatch`: the byte-identity arm decides drift from
  the bytes it reads, and with no bytes there is no verdict about the pack
  to report. Reporting one would send the operator to re-install a pack
  whose state this run never observed. Before the pack arm went on the
  railway an unread `.livespec.jsonc` resolved to the `ungoverned` policy —
  and an ungoverned tree needs no pack, so the check exited `0`.
- `4` — fail. A hooks-directory executable invokes lefthook without the
  canonical `unset GIT_DIR …` line (`failure_mode`
  `foreign_lefthook_wrapper`). The narration names the file in both
  `hook` (its basename) and `path` (absolute). Corrective action:
  `just install-commit-refuse-hooks`, whose sweep deletes it.
- `4` — fail. Any of the three hooks is missing, non-executable, or
  byte-different from `CANONICAL_HOOK_BODY`; OR a vendored hook-source
  copy exists outside the carve-outs; OR an installed worktree-pack
  file (`dev-tooling/worktree-lib.sh` / `dev-tooling/branch-protection.sh` /
  `dev-tooling/gate-run.sh` / `dev-tooling/check-no-workflow-edits.sh` /
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
  section "`primary-checkout-commit-refuse-hook-installed`". The corrective
  action is to unset the flag and repopulate the working tree.

Output discipline: structlog JSON to stderr; no `print`, no
`sys.stderr.write`.
"""

from __future__ import annotations

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
    core_bare_is_true,
    git_common_dir,
    is_git_repo_at_all,
    is_inside_work_tree,
    sandbox_exempt_is_true,
    work_tree_root,
)

# Sibling `_*` hook-file module — the hook byte-identity and vendored-copy
# arms, extracted when putting this check's file reads on the railway pushed
# the file back over its 250-LLOC hard ceiling. The extraction is also what
# surfaced that `inspect_hook` compared decoded TEXT under a docstring
# promising byte-identity; both are converted rather than merely moved.
from _primary_checkout_hook_files import (  # noqa: E402  — sibling private import
    _find_foreign_lefthook_wrappers,
    _find_vendored_hook_copies,
    _inspect_hook,
)

# Sibling `_*` worktree-pack module — the third arm, split out when this file
# first crossed its hard ceiling, exactly as `_primary_checkout_git_probes`
# was. It owns the config-policy read, the byte-identity comparison, and the
# discoverability assertion; this module owns the narration.
from _primary_checkout_narration import (  # noqa: E402  — sibling private import
    _CHECK_ID,
    _CORE_BARE_FAILURE_MODE,
    _FAIL_EXIT,
    _HOOK_READ_FAILURE_MODE,
    _PACK_READ_FAILURE_MODE,
    _emit_failures,
    _emit_foreign_wrapper_failures,
    _narrate_probe_failure,
    _narrate_unreadable_input,
)
from _primary_checkout_worktree_pack import (  # noqa: E402  — sibling private import
    inspect_worktree_pack,
)
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

# The one condition none of this check's arms can decide, in its own sibling so
# neither arm has to import the other for it. ABSOLUTE where the arm imports
# are bare: a bare import would create a second class object and the parent's
# matches would silently stop lining up with the arms' failures.
from livespec_dev_tooling.checks._primary_checkout_unreadable import (  # noqa: E402
    CheckInputUnreadable,
)

__all__: list[str] = []


# All three hooks the from-package installer writes; each MUST be present
# and byte-identical to CANONICAL_HOOK_BODY.
_HOOK_NAMES: tuple[str, ...] = ("pre-commit", "pre-push", "commit-msg")


# Failure-mode value for the legacy bare-flag regression — emitted on the
# dedicated `core.bare = true` fail branch (distinct from the per-hook
# `missing` / `not_executable` / `body_mismatch` modes and the
# `vendored_copy_present` mode).
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
    return _inspect_arms(
        log=log,
        hooks_dir=unsafe_perform_io(common.unwrap()) / "hooks",
        repo_root=unsafe_perform_io(root.unwrap()),
        sandbox_exempt=unsafe_perform_io(exempt.unwrap()),
    )


def _collect_hook_failures(
    *, hooks_dir: Path
) -> IOResult[list[tuple[str, str]], CheckInputUnreadable]:
    """Every hook that is missing, non-executable or byte-different, or the unread one.

    Stops at the FIRST unreadable hook rather than collecting around it: a
    partial hook verdict is not a smaller verdict, it is an unsound one, and
    the two remaining hooks would be reported as if all three had been checked.
    """
    failures: list[tuple[str, str]] = []
    for hook_name in _HOOK_NAMES:
        inspected = _inspect_hook(hook_path=hooks_dir / hook_name)
        if isinstance(inspected, IOFailure):
            return inspected
        ok, failure_mode = unsafe_perform_io(inspected.unwrap())
        if not ok:
            failures.append((hook_name, failure_mode))
    return IOSuccess(failures)


def _inspect_arms(
    *,
    log: structlog.stdlib.BoundLogger,
    hooks_dir: Path,
    repo_root: Path,
    sandbox_exempt: bool,
) -> int:
    """The four hooks-directory arms, each of which may decline to answer.

    Split from `_inspect_installed_state` at the seam the conversion created:
    that function owns the git probes, this one owns the file reads. Each arm
    is a `return`, and keeping them in one function would put both groups past
    the six-return lint budget.

    The FOREIGN-WRAPPER arm is the only one not keyed to a name this check
    already knew: the other three inspect `_HOOK_NAMES`, a vendored-copy name
    list, and the pack's file list respectively, which is exactly why a stock
    lefthook wrapper under a FOURTH hook name was invisible to all of them.
    """
    hooks = _collect_hook_failures(hooks_dir=hooks_dir)
    if isinstance(hooks, IOFailure):
        return _narrate_unreadable_input(
            log=log,
            failed=unsafe_perform_io(hooks.failure()),
            failure_mode=_HOOK_READ_FAILURE_MODE,
        )
    wrappers = _find_foreign_lefthook_wrappers(hooks_dir=hooks_dir)
    if isinstance(wrappers, IOFailure):
        return _narrate_unreadable_input(
            log=log,
            failed=unsafe_perform_io(wrappers.failure()),
            failure_mode=_HOOK_READ_FAILURE_MODE,
        )
    copies = _find_vendored_hook_copies(repo_root=repo_root)
    if isinstance(copies, IOFailure):
        return _narrate_unreadable_input(
            log=log,
            failed=unsafe_perform_io(copies.failure()),
            failure_mode=_HOOK_READ_FAILURE_MODE,
        )
    inspected = inspect_worktree_pack(repo_root=repo_root, sandbox_exempt=sandbox_exempt)
    if isinstance(inspected, IOFailure):
        return _narrate_unreadable_input(
            log=log,
            failed=unsafe_perform_io(inspected.failure()),
            failure_mode=_PACK_READ_FAILURE_MODE,
        )
    hook_failures = unsafe_perform_io(hooks.unwrap())
    foreign_wrappers = unsafe_perform_io(wrappers.unwrap())
    vendored_copies = unsafe_perform_io(copies.unwrap())
    pack_failures = unsafe_perform_io(inspected.unwrap())
    if not hook_failures and not foreign_wrappers and not vendored_copies and not pack_failures:
        return 0
    _emit_failures(
        log=log,
        hooks_dir=hooks_dir,
        repo_root=repo_root,
        hook_failures=hook_failures,
        vendored_copies=vendored_copies,
        pack_failures=pack_failures,
    )
    _emit_foreign_wrapper_failures(log=log, hooks_dir=hooks_dir, foreign_wrappers=foreign_wrappers)
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
