"""no_except_outside_io — broad catches confined to marked supervisor boundaries.

Per `livespec/SPECIFICATION/non-functional-requirements.md`
§"Supervisor discipline": narrow at the seam; broad only at
the boundary; at most one boundary per process. A NARROW
handler names specific exception types and is permitted
anywhere — it is how a seam handles an expected failure. A
BROAD handler (`except Exception`, `except BaseException`, or
a bare `except:`) is permitted ONLY as the sole boundary
catch: a direct child of `main()` in a declared supervisor
entry file, carrying one of the closed set of sanctioned
`# noqa: BLE001 — …` markers.

The enforcement labor is split: ruff `BLE001` polices catch
BREADTH at the construct level, and this check polices catch
POSITION — which trees a broad catch may live in, and which
`main()` direct-children are exempt — plus the per-artifact
boundary CARDINALITY: a second exempted boundary catch in one
entry artifact is an offense, since `sole` is load-bearing in
each boundary wording. Foreign-code catches carry their own
accounting unit (per extension invocation surface), so they
never consume the artifact's single boundary slot.

TWO accounting units, not three: the loop-iteration flavor —
accounted per supervision loop — was RETIRED by the maintainer
ruling of 2026-07-26, which holds that a daemon does not get a
per-iteration broad catch ("let it crash, systemd restarts";
exactly one broad catch per program, in `main()`).

Neither mechanism covers the whole rule on its own: the
pairing of each catch with its correct marker flavor, and
per-flavor contract discharge, both remain review-enforced.
The loop-iteration POSITION rule is no longer among the gaps —
it ceased to exist with the flavor rather than being
mechanized.

The universe is the GIT-DERIVED first-party set
(`resolve_check_universe`), so a new module is covered the
moment it is tracked. It is deliberately NOT the declared
`source_trees` allowlist: that made `source_trees = []` mean
"scan nothing" while the declaration read as conformance — a
scope dodge that disarmed this check over a whole package with
one empty array. `io_trees` remains DECLARED because it records
an architectural ROLE the git index cannot supply.

Files under `io_trees` are wholesale exempt; with `io_trees`
unset nothing is exempt and every source file is inspected.
The marker lives on the `except …:` clause itself, which
`ast` discards along with every other comment, so each module
is tokenized and only `COMMENT` tokens positioned on the
clause's own lines — up to and including its closing colon —
can legalize a broad catch. A marker in the handler body, or
in a string literal, is inert.

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
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._no_except_outside_io_markers import (  # noqa: E402
    BOUNDARY_FLAVOR,
    cardinality_offenses,
    comment_lines,
    sanctioned_marker_flavor,
    statement_colons,
)
from livespec_dev_tooling.checks._no_except_outside_io_ruff import (  # noqa: E402
    find_ruff_backstop_gaps,
)
from livespec_dev_tooling.config import (  # noqa: E402
    Config,
    load_config,
    resolve_check_universe,
)

__all__: list[str] = []


_BROAD_NAMES = frozenset({"Exception", "BaseException"})
_TRY_STAR_NODE_NAME = "TryStar"

_UNMARKED_REASON = (
    "broad catch at a supervisor boundary without a sanctioned "
    "`# noqa: BLE001 — …` marker is banned"
)
_MISPLACED_REASON = "broad catch outside io/ and the sole supervisor boundary is banned"


def _is_under_any(*, rel_path: Path, trees: tuple[Path, ...]) -> bool:
    return any(tree in rel_path.parents for tree in trees)


def _is_supervisor_main_file(*, rel_path: Path, config: Config) -> bool:
    return rel_path in config.supervisor_entry_files or _is_under_any(
        rel_path=rel_path, trees=config.commands_trees
    )


def _is_try_node(*, node: ast.AST) -> bool:
    return isinstance(node, ast.Try) or node.__class__.__name__ == _TRY_STAR_NODE_NAME


def _supervisor_main_boundary_lines(*, tree: ast.Module) -> set[int]:
    """Return line numbers of catch nodes that are direct children of `main()`'s body."""
    out: set[int] = set()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            for stmt in node.body:
                if _is_try_node(node=stmt) or isinstance(stmt, ast.With | ast.AsyncWith):
                    out.add(stmt.lineno)
    return out


