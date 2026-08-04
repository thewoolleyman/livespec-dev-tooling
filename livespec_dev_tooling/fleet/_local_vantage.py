"""_local_vantage — resolve the SELF member's local checkout, or nothing.

Extracted from `fleet_conformance.py` when the local-vantage read landed
(work-item livespec-dev-tooling-rjyc). The concern is small, wholly
self-contained, and has two fail-closed branches that are far easier to
exercise directly than through `main()` — which is why it lives here
rather than inline in the CLI module.

⛔ SELF ONLY. What this resolves is the member the run is executing
INSIDE, and nothing else. The consumption half of a conformance verdict
comes from OTHER members' trees, read at their canonical refs; only the
declaration and the member's own sources come from this checkout.
Generalize a local read to siblings and a PR could manufacture "no
sibling consumes this", which is the one thing it must never get to say.
See `_rows_public_api_conformance._local_root_for`, which enforces the
name equality this pair is fed into.

Output discipline matches sibling modules: structlog JSON to stderr; no
`print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.config import GitToplevelError, resolve_repo_root  # noqa: E402
from livespec_dev_tooling.fleet._context import OriginRemoteUnresolved  # noqa: E402

__all__: list[str] = []


def local_vantage(
    *,
    running_as: IOResult[str, OriginRemoteUnresolved],
    log: structlog.stdlib.BoundLogger,
) -> tuple[str | None, Path | None]:
    """The self member and its checkout root, or `(None, None)` when unresolvable.

    FAIL-CLOSED, and the closed direction is the FORGE vantage every member had
    before: an unresolvable local checkout leaves the whole roster read at its
    canonical ref rather than guessing. It never falls back to a directory name
    or a configured value — a wrong self member would hand one repo's tree to
    another repo's verdict, which is worse than reading a stale one.

    The unresolvable cases are REPORTED rather than swallowed. Both are ordinary
    off-checkout conditions rather than defects, so they log at info; silence
    would make the row's vantage impossible to explain from a run log.
    """
    if isinstance(running_as, IOFailure):
        unresolved = unsafe_perform_io(running_as.failure())
        log.info(
            "local vantage unavailable — grading every member from its canonical ref",
            reason=unresolved.reason,
            detail=unresolved.detail,
        )
        return (None, None)
    repo = unsafe_perform_io(running_as.unwrap())
    try:
        root = resolve_repo_root()
    except GitToplevelError as outside_worktree:
        # NARROW and genuinely inhabited: the lane also runs from contexts that
        # are not a git working tree at all, and that is the one condition this
        # resolution cannot answer.
        log.info(
            "local vantage unavailable — not inside a git working tree",
            member=repo,
            detail=str(outside_worktree),
        )
        return (None, None)
    return (repo, root)
