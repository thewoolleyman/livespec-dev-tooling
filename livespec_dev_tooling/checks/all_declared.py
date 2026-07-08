"""all_declared — every livespec module declares `__all__` and lists only defined names.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-all-declared` row), every module
under `.claude-plugin/scripts/livespec/**` MUST declare a
module-top `__all__: list[str]` (typed annotation, list
literal of string constants). Every name in `__all__` must
also be defined within the module — as a top-level `def`,
`class`, plain assignment, annotated assignment, or
`from <pkg> import <name>` statement.

The check walks the git-derived first-party `.py` universe
(`config.resolve_check_universe`), parses each via `ast`, and
inspects every module-top `AnnAssign` whose target is
`__all__`. Two failure modes:

- Missing `__all__` declaration (no module-top `__all__:
  list[str] = [...]` at all).
- Names in `__all__` that aren't defined as module-top
  symbols.

Phase-0 rollout severity (fleet-check-coverage): the file
universe is the git-derived first-party `.py` set
(`config.iter_first_party_py_files`) rather than a
`config.source_trees` walk. `config.source_trees` is retained
ONLY as a delta-WARN severity classifier: either failure mode
in a file UNDER a `source_trees` tree keeps today's hard gate
(an `error`-level diagnostic contributing to exit 1); the same
failure in a file newly pulled into the git-derived universe
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
from typing import NamedTuple

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    is_under_any_tree,
    load_config,
    resolve_check_universe,
    resolve_repo_root,
)

__all__: list[str] = []


def _names_from_def(
    *,
    node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef,
) -> set[str]:
    return {node.name}


def _names_from_assign(*, node: ast.Assign) -> set[str]:
    return {target.id for target in node.targets if isinstance(target, ast.Name)}


def _names_from_annassign(*, node: ast.AnnAssign) -> set[str]:
    if isinstance(node.target, ast.Name):
        return {node.target.id}
    return set()


def _names_from_import_from(*, node: ast.ImportFrom) -> set[str]:
    return {alias.asname or alias.name for alias in node.names}


def _names_from_import(*, node: ast.Import) -> set[str]:
    return {alias.asname or alias.name.split(".", maxsplit=1)[0] for alias in node.names}


def _module_top_defined_names(*, tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            out |= _names_from_def(node=node)
        elif isinstance(node, ast.Assign):
            out |= _names_from_assign(node=node)
        elif isinstance(node, ast.AnnAssign):
            out |= _names_from_annassign(node=node)
        elif isinstance(node, ast.ImportFrom):
            out |= _names_from_import_from(node=node)
        elif isinstance(node, ast.Import):
            out |= _names_from_import(node=node)
    return out


def _all_value_names(*, tree: ast.Module) -> list[str] | None:
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
            and isinstance(node.value, ast.List)
        ):
            return [
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            ]
    return None


class _Findings(NamedTuple):
    """The delta-WARN-classified `__all__` findings from one universe scan.

    Each list is repo-root-relative; the `legacy_*` lists carry today's
    hard gate (emitted at `error`, contribute to exit 1), the `newly_*`
    lists are Phase-0 newly-covered files (emitted at `warning`).
    """

    legacy_missing: list[Path]
    newly_missing: list[Path]
    legacy_undefined: list[tuple[Path, str]]
    newly_undefined: list[tuple[Path, str]]


def _scan_universe(
    *, universe: tuple[Path, ...], root: Path, source_trees: tuple[Path, ...]
) -> _Findings:
    """Classify every file's `__all__` findings into legacy vs newly-covered."""
    findings = _Findings(
        legacy_missing=[], newly_missing=[], legacy_undefined=[], newly_undefined=[]
    )
    for rel in universe:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"))
        is_legacy = is_under_any_tree(rel=rel, trees=source_trees)
        names = _all_value_names(tree=tree)
        if names is None:
            (findings.legacy_missing if is_legacy else findings.newly_missing).append(rel)
            continue
        defined = _module_top_defined_names(tree=tree)
        for name in names:
            if name in defined:
                continue
            bucket = findings.legacy_undefined if is_legacy else findings.newly_undefined
            bucket.append((rel, name))
    return findings


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("all_declared")
    root = resolve_repo_root()
    universe = resolve_check_universe(repo_root=root)
    if not universe:
        log.info("no first-party Python to check")
        return 0
    config = load_config(repo_root=root)
    findings = _scan_universe(universe=universe, root=root, source_trees=config.source_trees)
    for path in findings.legacy_missing:
        log.error("module missing `__all__: list[str]` declaration", file=str(path))
    for path, name in findings.legacy_undefined:
        log.error(
            "name listed in `__all__` not defined in module",
            file=str(path),
            name=name,
        )
    for path in findings.newly_missing:
        log.warning(
            "module missing `__all__: list[str]` declaration — newly git-derived "
            "coverage; Phase-0 WARN (hard-fails once this repo is flipped to the "
            "hard gate in Phase 2)",
            file=str(path),
            phase="0-warn",
            newly_covered=True,
        )
    for path, name in findings.newly_undefined:
        log.warning(
            "name listed in `__all__` not defined in module — newly git-derived "
            "coverage; Phase-0 WARN (hard-fails once this repo is flipped to the "
            "hard gate in Phase 2)",
            file=str(path),
            name=name,
            phase="0-warn",
            newly_covered=True,
        )
    return 1 if (findings.legacy_missing or findings.legacy_undefined) else 0


if __name__ == "__main__":
    raise SystemExit(main())
