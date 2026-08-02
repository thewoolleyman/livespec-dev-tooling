"""no_write_direct — bans `sys.{stdout,stderr}[.buffer].write` outside exemption surface.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-no-write-direct` row),
`sys.stdout.write(...)` and `sys.stderr.write(...)` calls — plus
their `sys.stdout.buffer.write(...)` / `sys.stderr.buffer.write(...)`
byte-stream forms, which reach the same streams and were used to
evade this exact-AST check — are
banned in `.claude-plugin/scripts/livespec/**`,
`.claude-plugin/scripts/bin/**`, and
`<repo-root>/dev-tooling/**`. Pairs with ruff `T20` (which
bans `print` / `pprint`).

The check walks every `.py` file under the three covered
subtrees, parses each via `ast`, and inspects every `Call`
node whose function unparses to `sys.stdout.write` or
`sys.stderr.write`. Any match emits a structlog ERROR
carrying the file path and line number; the script exits 1.
With no violations, exits 0.

Cycle 150 implements the core ban plus the three documented
exemption surfaces, all file-scope (each supervisor file owns
the private helpers that its `main()` dispatches to, e.g.,
`_emit_findings_json` in `run_static.py`):

- `bin/_bootstrap.py` (pre-import version-check stderr — no
  structlog available pre-bootstrap).
- `livespec/doctor/run_static.py` (findings JSON stdout
  contract — `main()` dispatches to a private
  `_emit_findings_json` helper).
- Every `.py` under `livespec/commands/**` (each supervisor's
  `main()` + the private helpers it dispatches to —
  HelpRequested rendering, resolve_template path emission,
  etc.).

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
    Config,
    is_under_any_tree,
    load_config,
    resolve_check_universe,
)

__all__: list[str] = []


# The `.buffer.write` forms are banned identically to the plain writes:
# `sys.stdout.buffer.write(...)` / `sys.stderr.buffer.write(...)` reach the
# same underlying streams and were used to evade this check's exact-AST
# match, so they carry the same ban.
_BANNED_CALL_TARGETS = frozenset(
    {
        "sys.stdout.write",
        "sys.stderr.write",
        "sys.stdout.buffer.write",
        "sys.stderr.buffer.write",
    }
)


def _is_file_scope_exempt(*, rel_path: Path, config: Config) -> bool:
    # File-scope exemption: each supervisor surface owns documented
    # stdout/stderr contracts. Per the canonical target list row's prose:
    # `bin/_bootstrap.py` + `livespec/doctor/run_static.py`
    # (config.supervisor_entry_files); every `.py` under
    # `livespec/commands/**` (config.commands_trees).
    if rel_path in config.supervisor_entry_files:
        return True
    return any(tree in rel_path.parents for tree in config.commands_trees)


def _find_banned_calls(*, source: str) -> list[int]:
    tree = ast.parse(source)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) in _BANNED_CALL_TARGETS
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
    log = structlog.get_logger("no_write_direct")
    root, universe = resolve_check_universe()
    config = load_config(repo_root=root)
    legacy_offenders: list[tuple[Path, int]] = []
    newly_covered_offenders: list[tuple[Path, int]] = []
    for rel in universe:
        if _is_file_scope_exempt(rel_path=rel, config=config):
            continue
        source = (root / rel).read_text(encoding="utf-8")
        for lineno in _find_banned_calls(source=source):
            if is_under_any_tree(rel=rel, trees=config.covered_trees):
                legacy_offenders.append((rel, lineno))
            else:
                newly_covered_offenders.append((rel, lineno))
    for path, lineno in newly_covered_offenders:
        log.warning(
            "`sys.{stdout,stderr}[.buffer].write` banned outside exemption surface — "
            "newly git-derived coverage; Phase-0 WARN "
            "(hard-fails once this repo is flipped to the hard gate in Phase 2)",
            file=str(path),
            line=lineno,
            phase="0-warn",
            newly_covered=True,
        )
    for path, lineno in legacy_offenders:
        log.error(
            "`sys.{stdout,stderr}[.buffer].write` banned outside exemption surface",
            file=str(path),
            line=lineno,
        )
    if legacy_offenders:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