def _local_catch_names(
    *, tree: ast.Module
) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """Return broad names plus contextlib module and suppress-function aliases.

    Any catch operand shape beyond a dotted `Name` or a `Tuple` thereof stays
    out of reach as accepted ruff parity. `contextlib.suppress(Exception)` is
    not in that parity bucket: it is idiomatic, unobfuscated, and invisible to
    ruff, so this check names it explicitly.
    """
    broad_names: set[str] = set(_BROAD_NAMES)
    contextlib_names: set[str] = {"contextlib"}
    suppress_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            contextlib_names.update(
                alias.asname or alias.name for alias in node.names if alias.name == "contextlib"
            )
        elif isinstance(node, ast.ImportFrom):
            broad_names.update(
                alias.asname or alias.name for alias in node.names if alias.name in _BROAD_NAMES
            )
            if node.module == "contextlib":
                suppress_names.update(
                    alias.asname or alias.name for alias in node.names if alias.name == "suppress"
                )
    return frozenset(broad_names), frozenset(contextlib_names), frozenset(suppress_names)


def _is_broad_operand(*, caught: ast.expr | None, broad_names: frozenset[str]) -> bool:
    """True for a broad builtin, a tuple containing one, or a bare `except:` operand.

    The operand is compared on its final dotted component, so the
    fully-qualified `builtins.Exception` classifies as broad. Matching the
    whole rendering instead would let the dotted spelling read as a narrow
    seam catch here while ruff still treats it as broad — the marker
    wording would then go uninspected AND the `BLE001` suppression would
    count as used, so both halves of the enforcement split would fall
    together.
    """
    if caught is None:
        return True
    parts = list(caught.elts) if isinstance(caught, ast.Tuple) else [caught]
    return any(ast.unparse(part).rsplit(".", maxsplit=1)[-1] in broad_names for part in parts)


def _is_broad(*, handler: ast.ExceptHandler, broad_names: frozenset[str]) -> bool:
    return _is_broad_operand(caught=handler.type, broad_names=broad_names)


def _is_broad_suppress_call(
    *,
    call: ast.Call,
    broad_names: frozenset[str],
    contextlib_names: frozenset[str],
    suppress_names: frozenset[str],
) -> bool:
    func = call.func
    recognized = (isinstance(func, ast.Name) and func.id in suppress_names) or (
        isinstance(func, ast.Attribute)
        and func.attr == "suppress"
        and ast.unparse(func.value) in contextlib_names
    )
    return recognized and _is_broad_operand(
        caught=ast.Tuple(elts=list(call.args), ctx=ast.Load()), broad_names=broad_names
    )


def _find_offending_suppress_lines(
    *,
    tree: ast.Module,
    comments: dict[int, tuple[str, ...]],
    colons: tuple[tuple[int, int], ...],
    catch_names: tuple[frozenset[str], frozenset[str], frozenset[str]],
    boundary_lines: set[int],
) -> tuple[list[tuple[int, str]], list[int]]:
    """Return suppress-form offenses plus the lines that consumed the boundary slot."""
    broad_names, contextlib_names, suppress_names = catch_names
    out: list[tuple[int, str]] = []
    exempted_boundary_lines: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.With | ast.AsyncWith):
            continue
        at_boundary = node.lineno in boundary_lines
        for item in node.items:
            if not isinstance(item.context_expr, ast.Call) or not _is_broad_suppress_call(
                call=item.context_expr,
                broad_names=broad_names,
                contextlib_names=contextlib_names,
                suppress_names=suppress_names,
            ):
                continue
            flavor = (
                sanctioned_marker_flavor(node=node, comments=comments, colons=colons)
                if at_boundary
                else None
            )
            if flavor is not None:
                if flavor == BOUNDARY_FLAVOR:
                    exempted_boundary_lines.append(node.lineno)
                continue
            out.append((node.lineno, _UNMARKED_REASON if at_boundary else _MISPLACED_REASON))
    return out, exempted_boundary_lines


