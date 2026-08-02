"""match_keyword_only — keyword-pattern destructuring on livespec classes.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-match-keyword-only` row), every
`match` statement's class pattern resolving to a livespec-
authored class binds via keyword sub-patterns (`Foo(x=x)`),
not positional (`Foo(x)`). Third-party library class
destructures (the `returns` package's types — `Success`,
`Failure`, `IOSuccess`, `IOFailure`) are permitted
positionally because their `__match_args__` is fixed by
upstream.

The check walks the git-derived first-party `.py` universe
(`config.resolve_check_universe`), parses each via `ast`, and
inspects every `MatchClass` pattern (the AST node for a class
destructure inside a `match`/`case` statement). The class-name
terminal is extracted via `ast.unparse(node.cls).rsplit(".",
maxsplit=1)[-1]` (so `IOSuccess` matches whether bare or
`returns.io.IOSuccess`). Positional sub-patterns are recorded
in `node.patterns`; keyword sub-patterns are in
`node.kwd_patterns` / `node.kwd_attrs`. A class pattern with
non-empty `node.patterns` and a class name OUTSIDE the
third-party allowlist surfaces as a violation.

Phase-0 rollout severity (fleet-check-coverage): the file
universe is the git-derived first-party `.py` set
(`config.iter_first_party_py_files`) rather than a
`config.source_trees` walk. `config.source_trees` is retained
ONLY as a delta-WARN severity classifier: a positional class
pattern in a file UNDER a `source_trees` tree keeps today's
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


_THIRD_PARTY_POSITIONAL_OK = frozenset({"Success", "Failure", "IOSuccess", "IOFailure"})


def _terminal_class_name(*, cls_node: ast.expr) -> str:
    return ast.unparse(cls_node).rsplit(".", maxsplit=1)[-1]


def _find_offending_match_classes(*, source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.MatchClass) or len(node.patterns) == 0:
            continue
        terminal = _terminal_class_name(cls_node=node.cls)
        if terminal not in _THIRD_PARTY_POSITIONAL_OK:
            out.append((node.cls.lineno, terminal))
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
    log = structlog.get_logger("match_keyword_only")
    root, universe = resolve_check_universe()
    if not universe:
        log.info("no first-party Python to check")
        return 0
    config = load_config(repo_root=root)
    legacy_offenders: list[tuple[Path, int, str]] = []
    newly_offenders: list[tuple[Path, int, str]] = []
    for rel in universe:
        source = (root / rel).read_text(encoding="utf-8")
        for lineno, class_name in _find_offending_match_classes(source=source):
            record = (rel, lineno, class_name)
            if is_under_any_tree(rel=rel, trees=config.source_trees):
                legacy_offenders.append(record)
            else:
                newly_offenders.append(record)
    for path, lineno, class_name in legacy_offenders:
        log.error(
            "positional class pattern requires keyword binding",
            file=str(path),
            line=lineno,
            class_name=class_name,
        )
    for path, lineno, class_name in newly_offenders:
        log.warning(
            "positional class pattern requires keyword binding — newly "
            "git-derived coverage; Phase-0 WARN (hard-fails once this repo is "
            "flipped to the hard gate in Phase 2)",
            file=str(path),
            line=lineno,
            class_name=class_name,
            phase="0-warn",
            newly_covered=True,
        )
    return 1 if legacy_offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
