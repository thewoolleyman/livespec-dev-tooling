"""Measure a proposed correction head from Git, never from the caller's claim.

The repair digest is measured here, so a reland whose change is unchanged from the
reverted attempt cannot claim a repair.
"""

from __future__ import annotations

import hashlib
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from livespec_dev_tooling._incident_run_types import OriginalRun

_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))
from returns.io import impure_safe  # noqa: E402

__all__: list[str] = ["measure_correction"]

_STAGED_TREE_NEEDS_BASE = "a staged tree is measured from the base, so the next head must be it"
_Git = Callable[[Sequence[str], bytes], bytes]


def _text(*, git: _Git, args: Sequence[str]) -> str:
    return git(args, b"").decode().strip()


def _patch_id(*, git: _Git, diff: bytes) -> str:
    return git(["patch-id", "--stable"], diff).decode().split(" ", 1)[0]


@impure_safe
def measure_correction(
    *, git: _Git, original: OriginalRun, next_head_sha: str, base_ref: str, staged_tree: str
) -> tuple[str, str, str]:
    """Base, staged tree and repair digest; the digest is empty for the reverted change."""
    head = next_head_sha
    base = _text(git=git, args=["merge-base", base_ref, head])
    _ = git(["merge-base", "--is-ancestor", original.revert_sha, base], b"")
    if staged_tree and head != base:
        raise ValueError(_STAGED_TREE_NEEDS_BASE)
    end = staged_tree or head
    tree = _text(git=git, args=["rev-parse", "--verify", end + "^{tree}"])
    proposed = git(["diff", "--binary", base, end], b"")
    reverted = git(["diff", "--binary", original.revert_sha, original.revert_sha + "^"], b"")
    unchanged = not proposed.strip() or _patch_id(git=git, diff=proposed) == _patch_id(
        git=git, diff=reverted
    )
    return base, tree, "" if unchanged else hashlib.sha256(proposed).hexdigest()
