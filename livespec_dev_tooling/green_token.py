"""green_token — advisory local cache for the pre-push full-aggregate check.

Writes a green token keyed on the current HEAD tree-hash after a
successful full check aggregate run (no skipped targets). Pre-push reads
the token and runs only the check set's WORLD-READING members when the
token matches HEAD's tree-hash and the worktree is clean.

WHAT THE TOKEN STANDS FOR, and what it never did. A tree-hash key is a
MEMOIZATION, and memoization is sound only for a pure function. `just
check` is not one, so the token memoizes only the members whose verdict
the committed tree alone decides — the TREE-PURE ones. The members that
read state outside the tree run again on every push. Which is which is
answered by `livespec_dev_tooling.check_purity` from each member's own
purity declaration, never from a list kept here; the token-memoization
contract is in this repository's own SPECIFICATION/contracts.md, in its
delegated pre-push gate section (v080).

STRICTLY advisory-local: CI remains authoritative. Any token miss, a
dirty worktree, or a missing token falls back to the full aggregate with
no behavior change.

CLI:
    python -m livespec_dev_tooling.green_token write
        Write (or overwrite) the token for the current HEAD tree.
        Called at the end of a successful full `just check` aggregate.
        Exits 0 on success.

    python -m livespec_dev_tooling.green_token check
        Exit 0 → current tree matches the cached green token AND
                  worktree is clean → caller may skip the aggregate's
                  TREE-PURE members.
        Exit 1 → no token, stale token, or dirty worktree → caller
                  must run the full aggregate.
        Never blocks a push — any error exits 1 (triggers full run).

    python -m livespec_dev_tooling.green_token world-reading TARGET ...
        Print, one per line, exactly those given targets that are
        declared world-reading or carry no purity declaration — the
        members a token match may NOT stand in for. Exit 0 on success.

    python -m livespec_dev_tooling.green_token undeclared TARGET ...
        Print, one per line, the given targets carrying no purity
        declaration, and exit 1 when there is any. This is the gate the
        aggregate runs over its own member list.

Both purity subcommands take the caller's OWN target list rather than
discovering one, because the population is a repository's aggregate and
not this library's slug set — which is what lets a consumer's justfile
make the same decision without keeping a copy of the list. Both FAIL on
an empty target list: an empty answer read as "no member reads outside
the tree" would memoize everything, which is the defect being closed.

Output discipline: the two purity subcommands write their one-name-per-line
report to stdout, which is why this file is declared in this repo's
`supervisor_entry_files`. Diagnostics stay on stderr as structlog JSON.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.pipeline import is_successful  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling import check_purity  # noqa: E402  — vendor-path-aware import.

__all__: list[str] = []

_TOKEN_FILE = "livespec-green-token.json"  # noqa: S105
_WRITE = "write"
_CHECK = "check"
_WORLD_READING = "world-reading"
_UNDECLARED = "undeclared"


def _git_dir(*, cwd: Path) -> Path:
    """Return the per-worktree git directory (always absolute path)."""
    result = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "--absolute-git-dir"],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return Path(result.stdout.strip())


def _head_tree_hash(*, cwd: Path) -> str:
    """Return the tree SHA of the current HEAD commit."""
    result = subprocess.run(  # noqa: S603
        ["git", "rev-parse", "HEAD^{tree}"],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _worktree_is_clean(*, cwd: Path) -> bool:
    """Return True when the worktree has no uncommitted modifications."""
    result = subprocess.run(  # noqa: S603
        ["git", "status", "--porcelain"],  # noqa: S607
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip() == ""


def _token_path(*, cwd: Path) -> Path:
    """Return the absolute path to the green token file for this worktree."""
    return _git_dir(cwd=cwd) / _TOKEN_FILE


def _load_stored_tree_hash(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> str | None:
    """Read and validate the stored tree hash from the token file.

    Returns the stored tree-hash string on success, or None when the
    token is absent, unreadable, or malformed (each case is logged).
    """
    try:
        path = _token_path(cwd=cwd)
        raw = path.read_text(encoding="utf-8")
        token: object = json.loads(raw)
    except FileNotFoundError:
        log.info(
            "green token check: no token found (cold path); running full aggregate",
        )
        return None
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
        subprocess.CalledProcessError,
    ) as exc:
        log.info(
            "green token check: token unreadable; running full aggregate",
            error=str(exc),
        )
        return None
    # A token whose JSON root is not an object is malformed rather than
    # unreadable, so it joins the missing-field case below on one report path.
    stored: object = None
    if isinstance(token, dict):
        stored = cast("dict[str, object]", token).get("tree_hash")
    if not isinstance(stored, str):
        log.info(
            "green token check: invalid token format; running full aggregate",
        )
        return None
    return stored


def write_token(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Write a green token for the current HEAD tree to the git dir.

    Returns 0 on success and also on any error — a failed write must
    never abort a successful check aggregate (strictly advisory-local).
    """
    try:
        tree_hash = _head_tree_hash(cwd=cwd)
        path = _token_path(cwd=cwd)
        _ = path.write_text(json.dumps({"tree_hash": tree_hash}), encoding="utf-8")
        log.info("green token written", tree_hash=tree_hash, path=str(path))
    except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover
        log.warning("green token write failed; non-blocking", error=str(exc))
    return 0


