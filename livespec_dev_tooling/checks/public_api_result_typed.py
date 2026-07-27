"""public_api_result_typed — pure-layer public APIs return Result/IOResult or carry decorator.

Per `python-skill-script-style-requirements.md` §"Canonical
target list" (the `check-public-api-result-typed` row),
every public function (per `__all__` declaration) returns
`Result` or `IOResult` per annotation OR carries a railway-
lifting decorator (`@impure_safe(...)` lifts to `IOResult`,
`@safe(...)` lifts to `Result`).

Cycle 169 implements minimum-viable: scope is
`livespec/parse/` and `livespec/validate/` (the pure layers).
For each `.py`, parse via `ast`, extract `__all__`, then
inspect each top-level FunctionDef whose name is in
`__all__`. A function passes if EITHER:

- Its return annotation's terminal name is `Result` or
  `IOResult` (also matching `Result[...]` / `IOResult[...]`
  / `livespec.types.Result` etc.).
- It carries a decorator whose terminal name is `safe` or
  `impure_safe` (call form or bare).

Documented exemptions (a-f from the canonical row) — the
supervisor `main()`, `build_parser`, `make_validator`,
`get_logger`, `compile_schema`, `rop_pipeline` — are NOT
yet wired in; subsequent cycles widen as concrete files
trigger them. Package-private modules (filename matching
`_*.py`) are skipped.

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

from livespec_dev_tooling.checks._role_key_gate import role_key_paths_exit_code  # noqa: E402
from livespec_dev_tooling.config import iter_py_files, load_config  # noqa: E402

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


def _all_value_names(*, tree: ast.Module) -> list[str]:
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
    return []


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

    Deliberately absent: `make_validator`, `get_logger`, `compile_schema`,
    `rop_pipeline`. This module's docstring cites them to an
    `archive/brainstorming/` document, which the repo's own convention
    makes reference-only; they appear nowhere in `SPECIFICATION/`.
    """
    if _returns_named(func=func, name="None"):
        return True
    under_commands = any(rel_path.is_relative_to(tree) for tree in commands_trees)
    if func.name == "main" and _returns_named(func=func, name="int"):
        return under_commands or rel_path == _DOCTOR_RUN_STATIC
    if func.name == "build_parser" and _returns_named(func=func, name="ArgumentParser"):
        return under_commands
    return False


def _find_offenders(
    *, source: str, rel_path: Path, commands_trees: tuple[Path, ...]
) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    declared = set(_all_value_names(tree=tree))
    out: list[tuple[int, str]] = []
    for node in tree.body:
        if (
            isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            and node.name in declared
            and not _is_railway_compliant(func=node)
            and not _is_exempt_supervisor(
                func=node, rel_path=rel_path, commands_trees=commands_trees
            )
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
    log = structlog.get_logger("public_api_result_typed")
    cwd = Path.cwd()
    config = load_config(repo_root=cwd)
    gate_exit = role_key_paths_exit_code(
        config=config,
        key="pure_trees",
        paths=config.pure_trees,
        repo_root=cwd,
        log=log,
        check_id="public_api_result_typed",
    )
    if gate_exit is not None:
        return gate_exit
    offenders: list[tuple[Path, int, str]] = []
    for tree_rel in config.pure_trees:
        for py_file in iter_py_files(root=cwd / tree_rel):
            if py_file.name.startswith("_"):
                continue
            source = py_file.read_text(encoding="utf-8")
            rel_path = py_file.relative_to(cwd)
            for lineno, name in _find_offenders(
                source=source, rel_path=rel_path, commands_trees=config.commands_trees
            ):
                offenders.append((rel_path, lineno, name))
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
