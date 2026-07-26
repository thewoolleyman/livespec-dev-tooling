"""local_reconcile — LOCAL-vantage first-touch reconcile of a governed checkout.

The generalized successor to `just bootstrap`'s local first-touch steps
(per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Governed-repo lifecycle"): runs the idempotent local setup an arbitrary
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

from livespec_dev_tooling.fleet._context import RowPass, RowSkip
from livespec_dev_tooling.fleet._contract_local_rows import LOCAL_OBLIGATION_ROWS
from livespec_dev_tooling.fleet._local_context import (
    CommandRunner,
    LocalContext,
    default_command_runner,
)

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = []


def _resolve_checkout_root(*, target: Path, run: CommandRunner) -> Path | None:
    """Resolve the primary checkout root for `target`, or None when not a checkout.

    Uses `git rev-parse --git-common-dir` so the resolution is
    worktree-safe: from a linked worktree the common dir is the
    primary's shared `.git`, whose parent is the primary checkout root.
    """
    result = run(args=["git", "rev-parse", "--git-common-dir"], cwd=target)
    if result.returncode != 0:
        return None
    common = Path(result.stdout.strip())
    if not common.is_absolute():
        common = (target / common).resolve()
    return common.parent


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
        if row.assert_local is not None:
            outcome = row.assert_local(ctx=ctx)
            if isinstance(outcome, RowPass):
                log.info("row already satisfied", row=row.row_id, note=outcome.note)
                continue
        fixed = row.reconcile_local(ctx=ctx)
        if isinstance(fixed, RowPass):
            log.info("row reconciled", row=row.row_id, note=fixed.note)
        elif isinstance(fixed, RowSkip):
            log.info("row not applicable", row=row.row_id, reason=fixed.reason)
        elif fixed.severity == "warning":
            log.warning(
                "row needs out-of-band action (detect-and-guide)",
                row=row.row_id,
                hint=fixed.message,
            )
        else:
            unresolved += 1
            log.error("row did not reconcile", row=row.row_id, detail=fixed.message)
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


def _resolve_invoked_worktree(*, target: Path, run: CommandRunner) -> Path:
    """The work-tree root `target` sits in.

    Distinct from `_resolve_checkout_root`: that returns the PRIMARY root via
    `--git-common-dir`, which is what shared obligations need. This returns the
    root of the worktree actually invoked, which per-worktree artifacts need.

    No failure branch: the sole caller resolves the checkout root FIRST and
    bails when that fails, so by the time this runs `target` is known to be a
    git checkout and `--show-toplevel` cannot fail. A dead error path here
    would be untestable by construction.
    """
    result = run(args=["git", "rev-parse", "--show-toplevel"], cwd=target)
    return Path(result.stdout.strip())


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
