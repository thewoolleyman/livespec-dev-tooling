"""keyword_only_args — `*`-separator on every `def` in `livespec/**`.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-keyword-only-args` row), every `def`
in `.claude-plugin/scripts/livespec/**` MUST use `*` as the
first separator (every parameter keyword-only). Exempts:

- Python-mandated dunder signatures (`__init__`, `__repr__`,
  `__call__`, etc. — the runtime calls them with positional
  args).
- Methods that take a single positional `self` or `cls` first,
  followed by the `*` separator and keyword-only parameters
  thereafter.

The check walks the git-derived first-party `.py` universe
(`config.resolve_check_universe`), parses each via `ast`, and
inspects every `FunctionDef` and `AsyncFunctionDef`'s `args`
block:

- If the function name is a dunder (matches `__*__`), exempt.
- If `args.args` is empty, the function is zero-positional
  and trivially compliant (no `*` needed).
- If `args.args` has exactly one entry whose name is `self`
  or `cls`, it's a regular method — the rest of the
  parameters MUST be in `args.kwonlyargs` and `args.args`
  beyond `self`/`cls` must be empty.
- Otherwise, `args.args` must be empty (every parameter is in
  `args.kwonlyargs`).

Cycle 154 implements the def-level check. Subsequent cycles
widen to `@dataclass(frozen=True, kw_only=True, slots=True)`
verification when fixtures demand it.

Phase-0 rollout severity (fleet-check-coverage): the file
universe is the git-derived first-party `.py` set
(`config.iter_first_party_py_files`) rather than a
`config.source_trees` walk. `config.source_trees` is retained
ONLY as a delta-WARN severity classifier: a `def` missing the
`*` separator in a file UNDER a `source_trees` tree keeps
today's hard gate (an `error`-level diagnostic contributing to
exit 1); the same violation in a file newly pulled into the
git-derived universe emits at WARN (`warning`-level,
`phase="0-warn"`, no exit-1 contribution) until Phase 2 flips
its repo to the hard gate. A genuinely codeless repo (zero
first-party `.py`) passes with an info-level "nothing to
check".

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


_IMPLICIT_FIRST_PARAMS = frozenset({"self", "cls"})
_SORT_FUNC_NAMES = frozenset({"sort", "sorted"})


def _is_dunder(*, name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _collect_sort_key_names(*, tree: ast.AST) -> frozenset[str]:
    """Collect names of callables passed as key= to sort/sorted call sites."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        is_sort_call = (isinstance(func, ast.Name) and func.id in _SORT_FUNC_NAMES) or (
            isinstance(func, ast.Attribute) and func.attr in _SORT_FUNC_NAMES
        )
        if not is_sort_call:
            continue
        for kw in node.keywords:
            if kw.arg == "key":
                val = kw.value
                if isinstance(val, ast.Name):
                    names.add(val.id)
                elif isinstance(val, ast.Attribute):
                    names.add(val.attr)
    return frozenset(names)


def _is_compliant(
    *,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    sort_key_names: frozenset[str],
) -> bool:
    if _is_dunder(name=func.name):
        return True
    if func.name in sort_key_names:
        return True
    positional = func.args.args
    if len(positional) == 0:
        return True
    return bool(
        len(positional) == 1 and positional[0].arg in _IMPLICIT_FIRST_PARAMS,
    )


def _find_offenders(*, source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    sort_key_names = _collect_sort_key_names(tree=tree)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not _is_compliant(
            func=node, sort_key_names=sort_key_names
        ):
            out.append((node.lineno, node.name))
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
    log = structlog.get_logger("keyword_only_args")
    root, universe = resolve_check_universe()
    if not universe:
        log.info("no first-party Python to check")
        return 0
    config = load_config(repo_root=root)
    legacy_offenders: list[tuple[Path, int, str]] = []
    newly_offenders: list[tuple[Path, int, str]] = []
    for rel in universe:
        source = (root / rel).read_text(encoding="utf-8")
        for lineno, fn_name in _find_offenders(source=source):
            record = (rel, lineno, fn_name)
            if is_under_any_tree(rel=rel, trees=config.source_trees):
                legacy_offenders.append(record)
            else:
                newly_offenders.append(record)
    for path, lineno, fn_name in legacy_offenders:
        log.error(
            "function missing `*` keyword-only separator",
            file=str(path),
            line=lineno,
            function=fn_name,
        )
    for path, lineno, fn_name in newly_offenders:
        log.warning(
            "function missing `*` keyword-only separator — newly git-derived "
            "coverage; Phase-0 WARN (hard-fails once this repo is flipped to "
            "the hard gate in Phase 2)",
            file=str(path),
            line=lineno,
            function=fn_name,
            phase="0-warn",
            newly_covered=True,
        )
    return 1 if legacy_offenders else 0


if __name__ == "__main__":
    raise SystemExit(main())
