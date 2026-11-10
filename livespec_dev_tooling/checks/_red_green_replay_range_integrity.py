"""Range-validation integrity of each commit's own message and recorded evidence.

`red_green_replay`'s commit-range validation used to judge a commit by the
PRESENCE of trailer keys in its message, so two factory defects published
commits it accepted (work-item livespec-dev-tooling-a4w7qr):

1. A TRAILER-ONLY commit. git runs the commit-msg hook BEFORE its empty-message
   abort, and the hooks' trailer writers (`git interpret-trailers --in-place`)
   turned an empty message into a trailer block, so the abort never fired and
   the first trailer became the commit's subject.
2. A REBASED commit keeping stale `TDD-Red-*` trailers whose recorded
   `TDD-Red-Test-File-Checksum` no longer matches the test file on the commit's
   own tree.

This module judges every non-merge commit in the range on those two properties,
whether or not the commit touches product impl `.py`: a trailer-only commit is
malformed whatever it changed.

A subject is a trailer when it has the `Key: value` shape and its key is not a
conventional-commit type. Conventional types (`fix: …`, `chore: …`) share the
shape and are exactly what a subject should be, so they are the one vocabulary
excluded; a scoped type (`fix(scope): …`, `fabro(<run>): …`) never matches the
key shape at all because of the parenthesis.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

# Make the script's own directory importable so the sibling `_*` module resolves
# when this module is loaded standalone (the importlib test path).
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from _red_green_replay_collect import collect_recorded_tests  # noqa: E402  — sibling private import

if TYPE_CHECKING:  # pragma: no cover
    import structlog.stdlib

__all__: list[str] = [
    "SUBJECT_CHECK_ID",
    "SUBJECT_HINT",
    "check_range_integrity",
    "validate_range_evidence",
]

SUBJECT_CHECK_ID: str = "red-green-replay-range-trailer-subject"
SUBJECT_HINT: str = (
    "Every commit in the range must open with a subject line that is not a git trailer "
    "(`Key: value`). A commit whose whole message is trailers is what a commit-msg hook "
    "produces when it appends trailers to an EMPTY message before git's empty-message abort. "
    "Remedy: rewrite the range so the commit carries a real conventional-commit subject, "
    "then redo it through the hook. There is no flag, skip or subject prefix that exempts it."
)
_TRAILER_SUBJECT_RE = re.compile(r"^([A-Za-z][A-Za-z0-9-]*):[ \t]+\S")
_CONVENTIONAL_TYPES = frozenset(
    {
        "build",
        "chore",
        "ci",
        "docs",
        "feat",
        "fix",
        "perf",
        "refactor",
        "revert",
        "style",
        "test",
        "tests",
    }
)


def _message(*, sha: str) -> str:
    done = subprocess.run(
        ["git", "log", "-1", "--format=%B", sha],
        capture_output=True,
        text=True,
        check=False,
    )
    return done.stdout


def _subject_is_trailer(*, message: str) -> bool:
    found = _TRAILER_SUBJECT_RE.match(message.lstrip("\n"))
    return found is not None and found.group(1).lower() not in _CONVENTIONAL_TYPES


def check_range_integrity(*, shas: list[str], log: structlog.stdlib.BoundLogger) -> int:
    """Return 0 when every commit in `shas` is intact, else log each finding and return 1."""
    trailer_subjects = [sha for sha in shas if _subject_is_trailer(message=_message(sha=sha))]
    if not trailer_subjects:
        return 0
    log.error(
        "commits in origin/master..HEAD have a trailer as their subject line",
        check_id=SUBJECT_CHECK_ID,
        violating_commits=trailer_subjects,
        hint=SUBJECT_HINT,
    )
    return 1


def validate_range_evidence(
    *, shas: list[str], base_ref: str, log: structlog.stdlib.BoundLogger
) -> int:
    """Judge each commit's own message, then collect each recorded test; return 0 or 1.

    Integrity runs first and a failure ends the validation: collecting the
    recorded test of a commit whose message is already malformed costs seconds
    per commit and adds nothing the finding does not already say.
    """
    return check_range_integrity(shas=shas, log=log) or collect_recorded_tests(
        shas=shas, base_ref=base_ref, log=log
    )