def check_token(*, cwd: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Check if the current state matches the cached green token.

    Returns 0 when the token is valid (caller may skip the aggregate).
    Returns 1 when the token is absent, stale, or the worktree is dirty
    (caller must run the full aggregate).
    """
    stored = _load_stored_tree_hash(cwd=cwd, log=log)
    if stored is None:
        return 1
    current = _head_tree_hash(cwd=cwd)
    if current != stored:
        log.info(
            "green token check: tree hash mismatch; running full aggregate",
            stored_tree_hash=stored,
            current_tree_hash=current,
        )
        return 1
    if not _worktree_is_clean(cwd=cwd):
        log.info(
            "green token check: worktree has uncommitted changes; running full aggregate",
        )
        return 1
    log.info(
        "green token check: matched — skipping the aggregate's tree-pure members",
        tree_hash=current,
    )
    return 0


def _write(*, text: str) -> None:
    """Write text to stdout and flush; discards the byte-count return value."""
    _ = sys.stdout.write(text)
    _ = sys.stdout.flush()


def _audited(
    *, targets: list[str], cwd: Path, log: structlog.stdlib.BoundLogger
) -> check_purity.PurityAudit | None:
    """The purity audit for `targets`, or None when the caller must not proceed.

    FAIL-CLOSED on both refusals, and for the same reason: every caller of this
    helper is deciding what NOT to run, so an answer it cannot trust must stop
    it rather than narrow anything.

    - An EMPTY target list is refused. Audited against nothing, every caller
      would read "no member reads outside the tree" and memoize the whole
      aggregate — the precise failure this module was changed to close.
    - A declaration naming neither purity is refused, naming the member and
      the value, because a partial classification whose remainder was never
      examined is not a classification.
    """
    if not targets:
        log.error(
            "check purity: no targets given; refusing to classify an empty check set",
            reason=(
                "a caller asks which members the green token may memoize, and an empty "
                "answer would read as 'no member reads outside the tree' — so emptiness "
                "must refuse rather than report"
            ),
        )
        return None
    result = check_purity.audit_check_purity(targets=tuple(targets), repo_root=cwd)
    if not is_successful(result):
        malformed = unsafe_perform_io(result.failure())
        log.error(
            "check purity: declaration is malformed",
            member=malformed.target,
            value=malformed.value,
            reason=malformed.reason,
        )
        return None
    return unsafe_perform_io(result.unwrap())


def _world_reading_targets(
    *, targets: list[str], cwd: Path, log: structlog.stdlib.BoundLogger
) -> int:
    """Print the given targets a token match may NOT stand in for, one per line.

    Emitted in the order the targets were given, so a caller can report "the
    members that ran" in its aggregate's own order. An UNDECLARED member joins
    the world-reading ones: the ratified contract makes no declaration mean
    world-reading, so the two must leave here together.
    """
    audit = _audited(targets=targets, cwd=cwd, log=log)
    if audit is None:
        return 1
    must_run = frozenset(audit.world_reading) | frozenset(audit.undeclared)
    _write(text="".join(f"{target}\n" for target in targets if target in must_run))
    return 0


def _undeclared_targets(*, targets: list[str], cwd: Path, log: structlog.stdlib.BoundLogger) -> int:
    """Print every given target carrying no purity declaration; exit 1 when there is one.

    The report goes to BOTH channels on purpose. Stdout carries the names for a
    caller that wants to relay them; the stderr diagnostic is what makes the
    aggregate's own output NAME the member, which the ratified scenario
    requires of it.
    """
    audit = _audited(targets=targets, cwd=cwd, log=log)
    if audit is None:
        return 1
    if not audit.undeclared:
        return 0
    log.error(
        "check aggregate member carries no purity declaration",
        members=list(audit.undeclared),
        reason=(
            "an undeclared member counts as world-reading and so still runs, but it "
            "shrinks the saving the green token exists for with nobody noticing. Declare "
            "a shipped check in its own livespec_dev_tooling/checks/<slug>.py module as "
            "CHECK_PURITY, and a repo-private member as a `# purity: <value>` annotation "
            "on its check-targets.txt line"
        ),
    )
    _write(text="".join(f"{target}\n" for target in audit.undeclared))
    return 1


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("green_token")

    parser = argparse.ArgumentParser(
        description="Advisory local green-token cache for the pre-push aggregate.",
    )
    _ = parser.add_argument(
        "command",
        choices=[_WRITE, _CHECK, _WORLD_READING, _UNDECLARED],
        help=(
            "'write' records a green token; 'check' tests if the token is valid; "
            "'world-reading' prints the given targets a token match may not stand in "
            "for; 'undeclared' names the given targets declaring no purity."
        ),
    )
    _ = parser.add_argument(
        "targets",
        nargs="*",
        default=[],
        help="The caller's own check target names, for the two purity subcommands.",
    )
    parsed = parser.parse_args()
    cwd = Path.cwd()
    targets: list[str] = list(parsed.targets)

    if parsed.command == _WRITE:
        return write_token(cwd=cwd, log=log)
    if parsed.command == _CHECK:
        return check_token(cwd=cwd, log=log)
    if parsed.command == _WORLD_READING:
        return _world_reading_targets(targets=targets, cwd=cwd, log=log)
    return _undeclared_targets(targets=targets, cwd=cwd, log=log)


if __name__ == "__main__":
    raise SystemExit(main())
