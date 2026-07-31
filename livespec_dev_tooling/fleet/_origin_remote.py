"""Resolve WHICH MEMBER this checkout is, from its `origin` remote.

Split out of `_context` to keep that file under the 250-LLOC hard
ceiling the `gh`-seam conversion pushed it past — the same
private-sibling split as `_pin_walk_failure` and `_ci_matrix_parse`.
`_context` re-exports both names, so no consumer import changes.

The split is not only arithmetic. These two are the ONE remaining
`subprocess` caller in the fleet package that is NOT behind an injected
seam, and their `subprocess.run` is UNGUARDED: an absent `git` raises
`FileNotFoundError` straight out of `resolve_owner`. That is a real
defect and it is deliberately NOT fixed here — the pair is the
`livespec-dev-tooling-dx8l`-blocked unit whose conversion must land
consumer wiring FIRST, in `livespec-orchestrator-beads-fabro`
(`codex_yolo_gate.py`), because clause (d) couples the two. Isolating
them in their own module is what makes that a clean single-file unit
when it is unblocked.
"""

from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__: list[str] = ["resolve_owner", "resolve_repo_name"]


# Matches the two canonical github.com remote URL forms emitted by
# `git remote get-url origin`, mirroring the sibling
# `branch_protection_alignment` resolver: the owner identifier comes
# from the local remote rather than a hardcoded constant.
_REMOTE_URL_PATTERN = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?/?$"
)


def _origin_remote_match(*, cwd: Path | None = None) -> re.Match[str] | None:
    """Match `git remote get-url origin` against the owner/repo pattern, or None.

    One parse shared by `resolve_owner` and `resolve_repo_name`: the two answers
    come from the same remote URL, and a second copy of the pattern-and-subprocess
    dance would be a rule with two copies, which drifts.
    """
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
        cwd=None if cwd is None else str(cwd),
    )
    if completed.returncode != 0:
        return None
    return _REMOTE_URL_PATTERN.match(completed.stdout.strip())


def resolve_owner(*, cwd: Path | None = None) -> str | None:
    """Resolve the GitHub owner from `git remote get-url origin`, or None."""
    match = _origin_remote_match(cwd=cwd)
    return None if match is None else match.group(1)


def resolve_repo_name(*, cwd: Path | None = None) -> str | None:
    """Resolve the repository's short name from `git remote get-url origin`, or None.

    This is the "which member am I RUNNING AS" derivation. It is DERIVED rather
    than configured on purpose: a config key naming the running repo would be a
    second source of truth that can drift from the checkout it describes, and the
    remote already knows the answer. `.git` suffix and trailing slash are stripped
    by the shared pattern, so a member's name matches the manifest entry directly.
    """
    match = _origin_remote_match(cwd=cwd)
    return None if match is None else match.group(2)
