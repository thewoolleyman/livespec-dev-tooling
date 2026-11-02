"""Same-tree pre-commit evidence helpers for the suite-green replay leg."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import structlog.stdlib

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _red_green_replay_trailers import write_trailers  # noqa: E402

from livespec_dev_tooling.green_token import PreCommitAggregateEvidence  # noqa: E402

__all__: list[str] = [
    "PreCommitAggregateEvidence",
    "reuse_pre_commit_evidence",
    "staged_tree_hash",
]


def staged_tree_hash(*, cwd: Path) -> str | None:
    """Return the current index tree, or None when the hook cannot establish it."""
    try:
        result = subprocess.run(
            ["git", "write-tree"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return result.stdout.strip() or None


def reuse_pre_commit_evidence(
    *,
    evidence: PreCommitAggregateEvidence | None,
    index_tree: str | None,
    log: structlog.stdlib.BoundLogger,
    msg_path: Path,
) -> bool:
    """Write named same-tree evidence, returning whether the aggregate was reusable."""
    if evidence is None or evidence.tree_hash != index_tree:
        return False
    log.info(
        "suite-green-reused-pre-commit-aggregate",
        check_id="red-green-replay-suite-green-reused-pre-commit-aggregate",
        tree_hash=index_tree,
        run_id=evidence.run_id,
    )
    write_trailers(
        msg_path=msg_path,
        trailers=(
            ("TDD-Suite-Green-Scope", "full-suite"),
            ("TDD-Suite-Green-Output-Checksum", evidence.output_checksum),
            ("TDD-Suite-Green-Captured-At", evidence.captured_at),
            ("TDD-Suite-Green-Producer", evidence.run_id),
        ),
    )
    return True
