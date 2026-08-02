"""keyword_only_args — `*`-separator on every `def` in `livespec/**`.

Per `python-skill-script-style-requirements.md` section "Canonical
target list" (the `check-keyword-only-args` row), every `def`
in `.claude-plugin/scripts/livespec/**` MUST use `*` as the
first separator (every parameter keyword-only). Exempts:

- Python-mandated dunder signatures (`__init__`, `__repr__`,
  `__call__`, etc. — the runtime calls them with positional
  args).
- Methods that take a single positional `self` or `cls` first,
  followed by the `*` separator and keyword-only parameters
  thereafter.
- Callables bound into an EXTERNALLY-FIXED CALLING CONVENTION —
  a position whose caller lives outside this repository and
  passes positionally, so a keyword-only signature would stop
  the callable being a substitute for the thing it stands in
  for. Three forms, every one DERIVED from the consumer's own
  code rather than declared in config:
    * `sorted(..., key=fn)` / `list.sort(key=fn)`;
    * `monkeypatch.setattr(<stdlib-owned name>, ..., fn)`, and
      the methods of a stand-in class a substituted factory
      constructs;
    * `parser.add_argument(..., type=fn)`.
  The exemption is deliberately NOT "is monkeypatched": a
  double of a FIRST-PARTY keyword-only function keeps failing,
  because there the positional signature is a real defect.
  Scope is one module — evidence and definition must share a
  file — so a carve-out cannot leak across the tree, and the
  match is by function NAME within that file.

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
_STDLIB_MODULE_NAMES = frozenset(sys.stdlib_module_names)
# `monkeypatch.setattr(target, "name", value)` — the three-positional form. The
# two-arg `setattr("mod.attr", value)` form carries no separable target to test
# for external ownership, so it is not a source of evidence here.
_SETATTR_TARGET_ATTR_VALUE_ARITY = 3


def _is_dunder(*, name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _stdlib_names_imported(*, tree: ast.AST) -> frozenset[str]:
    """Names this module binds by importing them FROM the stdlib.

    `from pathlib import Path` binds `Path`. Used to decide whether an attribute
    a test substitutes is owned outside this repo.

    Plain `import os` needs no tracking: a module imported that way is reached as
    `os.fsync`, and both the target chain and the bare attribute are already
    tested against `_STDLIB_MODULE_NAMES` directly. Only the `from`-form binds a
    stdlib-owned name under an identifier that is not itself a module name.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.split(".")[0] in _STDLIB_MODULE_NAMES
        ):
            names.update(alias.asname or alias.name for alias in node.names)
    return frozenset(names)


def _names_in_attribute_chain(*, node: ast.expr) -> list[str]:
    """Every identifier in `a.b.c`, outermost last: `["a", "b", "c"]`."""
    out: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        out.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        out.append(current.id)
    out.reverse()
    return out


def _substitution_is_externally_owned(
    *,
    target: ast.expr,
    attr: str,
    stdlib_names: frozenset[str],
) -> bool:
    """True when `setattr(target, attr, ...)` replaces a name this repo does not own.

    Two forms carry that evidence, and BOTH are needed:

    - the target names a stdlib module, directly (`os`) or as the root or last
      component of a chain (`pathlib.Path`, `_supervisor_config.subprocess`);
    - the target is a first-party module but the ATTRIBUTE is a stdlib name this
      file imports (`monkeypatch.setattr(sessions, "Path", ...)`).

    Everything else — notably a first-party attribute on a first-party module —
    is NOT exempt. That is the load-bearing half: `setattr(mod, "run_daemon", d)`
    must keep failing, because `run_daemon` is this repo's own keyword-only
    function and a positional double of it is a genuine defect.
    """
    chain = _names_in_attribute_chain(node=target)
    if chain and (chain[0] in _STDLIB_MODULE_NAMES or chain[-1] in _STDLIB_MODULE_NAMES):
        return True
    return attr in stdlib_names or attr in _STDLIB_MODULE_NAMES


def _record_substitute(
    *,
    value: ast.expr,
    functions: set[str],
    classes: set[str],
) -> None:
    """Note whatever `value` binds into an externally-fixed position.

    A bare name is the substitute itself. A lambda is a FACTORY for one: any class
    it constructs is standing in for the external name, so that class's methods
    implement the external interface too.
    """
    if isinstance(value, ast.Name):
        functions.add(value.id)
        return
    if isinstance(value, ast.Lambda):
        for node in ast.walk(value):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                classes.add(node.func.id)


def _collect_externally_fixed(*, tree: ast.AST) -> tuple[frozenset[str], frozenset[str]]:
    """Names bound into a position whose calling convention is fixed outside this repo.

    Returns `(function names, stand-in class names)`. The evidence is derived from
    the consumer's own code — nothing is declared and no list is maintained:

    - `monkeypatch.setattr(<stdlib-owned name>, ..., <substitute>)`;
    - `parser.add_argument(..., type=<callback>)`, which argparse calls with one
      positional string.

    Scope is deliberately ONE module: a name is exempt only where the evidence and
    the definition sit in the same file, so a carve-out cannot leak across the tree.
    """
    stdlib_names = _stdlib_names_imported(tree=tree)
    functions: set[str] = set()
    classes: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr == "setattr" and len(node.args) == _SETATTR_TARGET_ATTR_VALUE_ARITY:
            target, attr_node, value = node.args
            if (
                isinstance(attr_node, ast.Constant)
                and isinstance(attr_node.value, str)
                and _substitution_is_externally_owned(
                    target=target, attr=attr_node.value, stdlib_names=stdlib_names
                )
            ):
                _record_substitute(value=value, functions=functions, classes=classes)
        elif node.func.attr == "add_argument":
            for kw in node.keywords:
                if kw.arg == "type":
                    _record_substitute(value=kw.value, functions=functions, classes=classes)
    return frozenset(functions), frozenset(classes)


def _methods_of(*, tree: ast.AST, class_names: frozenset[str]) -> frozenset[str]:
    """Names of methods defined directly on any class in `class_names`."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name in class_names:
            names.update(
                child.name
                for child in node.body
                if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef)
            )
    return frozenset(names)


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
    exempt_names: frozenset[str],
) -> bool:
    if _is_dunder(name=func.name):
        return True
    if func.name in exempt_names:
        return True
    positional = func.args.args
    if len(positional) == 0:
        return True
    return bool(
        len(positional) == 1 and positional[0].arg in _IMPLICIT_FIRST_PARAMS,
    )


def _find_offenders(*, source: str) -> list[tuple[int, str]]:
    tree = ast.parse(source)
    fixed_functions, standin_classes = _collect_externally_fixed(tree=tree)
    exempt_names = (
        _collect_sort_key_names(tree=tree)
        | fixed_functions
        | _methods_of(tree=tree, class_names=standin_classes)
    )
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not _is_compliant(
            func=node, exempt_names=exempt_names
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
