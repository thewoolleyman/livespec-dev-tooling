"""global_writes — bans `global`/`nonlocal` statements in `livespec/**`.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-global-writes` row), no module-level
mutable state writes from functions are permitted in
`livespec/**`. The `global` keyword is the canonical
declarator for writing module state from a function body and
is banned. The `nonlocal` keyword (writing enclosing-scope
state from nested functions) is banned for the same reason —
state flows down via parameters, up via return values, never
through scoped mutation.

The check walks the git-derived first-party `.py` universe
(`config.resolve_check_universe`), parses each via `ast`, and
inspects every `Global` and `Nonlocal` node.

Phase-0 rollout severity (fleet-check-coverage): the file
universe is the git-derived first-party `.py` set
(`config.iter_first_party_py_files`) rather than a
`config.source_trees` walk. `config.source_trees` is retained
ONLY as a delta-WARN severity classifier: a `global`/`nonlocal`
in a file UNDER a `source_trees` tree keeps today's hard gate
(an `error`-level diagnostic contributing to exit 1); the same
violation in a file newly pulled into the git-derived universe
emits at WARN (`warning`-level, `phase="0-warn"`, no exit-1
contribution) until Phase 2 flips its repo to the hard gate. A
genuinely codeless repo (zero first-party `.py`) passes with an
info-level "nothing to check".

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


def _find_offenders(*, source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Global):
            out.append((node.lineno, "global"))
        elif isinstance(node, ast.Nonlocal):
            out.append((node.lineno, "nonlocal"))
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
    log = structlog.get_logger("global_writes")
    root, universe = resolve_check_universe()
    if not universe:
        log.info("no first-party Python to check")
        return 0
    config = load_config(repo_root=root)
    legacy_offenders: list[tuple[Path, int, str]] = []
    newly_offenders: list[tuple[Path, int, str]] = []
    for rel in universe:
        source = (root / rel).read_text(encoding="utf-8")
        for lineno, keyword in _find_offenders(source=source):
            record = (rel, lineno, keyword)
            if is_under_any_tree(rel=rel, trees=config.source_trees):
                legacy_offenders.append(record)
            else:
                newly_offenders.append(record)
    for path, lineno, keyword in legacy_offenders:
        log.error(
            "module-level mutable writes from functions are banned",
            file=str(path),
            line=lineno,
            keyword=keyword,
        )
    for path, lineno, keyword in newly_offenders:
        log.warning(
            "module-level mutable writes from functions are banned — newly "
            "git-derived coverage; Phase-0 WARN (hard-fails once this repo is "
            "flipped to the hard gate in Phase 2)",
            file=str(path),
            line=lineno,
            keyword=keyword,
            phase="0-warn",
            newly_covered=True,
        )
    return 1 if legacy_offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
