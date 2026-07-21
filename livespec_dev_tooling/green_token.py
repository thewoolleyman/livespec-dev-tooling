"""green_token — advisory local cache for the pre-push full-aggregate check.

Writes a green token keyed on the current HEAD tree-hash after a
successful full check aggregate run (no skipped targets). Pre-push reads
the token and skips the aggregate when the token matches HEAD's tree-hash
and the worktree is clean.

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
                  worktree is clean → caller can skip the aggregate.
        Exit 1 → no token, stale token, or dirty worktree → caller
                  must run the full aggregate.
        Never blocks a push — any error exits 1 (triggers full run).
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

__all__: list[str] = []

_TOKEN_FILE = "livespec-green-token.json"  # noqa: S105


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
        "green token check: matched — skipping full aggregate",
        tree_hash=current,
    )
    return 0


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
        choices=["write", "check"],
        help="'write' records a green token; 'check' tests if the token is valid.",
    )
    parsed = parser.parse_args()
    cwd = Path.cwd()

    if parsed.command == "write":
        return write_token(cwd=cwd, log=log)
    return check_token(cwd=cwd, log=log)


if __name__ == "__main__":
    raise SystemExit(main())
