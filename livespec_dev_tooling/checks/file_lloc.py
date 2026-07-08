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

Phase-0 rollout severity: widening the file universe from three
hardcoded trees to the whole git index would turn every previously
unwalked repo (the orchestrator's 2,616-line `dispatcher.py`, this
package's own 88 files) red in one step. To avoid that, the three
legacy trees are RETAINED — not as the file universe, but as a
severity classifier (`_LEGACY_HARDFAIL_TREES`). A file that falls
under a legacy tree keeps today's hard gate (soft-warn 201-250,
hard-fail >250, exit 1); a file newly pulled into the git-derived
universe emits ALL its LLOC diagnostics at WARN (even >250, with NO
exit-1 contribution) until Phase 2 flips its repo to the hard gate.
The classifier is removed in Phase 2.

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

from livespec_dev_tooling.config import iter_first_party_py_files  # noqa: E402

__all__: list[str] = []


# Phase-0 severity classifier: files under these legacy trees retain the
# hard gate; files newly pulled into the git-derived universe emit at WARN
# until Phase-2 flips them per-repo. Remove in Phase 2.
_LEGACY_HARDFAIL_TREES = (
    Path(".claude-plugin") / "scripts" / "livespec",
    Path(".claude-plugin") / "scripts" / "bin",
    Path("dev-tooling"),
)
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


def _under_legacy_hardfail_tree(*, rel: Path) -> bool:
    """True iff `rel` (a repo-root-relative path) sits under a legacy hard-fail tree."""
    return any(rel.is_relative_to(tree) for tree in _LEGACY_HARDFAIL_TREES)


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
    cwd = Path.cwd()
    legacy_soft_offenders: list[tuple[Path, int]] = []
    legacy_hard_offenders: list[tuple[Path, int]] = []
    newly_covered_offenders: list[tuple[Path, int]] = []
    for rel in iter_first_party_py_files(repo_root=cwd):
        source = (cwd / rel).read_text(encoding="utf-8")
        lloc = _count_lloc(source=source)
        if lloc <= _LLOC_SOFT_CEILING:
            continue
        if not _under_legacy_hardfail_tree(rel=rel):
            newly_covered_offenders.append((rel, lloc))
        elif lloc > _LLOC_HARD_CEILING:
            legacy_hard_offenders.append((rel, lloc))
        else:
            legacy_soft_offenders.append((rel, lloc))
    for path, lloc in legacy_soft_offenders:
        log.warning(
            "file LLOC exceeds 200-line soft ceiling — flag for refactor",
            file=str(path),
            lloc=lloc,
            soft_ceiling=_LLOC_SOFT_CEILING,
            hard_ceiling=_LLOC_HARD_CEILING,
        )
    for path, lloc in newly_covered_offenders:
        log.warning(
            "file LLOC exceeds ceiling — newly git-derived coverage; Phase-0 WARN "
            "(hard-fails once this repo is flipped to the hard gate in Phase 2)",
            file=str(path),
            lloc=lloc,
            soft_ceiling=_LLOC_SOFT_CEILING,
            hard_ceiling=_LLOC_HARD_CEILING,
            phase="0-warn",
            newly_covered=True,
        )
    for path, lloc in legacy_hard_offenders:
        log.error(
            "file LLOC exceeds 250-line hard ceiling",
            file=str(path),
            lloc=lloc,
            hard_ceiling=_LLOC_HARD_CEILING,
        )
    if legacy_hard_offenders:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
