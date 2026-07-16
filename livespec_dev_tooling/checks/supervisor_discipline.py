"""supervisor_discipline — `sys.exit`/`raise SystemExit` confined to `bin/*.py`.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-supervisor-discipline` row),
`sys.exit(...)` calls and `raise SystemExit(...)` statements
are permitted only in `.claude-plugin/scripts/bin/*.py`
(including `_bootstrap.py`). Anywhere else under
`.claude-plugin/scripts/livespec/**`, both forms are banned —
process termination flows through the supervisor-at-the-edge
surface only; livespec modules return `Result`/`IOResult`
values that the supervisor unpacks into an exit code.

The check walks every `.py` file under `.claude-plugin/
scripts/livespec/`, parses each via `ast`, and inspects:

- Every `Call` node whose function unparses to `sys.exit`.
- Every `Raise` node whose exception is `SystemExit(...)` or
  `SystemExit` (bare).

Any match emits a structlog ERROR carrying the file path,
line number, and termination form; the script exits 1. With
no violations, exits 0.

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
    BIN_WRAPPER_TREE,
    is_under_any_tree,
    load_config,
    resolve_check_universe,
)

__all__: list[str] = []


_PLUGIN_SCRIPTS_TREE = Path(".claude-plugin") / "scripts"


def _find_termination_sites(*, source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "sys.exit":
            out.append((node.lineno, "sys.exit"))
        elif (
            isinstance(node, ast.Raise)
            and node.exc is not None
            and ast.unparse(node.exc).split("(", maxsplit=1)[0] == "SystemExit"
        ):
            out.append((node.lineno, "raise SystemExit"))
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
    log = structlog.get_logger("supervisor_discipline")
    root, universe = resolve_check_universe()
    if not universe:
        log.info("no first-party Python to check")
        return 0
    config = load_config(repo_root=root)
    legacy_offenders: list[tuple[Path, int, str]] = []
    newly_covered_offenders: list[tuple[Path, int, str]] = []
    for rel in universe:
        if rel.is_relative_to(BIN_WRAPPER_TREE) or rel in config.supervisor_entry_files:
            continue
        source = (root / rel).read_text(encoding="utf-8")
        for lineno, form in _find_termination_sites(source=source):
            if form == "raise SystemExit" and not rel.is_relative_to(_PLUGIN_SCRIPTS_TREE):
                continue
            record = (rel, lineno, form)
            if is_under_any_tree(rel=rel, trees=config.source_trees):
                legacy_offenders.append(record)
            else:
                newly_covered_offenders.append(record)
    for path, lineno, form in newly_covered_offenders:
        log.warning(
            "process termination outside `bin/` is banned — newly git-derived coverage; "
            "Phase-0 WARN (hard-fails once this repo is flipped to the hard gate in Phase 2)",
            file=str(path),
            line=lineno,
            form=form,
            phase="0-warn",
            newly_covered=True,
        )
    for path, lineno, form in legacy_offenders:
        log.error(
            "process termination outside `bin/` is banned",
            file=str(path),
            line=lineno,
            form=form,
        )
    return 1 if legacy_offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
