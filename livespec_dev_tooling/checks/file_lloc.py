"""file_lloc — per-file LLOC two-tier policy (soft warn at 200, hard fail at 250).

Per `SPECIFICATION/constraints.md` §"File LLOC ceiling" (post-v005),
every first-party `.py` file SHOULD have at most 200 logical lines of
code (LLOC) and MUST have at most 250 LLOC.

The set of files this check inspects is the git-derived first-party
`.py` universe (`config.iter_first_party_py_files`): `git ls-files
'*.py'` minus `_vendor/`, the configured test tree, `templates/**`,
and `@generated`-marked files — NOT a hardcoded tree allowlist. The
old hardcoded `_COVERED_TREES` tuple (`.claude-plugin/scripts/livespec`,
`.claude-plugin/scripts/bin`, `dev-tooling`) resolved its files by
`rglob`, so in any repo whose package dir is not named `livespec/` —
the orchestrator (`livespec_orchestrator_beads_fabro/`) and this
package (`livespec_dev_tooling/`) itself — those trees did not exist,
the check walked ZERO files, and exited 0: a scan that scanned nothing
reported green. Routing the walk through the git index (the
fleet-check-coverage mechanism; `livespec` repo's
`plan/fleet-check-coverage/research/design.md`) closes that fail-open
hole.

LLOC excludes blank lines, comment-only lines, and module/class/
function docstrings — it counts only executable statements. The
check tokenizes each `.py` via the standard library `tokenize`
module and filters docstring lines via `ast`.

Two-tier policy:

- 201-250 LLOC — SOFT ceiling. The file passes the check (exit 0)
  but a `warning`-level structured diagnostic is emitted to stderr
  flagging the file for refactoring.
- > 250 LLOC — HARD ceiling. The file fails the check (exit 1)
  with an `error`-level structured diagnostic.

The two-tier split removes the mid-Green-amend wedge where an
in-progress refactor naturally pushes LLOC above 200 and would
otherwise force a sibling-module extraction in the same amend.

THE CEILING IS UNCONDITIONAL — there is no per-repo opt-in and no
severity classifier. Every over-ceiling file in the git-derived
universe is gated identically in every governed repo.

That was NOT always true, and the history is worth keeping because it
is a rollout pattern rather than a quirk. When the universe widened
from three hardcoded trees to the whole git index, flipping every
previously-unwalked repo red in one step was unacceptable, so the
rollout ran in two phases: the legacy trees were retained as a
severity CLASSIFIER (`_LEGACY_HARDFAIL_TREES`), and a repo opted its
whole universe into the hard gate by committing
`file_lloc_hard_gate = true`. Absent or false meant a newly-covered
file only WARNed, carrying a `phase="0-warn"` / `newly_covered=True`
marker and contributing no exit-1.

Both are now RETIRED (`livespec-dev-tooling-426a`). The opt-in made
enforcement repo-OPTIONAL: `file_lloc_hard_gate` absent meant a repo
disarmed the ceiling for its entire package by never declaring
anything, and the omission read as conformance. Retiring it was gated
on every governed repo satisfying the ceiling first, per the
enforcement-before-adoption corollary in livespec
`.ai/ci-gate-discipline.md` — verified before the flip: all eight
Python-carrying fleet repos declared the gate, and the ninth
(`livespec-console-beads-fabro`) is a Rust repo with zero tracked
`.py`. So the retirement changed no repo's result on the day it
landed; what it changes is that a NEW repo can no longer opt out, and
a new over-ceiling file can no longer hide behind a missing key.

Consumers may still carry a `file_lloc_hard_gate` line; it is inert
and read by nothing. Removing it is per-repo cleanup, not a
precondition.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import sys
import tokenize
from io import BytesIO
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import resolve_check_universe  # noqa: E402

__all__: list[str] = []


_LLOC_SOFT_CEILING = 200
_LLOC_HARD_CEILING = 250
_NON_LLOC_TOKEN_TYPES = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENCODING,
        tokenize.ENDMARKER,
    }
)


def _docstring_lines(*, source: str) -> set[int]:
    """Return line numbers covered by module/class/function docstrings."""
    tree = ast.parse(source)
    out: set[int] = set()
    holders: list[ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            holders.append(node)
    for holder in holders:
        body = holder.body
        if (
            len(body) > 0
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            first = body[0]
            assert first.end_lineno is not None  # noqa: S101 — narrowing for arithmetic
            out.update(range(first.lineno, first.end_lineno + 1))
    return out


def _count_lloc(*, source: str) -> int:
    docstring_lines = _docstring_lines(source=source)
    code_lines: set[int] = set()
    tokens = tokenize.tokenize(BytesIO(source.encode("utf-8")).readline)
    for tok in tokens:
        if tok.type in _NON_LLOC_TOKEN_TYPES:
            continue
        line = tok.start[0]
        if line in docstring_lines:
            continue
        code_lines.add(line)
    return len(code_lines)


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("file_lloc")
    root, universe = resolve_check_universe()
    soft_offenders: list[tuple[Path, int]] = []
    hard_offenders: list[tuple[Path, int]] = []
    for rel in universe:
        source = (root / rel).read_text(encoding="utf-8")
        lloc = _count_lloc(source=source)
        if lloc <= _LLOC_SOFT_CEILING:
            continue
        if lloc > _LLOC_HARD_CEILING:
            hard_offenders.append((rel, lloc))
        else:
            soft_offenders.append((rel, lloc))
    for path, lloc in soft_offenders:
        log.warning(
            "file LLOC exceeds 200-line soft ceiling — flag for refactor",
            file=str(path),
            lloc=lloc,
            soft_ceiling=_LLOC_SOFT_CEILING,
            hard_ceiling=_LLOC_HARD_CEILING,
        )
    for path, lloc in hard_offenders:
        log.error(
            "file LLOC exceeds 250-line hard ceiling",
            file=str(path),
            lloc=lloc,
            hard_ceiling=_LLOC_HARD_CEILING,
        )
    if hard_offenders:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
