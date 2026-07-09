"""assert_never_exhaustiveness — every `match` ends with `case _: assert_never(<subject>)`.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-assert-never-exhaustiveness` row),
every `match` statement in `livespec/**` MUST terminate with
a `case _: assert_never(<subject>)` arm where `<subject>` is
the match-statement's subject expression. Conservative scope:
every match, regardless of subject type.

The check walks the git-derived first-party `.py` universe
(`config.resolve_check_universe`), parses each via `ast`, and
inspects every `Match` node. The final case (`node.cases[-1]`)
MUST be:

- A wildcard pattern (`case _:`) — `MatchAs(pattern=None,
  name=None)`.
- A body that is exactly one `Expr` statement whose value is
  a `Call` to a name `assert_never` with one positional arg.

Cycle 156 implements the structural check (final case is
wildcard + body is `assert_never(...)` call). Subsequent
cycles can tighten to verify the call's argument equals the
match subject.

Phase-0 rollout severity (fleet-check-coverage): the file
universe is the git-derived first-party `.py` set
(`config.iter_first_party_py_files`) rather than a
`config.source_trees` walk. `config.source_trees` is retained
ONLY as a delta-WARN severity classifier: a non-compliant
`match` in a file UNDER a `source_trees` tree keeps today's
hard gate (an `error`-level diagnostic contributing to exit 1);
the same violation in a file newly pulled into the git-derived
universe emits at WARN (`warning`-level, `phase="0-warn"`, no
exit-1 contribution) until Phase 2 flips its repo to the hard
gate. A genuinely codeless repo (zero first-party `.py`) passes
with an info-level "nothing to check".

Output discipline: per spec, `print` (T20) and
`sys.stderr.write` (`check-no-write-direct`) are banned in
dev-tooling/**. Diagnostics flow through structlog (JSON to
stderr); the vendored copy under `.claude-plugin/scripts/
_vendor/structlog` is added to `sys.path` at module import time.
"""

from __future__ import annotations

import ast
import sys
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


def _is_wildcard_pattern(*, pattern: ast.pattern) -> bool:
    return isinstance(pattern, ast.MatchAs) and pattern.pattern is None and pattern.name is None


def _is_assert_never_call(*, body: list[ast.stmt]) -> bool:
    if len(body) != 1 or not isinstance(body[0], ast.Expr):
        return False
    expr = body[0].value
    return (
        isinstance(expr, ast.Call)
        and isinstance(expr.func, ast.Name)
        and expr.func.id == "assert_never"
    )


def _is_compliant_terminator(*, case: ast.match_case) -> bool:
    return _is_wildcard_pattern(pattern=case.pattern) and _is_assert_never_call(body=case.body)


def _find_offending_match_lines(*, source: str) -> list[int]:
    tree = ast.parse(source)
    out: list[int] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Match) and (
            len(node.cases) == 0 or not _is_compliant_terminator(case=node.cases[-1])
        ):
            out.append(node.lineno)
    return out


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("assert_never_exhaustiveness")
    root, universe = resolve_check_universe()
    if not universe:
        log.info("no first-party Python to check")
        return 0
    config = load_config(repo_root=root)
    legacy_offenders: list[tuple[Path, int]] = []
    newly_offenders: list[tuple[Path, int]] = []
    for rel in universe:
        source = (root / rel).read_text(encoding="utf-8")
        for lineno in _find_offending_match_lines(source=source):
            if is_under_any_tree(rel=rel, trees=config.source_trees):
                legacy_offenders.append((rel, lineno))
            else:
                newly_offenders.append((rel, lineno))
    for path, lineno in legacy_offenders:
        log.error(
            "match must terminate with `case _: assert_never(<subject>)`",
            file=str(path),
            line=lineno,
        )
    for path, lineno in newly_offenders:
        log.warning(
            "match must terminate with `case _: assert_never(<subject>)` — "
            "newly git-derived coverage; Phase-0 WARN (hard-fails once this "
            "repo is flipped to the hard gate in Phase 2)",
            file=str(path),
            line=lineno,
            phase="0-warn",
            newly_covered=True,
        )
    return 1 if legacy_offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
