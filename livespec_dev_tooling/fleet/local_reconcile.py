"""local_reconcile — LOCAL-vantage first-touch reconcile of a governed checkout.

The generalized successor to `just bootstrap`'s local first-touch steps
(per `livespec/SPECIFICATION/non-functional-requirements.md`
section "Governed-repo lifecycle"): runs the idempotent local setup an arbitrary
governed checkout needs — toolchain install, dependency sync, the
commit-refuse hooks, the git notes refspec, the worktree-root mise-trust
entry, the beads tenant-dir hardening, and project-scoped plugin +
marketplace registration — against a TARGET checkout rather than only the
current repo. It walks the LOCAL obligation partition
(`contract.LOCAL_OBLIGATION_ROWS`), the local-vantage sibling of the
central `wire_fleet_member` reconcile: a row carrying a drift assert is
asserted first and reconciled only when unmet; a pure provisioning row
runs its idempotent reconcile unconditionally.

`just bootstrap` becomes a thin delegator to this verb for the current
checkout. The checkout root is resolved worktree-safely via
`git rev-parse --git-common-dir`, so invoking from a linked worktree
still provisions the primary checkout's shared state.

Exit codes:

- `0` — every applicable row reconciled (or was already satisfied / not
  applicable, e.g. a repo with no beads tenant).
- `1` — precondition failure: the target path is not a git checkout.
- `4` — one or more rows did not reconcile (the log carries each row's
  detail).

Output discipline matches the sibling fleet CLIs: structlog JSON to
stderr; no `print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import cast

from livespec_dev_tooling.config import assert_never
from livespec_dev_tooling.fleet._context import (
    EXCLUDED_NOTE_PREFIX,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._contract_local_rows import LOCAL_OBLIGATION_ROWS
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._local_context import (
    CommandRunner,
    LocalContext,
    command_answer,
    default_command_runner,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


def _resolve_checkout_root(
    *, target: Path, run: CommandRunner
) -> Path | InvocationNotPerformed | None:
    """The primary checkout root for `target`; None when `git` says it is not one.

    Uses `git rev-parse --git-common-dir` so the resolution is
    worktree-safe: from a linked worktree the common dir is the
    primary's shared `.git`, whose parent is the primary checkout root.

    THREE answers rather than two, because the caller's diagnostic differs
    for each. `git` that never ran is not evidence that `target` is not a
    checkout — `main()` used to print "target is not a git checkout" and
    advise passing `--checkout` for a host that simply has no `git`.
    """
    answer = command_answer(outcome=run(args=["git", "rev-parse", "--git-common-dir"], cwd=target))
    if isinstance(answer, InvocationNotPerformed):
        return answer
    if answer.returncode != 0:
        return None
    common = Path(answer.stdout.strip())
    if not common.is_absolute():
        common = (target / common).resolve()
    return common.parent


def _already_settled(
    *, outcome: RowOutcome, row_id: str, log: structlog.stdlib.BoundLogger
) -> bool:
    """True when the assert leg settled the row and no reconcile is owed.

    An EXCLUDED pass (the row does not apply here) and a satisfied pass both
    settle it; a finding or a can't-read do not. Split out with its reconcile
    sibling when the excluded-note arms pushed `reconcile_checkout` past
    PLR0912's branch cap — the cap was paid, never routed around.
    """
    match outcome:
        case RowPass() if outcome.note.startswith(EXCLUDED_NOTE_PREFIX):
            log.info(
                "row not applicable",
                row=row_id,
                reason=outcome.note.removeprefix(EXCLUDED_NOTE_PREFIX),
            )
            return True
        case RowPass():
            log.info("row already satisfied", row=row_id, note=outcome.note)
            return True
        case RowFinding() | RowSkip():
            return False
        case _:
            assert_never(outcome)


def _log_reconcile_outcome(
    *, fixed: RowOutcome, row_id: str, log: structlog.stdlib.BoundLogger
) -> int:
    """Narrate one reconcile result; return its contribution to `unresolved`.

    ⛔ The excluded-pass arm comes FIRST and is a GUARD, not a bare pattern: a
    bare name in a `case` is a capture, not a comparison. An excluded pass must
    read "not applicable" rather than "row reconciled", because the local lane
    would otherwise claim it FIXED a row that never applied — the same two
    meanings this change removes, arriving in the narration instead of the type.
    """
    match fixed:
        case RowPass() if fixed.note.startswith(EXCLUDED_NOTE_PREFIX):
            log.info(
                "row not applicable",
                row=row_id,
                reason=fixed.note.removeprefix(EXCLUDED_NOTE_PREFIX),
            )
            return 0
        case RowPass():
            log.info("row reconciled", row=row_id, note=fixed.note)
            return 0
        case RowSkip():
            log.info("row not evaluable", row=row_id, reason=fixed.reason)
            return 0
        case RowFinding() if fixed.severity == "warning":
            log.warning(
                "row needs out-of-band action (detect-and-guide)",
                row=row_id,
                hint=fixed.message,
            )
            return 0
        case RowFinding():
            log.error("row did not reconcile", row=row_id, detail=fixed.message)
            return 1
        case _:
            assert_never(fixed)


def reconcile_checkout(*, ctx: LocalContext, log: structlog.stdlib.BoundLogger) -> int:
    """Assert-then-reconcile every local first-touch row; return the unresolved count.

    A `RowFinding` is split by severity, reusing the `RowFinding.severity` field
    the central `fleet_conformance` reader already distinguishes: a `warning`
    finding is DETECT-AND-GUIDE guidance — an out-of-band human seam the verb
    cannot machine-fix (a missing runtime binary, an unreachable backend, an
    absent secret) — surfaced via `log.warning` and NOT counted as unresolved, so
    it never fails the verb; an `error` finding is a genuine unmet obligation that
    counts toward the unresolved exit code.
    """
    unresolved = 0
    for row in LOCAL_OBLIGATION_ROWS:
        if row.assert_local is not None and _already_settled(
            outcome=row.assert_local(ctx=ctx), row_id=row.row_id, log=log
        ):
            continue
        unresolved += _log_reconcile_outcome(
            fixed=row.reconcile_local(ctx=ctx), row_id=row.row_id, log=log
        )
    return unresolved


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="local-reconcile",
        description=(
            "LOCAL-vantage first-touch reconcile of a governed checkout "
            '(livespec §"Governed-repo lifecycle").'
        ),
    )
    _ = parser.add_argument(
        "--checkout",
        default=None,
        help="Target checkout path; defaults to the current working directory.",
    )
    return parser


def _resolve_invoked_worktree(*, target: Path, run: CommandRunner) -> Path | None:
    """The work-tree root `target` sits in, or None when `git` did not run.

    Distinct from `_resolve_checkout_root`: that returns the PRIMARY root via
    `--git-common-dir`, which is what shared obligations need. This returns the
    root of the worktree actually invoked, which per-worktree artifacts need.

    The None arm is UNREACHABLE THROUGH `main()` and is still real code: the
    sole caller resolves the checkout root FIRST and bails when that fails, so
    by the time this runs `git` is known invocable. It is therefore exercised
    at its OWN seam rather than through the composed caller — the same shape as
    `walk_github_workflow_container_image`, whose failure branch a
    short-circuiting caller left uncovered forever while looking thorough.

    None rather than a fabricated path: `LocalContext.worktree` already
    documents None as falling back to `checkout`, so this reuses the existing
    spelling for "unknown" instead of inventing a second one.
    """
    answer = command_answer(outcome=run(args=["git", "rev-parse", "--show-toplevel"], cwd=target))
    if isinstance(answer, InvocationNotPerformed):
        return None
    return Path(answer.stdout.strip())


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("local_reconcile")
    args = _build_parser().parse_args()
    raw_target = cast("str | None", args.checkout)
    target = Path(raw_target) if raw_target is not None else Path.cwd()
    root = _resolve_checkout_root(target=target, run=default_command_runner)
    if isinstance(root, InvocationNotPerformed):
        log.error(
            "git could not be invoked, so the target was never inspected",
            target=str(target),
            reason=root.reason,
        )
        return 1
    if root is None:
        log.error(
            "target is not a git checkout",
            target=str(target),
            hint="pass --checkout <path> pointing at a governed repo checkout",
        )
        return 1
    worktree = _resolve_invoked_worktree(target=target, run=default_command_runner)
    ctx = LocalContext(
        checkout=root,
        home=Path.home(),
        run=default_command_runner,
        worktree=worktree,
    )
    unresolved = reconcile_checkout(ctx=ctx, log=log)
    if unresolved:
        log.error(
            "local first-touch reconcile incomplete",
            checkout=str(root),
            unresolved_rows=unresolved,
        )
        return 4
    log.info("local first-touch reconcile complete", checkout=str(root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
