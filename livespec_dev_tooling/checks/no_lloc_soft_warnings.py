"""no_lloc_soft_warnings — 201-250 LLOC soft-band scan with a severity lever.

Per `SPECIFICATION/constraints.md` section "File LLOC ceiling" (post-v008),
this is the soft-band analog of `check-no-todo-registry`: it flags any
first-party `.py` file in the 201-250 LLOC soft band, forcing refactor
work before a release.

The scan ALWAYS runs (no skip carve-out). A self-documenting severity
lever controls only the release-context behavior: when
`LIVESPEC_FAIL_IF_LLOC_SOFT_WARNINGS_EXIST` is set to a non-empty value
(CI sets it to `true` for the release context), soft-band offenders
fail the check (exit 1, error-level diagnostics). When the lever is
unset (or empty), the SAME findings are logged at WARNING level and the
check exits 0, so soft-band files surface during authoring without
blocking per-commit `just check`. This replaces the prior
`LIVESPEC_RELEASE_GATE` skip carve-out (epic li-cvaudit, cvtodo) — the
old carve-out SILENTLY skipped the scan entirely when the gate was unset.

The check tokenizes each `.py` via the same algorithm as
`file_lloc.py` (the per-commit two-tier check). Helpers are
duplicated rather than imported because each `dev-tooling/checks/
<name>.py` is a self-contained Python module per the directory's
CLAUDE.md.

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import os
import sys
import tokenize
from io import BytesIO
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    is_under_any_tree,
    load_config,
    resolve_check_universe,
)

__all__: list[str] = []


_LLOC_SOFT_CEILING = 200
_LLOC_HARD_CEILING = 250
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_LLOC_SOFT_WARNINGS_EXIST"
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
    log = structlog.get_logger("no_lloc_soft_warnings")
    root, universe = resolve_check_universe()
    config = load_config(repo_root=root)
    legacy_soft_offenders: list[tuple[Path, int]] = []
    newly_covered_soft_offenders: list[tuple[Path, int]] = []
    for rel in universe:
        source = (root / rel).read_text(encoding="utf-8")
        lloc = _count_lloc(source=source)
        if not (_LLOC_SOFT_CEILING < lloc <= _LLOC_HARD_CEILING):
            continue
        if is_under_any_tree(rel=rel, trees=config.covered_trees):
            legacy_soft_offenders.append((rel, lloc))
        else:
            newly_covered_soft_offenders.append((rel, lloc))
    fail = bool(os.environ.get(_FAIL_ENV_VAR))
    if legacy_soft_offenders:
        for path, lloc in legacy_soft_offenders:
            emit = log.error if fail else log.warning
            emit(
                "file in 201-250 LLOC soft band",
                file=str(path),
                lloc=lloc,
                soft_ceiling=_LLOC_SOFT_CEILING,
                hard_ceiling=_LLOC_HARD_CEILING,
                fail_env_var=_FAIL_ENV_VAR,
                failing=fail,
            )
    for path, lloc in newly_covered_soft_offenders:
        log.warning(
            "file in 201-250 LLOC soft band — newly git-derived coverage; Phase-0 WARN "
            "(hard-fails once this repo is flipped to the hard gate in Phase 2)",
            file=str(path),
            lloc=lloc,
            soft_ceiling=_LLOC_SOFT_CEILING,
            hard_ceiling=_LLOC_HARD_CEILING,
            fail_env_var=_FAIL_ENV_VAR,
            failing=False,
            phase="0-warn",
            newly_covered=True,
        )
    if legacy_soft_offenders and fail:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
