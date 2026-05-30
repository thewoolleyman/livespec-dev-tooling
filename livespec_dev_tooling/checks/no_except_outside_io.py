"""no_except_outside_io — `try/except` confined to `io/` and supervisor bug-catchers.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-no-except-outside-io` row), catching
exceptions (`try/except`) outside `livespec/io/**` is
permitted only in supervisor bug-catchers — the top-level
`try/except Exception` block inside `main()` of
`livespec/commands/*.py` and `livespec/doctor/run_static.py`.
Anywhere else under `livespec/**`, `try/except` is banned —
pure layers handle expected failures via the ROP railway
(`Result.bind`, `Result.alt`).

The check walks every `.py` file under `.claude-plugin/
scripts/livespec/`, parses each via `ast`, and inspects every
`Try` node (the AST representation of a `try/except`
statement). Files under `io/` are wholesale exempt. For files
under `commands/` and `doctor/run_static.py`, only the
direct-child `Try` nodes inside the `main()` function body
are exempt — `try/except` in helper functions remains banned.

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

from livespec_dev_tooling.config import Config, iter_py_files, load_config  # noqa: E402

__all__: list[str] = []


def _is_under_any(*, rel_path: Path, trees: tuple[Path, ...]) -> bool:
    return any(tree in rel_path.parents for tree in trees)


def _is_supervisor_main_file(*, rel_path: Path, config: Config) -> bool:
    if rel_path in config.supervisor_entry_files:
        return True
    return _is_under_any(rel_path=rel_path, trees=config.commands_trees)


def _supervisor_main_try_lines(*, tree: ast.Module) -> set[int]:
    """Return line numbers of `Try` nodes that are direct children of `main()`'s body."""
    out: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            for stmt in node.body:
                if isinstance(stmt, ast.Try):
                    out.add(stmt.lineno)
    return out


def _find_offending_try_lines(*, source: str, exempt_main_try: set[int]) -> list[int]:
    tree = ast.parse(source)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Try) and node.lineno not in exempt_main_try
    ]


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("no_except_outside_io")
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)
    if not config.io_trees:
        log.info(
            "role key absent — check no-ops",
            check_id="no_except_outside_io",
            role="io_trees",
        )
        return 0
    offenders: list[tuple[Path, int]] = []
    for tree_rel in config.source_trees:
        for py_file in iter_py_files(root=cwd / tree_rel):
            rel = py_file.relative_to(cwd)
            if _is_under_any(rel_path=rel, trees=config.io_trees):
                continue
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
            exempt = (
                _supervisor_main_try_lines(tree=tree)
                if _is_supervisor_main_file(rel_path=rel, config=config)
                else set[int]()
            )
            for lineno in _find_offending_try_lines(source=source, exempt_main_try=exempt):
                offenders.append((rel, lineno))
    if offenders:
        for path, lineno in offenders:
            log.error(
                "`try/except` outside io/ + supervisor bug-catcher is banned",
                file=str(path),
                line=lineno,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
