"""public_api_result_typed — pure-layer public APIs return Result/IOResult or carry decorator.

Every PUBLIC function returns `Result` or `IOResult` per
annotation OR carries a railway-lifting decorator
(`@impure_safe(...)` lifts to `IOResult`, `@safe(...)` lifts
to `Result`).

WHAT COUNTS AS PUBLIC IS NO LONGER `__all__` MEMBERSHIP.
Ratified livespec v178 (`non-functional-requirements.md`
§"ROP composition") makes a top-level function public only
when it is CONSUMED ACROSS A BOUNDARY, measured FLEET-WIDE.
`checks/_public_api_consumption` computes the forms a
repo-local vantage can see; the consumer DECLARES the rest in
`cross_repo_public_api` (SPECIFICATION v036), because a
repo-local check structurally CANNOT see a sibling's import.
The declaration is TIGHTENING-ONLY — it is UNIONED with the
computed set, so an absent declaration removes nothing — and
a declared entry that no longer resolves to a real top-level
function FAILS the check rather than being carried forward.

COMPLETENESS OF THAT DECLARATION IS NOT VERIFIED HERE, and a
green run does NOT mean it is complete: whether a member's
declared surface omits a name another member consumes is the
central-vantage conformance row's obligation under v178's
split-enforcement clause.

The scan universe is still `pure_trees`-scoped; the
CONSUMPTION universe is the git-derived first-party set from
`resolve_check_universe()`, because a consumer of a pure-layer
function generally lives outside the pure layer.

For each `.py` in scope, parse via `ast` and inspect each
top-level FunctionDef the criterion calls public. A function
passes if EITHER:

- Its return annotation's terminal name is `Result` or
  `IOResult` (also matching `Result[...]` / `IOResult[...]`
  / `livespec.types.Result` etc.).
- It carries a decorator whose terminal name is `safe` or
  `impure_safe` (call form or bare).

The exemption set is the EXHAUSTIVE four-member set ratified in
livespec v177 (`non-functional-requirements.md` §"ROP
composition"), and all four ARE wired in: `main() -> int` under
`commands_trees` or at `doctor/run_static.py`; `build_parser()
-> ArgumentParser` under `commands_trees`; any function
annotated `None`; and a supervisor entry point in a file
declared in `supervisor_entry_files`. `make_validator`,
`get_logger`, `compile_schema` and `rop_pipeline` are NOT
members — they are cited only to an `archive/brainstorming/`
document this repo treats as reference-only, and appear nowhere
in any `SPECIFICATION/`.

Package-private modules (filename matching `_*.py`) are
skipped, and a `_`-prefixed FUNCTION name is not public
however it is reached — v178 clause 0 (see `_is_public_name`).

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
from typing import TYPE_CHECKING

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.checks._public_api_consumption import (  # noqa: E402
    declared_public_names,
    repo_local_public_names,
    stale_declarations,
)
from livespec_dev_tooling.checks._role_key_gate import (  # noqa: E402
    ensure_declared_paths_contain_python,
    role_absence_exit_code,
)
from livespec_dev_tooling.config import (  # noqa: E402
    iter_py_files,
    load_config,
    resolve_check_universe,
    role_trees,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from livespec_dev_tooling.config import Config

__all__: list[str] = []


_RESULT_NAMES = frozenset({"Result", "IOResult"})
# The one non-`commands/` location the spec names for the `main() -> int`
# supervisor exemption.
_DOCTOR_RUN_STATIC = Path("doctor") / "run_static.py"
_RAILWAY_LIFTING_DECORATORS = frozenset({"safe", "impure_safe"})


def _decorator_terminal_name(*, decorator: ast.expr) -> str:
    if isinstance(decorator, ast.Call):
        decorator = decorator.func
    return ast.unparse(decorator).rsplit(".", maxsplit=1)[-1]


def _annotation_head_name(*, annotation: ast.expr) -> str:
    rendered = ast.unparse(annotation)
    head = rendered.split("[", maxsplit=1)[0]
    return head.rsplit(".", maxsplit=1)[-1]


def _is_railway_compliant(*, func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in func.decorator_list:
        if _decorator_terminal_name(decorator=decorator) in _RAILWAY_LIFTING_DECORATORS:
            return True
    if func.returns is None:
        return False
    return _annotation_head_name(annotation=func.returns) in _RESULT_NAMES


def _returns_named(*, func: ast.FunctionDef | ast.AsyncFunctionDef, name: str) -> bool:
    """True iff `func`'s return annotation's terminal name is `name`."""
    if func.returns is None:
        return False
    return _annotation_head_name(annotation=func.returns) == name


def _is_exempt_supervisor(
    *,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    rel_path: Path,
    commands_trees: tuple[Path, ...],
    supervisor_entry_files: tuple[Path, ...] = (),
) -> bool:
    """True iff the spec exempts `func` from the Result/IOResult return rule.

    Implements `non-functional-requirements.md` verbatim, INCLUDING its
    path scoping — "a supervisor at a deliberate side-effect boundary
    (`main() -> int` in `commands/*.py` and `doctor/run_static.py`, or
    any function returning `None`) ... OR the `build_parser() ->
    ArgumentParser` factory in `commands/**.py`".

    The scoping is load-bearing, not decoration: a flat-layout repo that
    declares no commands tree gets NO `main()` exemption, because the
    spec grants it to a LOCATION, not to a name. Exempting every `main`
    everywhere would be a reading of intent, not the stated rule.

    MEMBER 4, ratified in livespec v177: a supervisor entry point in a file
    the consumer DECLARES in `supervisor_entry_files`. It admits the SAME
    category as the `commands/` members through a per-file declaration rather
    than a directory glob, because a flat-layout consumer cannot satisfy a
    LOCATION scoping at all — its process entry points sit beside its ordinary
    modules. Four other checks (`no_except_outside_io`, `no_write_direct`,
    `supervisor_discipline`, `partition_completeness`) already act on this same
    declaration; this check was the only consumer of the supervisor concept
    that never asked the repo.

    The declaration is STRICTER than the glob it complements: `commands/*.py`
    exempts every present and future file in that directory with nobody
    deciding anything, whereas an undeclared file gets NOTHING here. And it is
    BOUNDED — it exempts the supervisor ENTRY POINTS in a declared file, never
    every function in it.

    Deliberately absent: `make_validator`, `get_logger`, `compile_schema`,
    `rop_pipeline`. This module's docstring cites them to an
    `archive/brainstorming/` document, which the repo's own convention
    makes reference-only; they appear nowhere in `SPECIFICATION/`.
    """
    if _returns_named(func=func, name="None"):
        return True
    under_commands = any(rel_path.is_relative_to(tree) for tree in commands_trees)
    declared_supervisor = rel_path in supervisor_entry_files
    if func.name == "main" and _returns_named(func=func, name="int"):
        return under_commands or declared_supervisor or rel_path == _DOCTOR_RUN_STATIC
    if func.name == "build_parser" and _returns_named(func=func, name="ArgumentParser"):
        return under_commands or declared_supervisor
    return False


def _is_public_name(*, name: str) -> bool:
    """True iff `name` survives v178 CLAUSE 0 — a leading underscore is DECISIVE.

    Clause 0 of the ratified criterion disqualifies a `_`-prefixed name
    outright, regardless of `__all__` membership or of any consumption
    below it. Consumers legitimately list private helpers in `__all__` so
    their tests may import them; `checks/check_mutation.py` is the
    clearest case — its `__all__` holds six `_`-prefixed helpers and does
    not list `main` at all.

    This is the ONE place `__all__` used to decide publicness and no
    longer does. v178 replaced membership with CONSUMED ACROSS A
    BOUNDARY; `_public_api_consumption` computes that, and clause 0
    remains as a disqualifier layered on top of it.
    """
    return not name.startswith("_")


def _find_offenders(
    *,
    source: str,
    rel_path: Path,
    commands_trees: tuple[Path, ...],
    public_names: frozenset[str],
    supervisor_entry_files: tuple[Path, ...] = (),
) -> list[tuple[int, str]]:
    """Offending top-level functions in `source`, given this file's PUBLIC names.

    `public_names` is the v178 answer for THIS file — computed by
    `_public_api_consumption` from the repo's own consumption graph and the
    consumer's `cross_repo_public_api` declaration. It replaces the
    `__all__`-membership proxy, which was false for this repo at scale: 25 of
    31 reported offenders were `__all__` members no boundary ever crossed.
    """
    tree = ast.parse(source)
    out: list[tuple[int, str]] = []
    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name in public_names
            and _is_public_name(name=node.name)
            and not _is_railway_compliant(func=node)
            and not _is_exempt_supervisor(
                func=node,
                rel_path=rel_path,
                commands_trees=commands_trees,
                supervisor_entry_files=supervisor_entry_files,
            )
        ):
            out.append((node.lineno, node.name))
    return out


def _scan(
    *,
    cwd: Path,
    pure_trees: tuple[Path, ...],
    config: Config,
    sources: Mapping[Path, str],
) -> list[tuple[Path, int, str]]:
    """Offenders across the scanned trees, given the repo's consumption universe.

    Two universes meet here and they are NOT the same set. The SCANNED universe
    is `pure_trees`; the CONSUMPTION universe is `sources`, the git-derived
    first-party set. A consumer of a pure-layer function generally lives
    outside the pure layer, so deriving consumption from the scanned trees
    alone would miss most of it — and missing consumption is the RELAXING
    direction.
    """
    public = repo_local_public_names(sources=sources) | declared_public_names(
        declared=config.cross_repo_public_api, sources=sources
    )
    offenders: list[tuple[Path, int, str]] = []
    for tree_rel in pure_trees:
        for py_file in iter_py_files(root=cwd / tree_rel):
            if py_file.name.startswith("_"):
                continue
            rel_path = py_file.relative_to(cwd)
            for lineno, name in _find_offenders(
                source=py_file.read_text(encoding="utf-8"),
                rel_path=rel_path,
                commands_trees=config.commands_trees,
                public_names=frozenset(n for p, n in public if p == rel_path),
                supervisor_entry_files=config.supervisor_entry_files,
            ):
                offenders.append((rel_path, lineno, name))
    return offenders


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("public_api_result_typed")
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)
    gate_exit = role_absence_exit_code(
        config=config,
        role=config.pure_trees,
        key="pure_trees",
        log=log,
        check_id="public_api_result_typed",
    )
    if gate_exit is not None:
        return gate_exit
    pure_trees = role_trees(role=config.pure_trees)
    if not ensure_declared_paths_contain_python(
        repo_root=cwd,
        key="pure_trees",
        paths=pure_trees,
        log=log,
        check_id="public_api_result_typed",
    ):
        return 1
    root, universe = resolve_check_universe()
    sources = {rel: (root / rel).read_text(encoding="utf-8") for rel in universe}
    stale = stale_declarations(declared=config.cross_repo_public_api, sources=sources)
    if stale:
        for entry in stale:
            log.error(
                "declared cross_repo_public_api entry no longer resolves to a public function",
                file=str(entry.file),
                function=entry.function,
                reason=entry.reason,
            )
        return 1
    offenders = _scan(cwd=cwd, pure_trees=pure_trees, config=config, sources=sources)
    if offenders:
        for path, lineno, name in offenders:
            log.error(
                "public function not Result-typed and not railway-lifting-decorated",
                file=str(path),
                line=lineno,
                function=name,
            )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