def _find_offending_handlers(*, source: str, position_exempt: bool) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    comments = comment_lines(source=source)
    colons = statement_colons(source=source)
    broad_names, contextlib_names, suppress_names = _local_catch_names(tree=tree)
    boundary_lines = _supervisor_main_boundary_lines(tree=tree) if position_exempt else set[int]()
    out: list[tuple[int, str]] = []
    exempted_boundary_lines: list[int] = []
    for node in ast.walk(tree):
        if not _is_try_node(node=node):
            continue
        try_node = cast(ast.Try, node)
        at_boundary = try_node.lineno in boundary_lines
        for handler in try_node.handlers:
            if not _is_broad(handler=handler, broad_names=broad_names):
                continue
            flavor = (
                sanctioned_marker_flavor(node=handler, comments=comments, colons=colons)
                if at_boundary
                else None
            )
            if flavor is not None:
                if flavor == BOUNDARY_FLAVOR:
                    exempted_boundary_lines.append(handler.lineno)
                continue
            out.append((handler.lineno, _UNMARKED_REASON if at_boundary else _MISPLACED_REASON))
    suppress_offenses, suppress_boundary_lines = _find_offending_suppress_lines(
        tree=tree,
        comments=comments,
        colons=colons,
        catch_names=(broad_names, contextlib_names, suppress_names),
        boundary_lines=boundary_lines,
    )
    out.extend(suppress_offenses)
    exempted_boundary_lines.extend(suppress_boundary_lines)
    out.extend(cardinality_offenses(boundary_lines=exempted_boundary_lines))
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
    log = structlog.get_logger("no_except_outside_io")
    root, universe = resolve_check_universe()
    # A genuinely codeless repo is a PASS, not a configuration error. It is the
    # one exemption the railway clause grants, and `resolve_check_universe`
    # raises typed git errors rather than returning a spuriously-empty walk, so
    # an empty universe here means exactly what it says.
    if not universe:
        log.info("no first-party Python to check", check_id="no_except_outside_io")
        return 0
    config = load_config(repo_root=root)
    offenders: list[tuple[Path, int, str]] = []
    inspected_files: list[Path] = []
    for rel in universe:
        if _is_under_any(rel_path=rel, trees=config.io_trees):
            continue
        inspected_files.append(rel)
        source = (root / rel).read_text(encoding="utf-8")
        exempt = _is_supervisor_main_file(rel_path=rel, config=config)
        for lineno, reason in _find_offending_handlers(source=source, position_exempt=exempt):
            offenders.append((rel, lineno, reason))
    # An inspected count of zero otherwise reads exactly like a clean pass, so
    # it is reported on every run rather than inferred from silence.
    log.info(
        "inspection complete",
        check_id="no_except_outside_io",
        files_inspected=len(inspected_files),
        offenses=len(offenders),
    )
    backstop_gaps = find_ruff_backstop_gaps(
        repo_root=root,
        scan_roots=(Path(),),
        inspected_files=tuple(inspected_files),
    )
    # BOTH failure kinds are reported in the SAME run. An earlier form returned
    # on the first backstop gap, before this offender loop — so a repo carrying
    # a gap had its real broad catches computed, counted in the info line above,
    # and then never logged. That is worse than a missing check: the non-zero
    # exit makes it look like the check worked while the offenses it found stay
    # invisible to the error stream a reviewer and a CI log actually read. A
    # fleet census concluded "zero genuine broad catches" on exactly that basis;
    # there were seven, every one behind a gap.
    for path, gap_reason in backstop_gaps:
        log.error(gap_reason, file=str(path))
    for path, lineno, reason in offenders:
        log.error(reason, file=str(path), line=lineno)
    return 1 if (backstop_gaps or offenders) else 0


if __name__ == "__main__":
    raise SystemExit(main())
