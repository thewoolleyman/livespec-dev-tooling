"""_public_api_consumption — which top-level functions are CONSUMED ACROSS A BOUNDARY.

`livespec` v178 (`non-functional-requirements.md` §"ROP composition") replaced
`__all__` membership as the definition of public API for the Result-return
rule. A top-level function is PUBLIC API when, and only when, it is CONSUMED
ACROSS A BOUNDARY, measured FLEET-WIDE, in four forms: (1) product import, (2)
cross-repo test import, (3) process entry point, (4) declared distributed
surface. Clause 0 keeps the `_`-prefix disqualifier.

THIS MODULE OWNS ONLY THE FORMS A REPO-LOCAL VANTAGE CAN COMPUTE — the
declaring-repo half of form 1, and form 3. Forms 2 and 4, and form 1's sibling
half, are structurally invisible from inside one checkout; the consumer
DECLARES them in the `cross_repo_public_api` role key (SPECIFICATION v036), and
a central-vantage conformance row checks that declaration against the fleet's
actual consumption graph. Neither vantage suffices alone.

TWO PROPERTIES ARE LOAD-BEARING AND ARE PINNED BY TEST:

- **AN IMPORT IS RESOLVED TO ITS DEFINING MODULE, never matched by bare name.**
  A bare-name oracle was measured wrong on this very repo: it scored
  `fleet/merged_branch_sweep.py`'s `fetch_manifest` PUBLIC on two consumers
  that both import a DIFFERENT `fetch_manifest` (`fleet/fleet_conformance.py`),
  and it produced 51 false `parse_argv` hits against a sibling repo's homonym.
  The offender had ZERO consumers. Name-matching errs toward calling private
  helpers public, which manufactures work; worse, it hides which function a
  consumer actually depends on.
- **FORM 3 IS `__all__`-SCOPED; FORMS 1, 2 AND 4 ARE NOT.** v178's tightening
  clause states that a function consumed by form 1, 2 or 4 is public whether or
  not it appears in `__all__`, and deliberately omits form 3. Reading form 3 as
  `__all__`-independent too would make every undeclared `main()` in the fleet
  public API at once — not what the ratified criterion was measured to do
  (34 → 8 in this repo). Form 3's job is narrower: to stop "nobody imports it,
  therefore it is not public" from becoming an escape for a process entry point
  a repo HAS declared.

The analysis is STATIC and cannot see `getattr` / `importlib` / string
dispatch — a blind spot v178 states rather than leaves to be discovered.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__: list[str] = ["repo_local_public_names"]


_INIT_FILENAME = "__init__.py"
_MAIN_GUARD_NAMES = frozenset({"__name__", "__main__"})


def _module_name(*, rel: Path) -> str:
    """Dotted module name for a repo-root-relative first-party `.py` path."""
    parts = list(rel.parts)
    if parts[-1] == _INIT_FILENAME:
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def _declared_all(*, tree: ast.Module) -> frozenset[str]:
    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "__all__"
            and isinstance(node.value, ast.List)
        ):
            return frozenset(
                elt.value
                for elt in node.value.elts
                if isinstance(elt, ast.Constant) and isinstance(elt.value, str)
            )
    return frozenset()


def _top_level_functions(*, tree: ast.Module) -> frozenset[str]:
    return frozenset(
        node.name for node in tree.body if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    )


def _relative_base(*, current: str, level: int) -> str:
    """Package `current` is `level` levels above — the anchor of a relative import."""
    head = current.rsplit(".", maxsplit=level)
    return head[0] if len(head) > level else ""


def _import_from_target(*, node: ast.ImportFrom, current: str) -> str:
    if node.level == 0:
        return node.module or ""
    base = _relative_base(current=current, level=node.level)
    if not base:
        return node.module or ""
    return f"{base}.{node.module}" if node.module else base


def _module_aliases(*, tree: ast.Module, current: str, modules: frozenset[str]) -> dict[str, str]:
    """Local names bound to a first-party MODULE, for later attribute resolution."""
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom):
            target = _import_from_target(node=node, current=current)
            for alias in node.names:
                submodule = f"{target}.{alias.name}"
                if submodule in modules:
                    aliases[alias.asname or alias.name] = submodule
    return aliases


def _name_imports(
    *, tree: ast.Module, current: str, modules: frozenset[str]
) -> set[tuple[str, str]]:
    """`(defining module, name)` pairs this module imports by NAME."""
    out: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        target = _import_from_target(node=node, current=current)
        if target not in modules or target == current:
            continue
        for alias in node.names:
            if f"{target}.{alias.name}" in modules or alias.name == "*":
                continue
            out.add((target, alias.name))
    return out


def _attribute_reaches(
    *, tree: ast.Module, current: str, aliases: Mapping[str, str], modules: frozenset[str]
) -> set[tuple[str, str]]:
    """`(defining module, name)` pairs reached as `<module alias>.<name>`."""
    out: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        rendered = ast.unparse(node.value)
        target = aliases.get(rendered, rendered)
        if target in modules and target != current:
            out.add((target, node.attr))
    return out


def _entry_point_names(*, tree: ast.Module) -> frozenset[str]:
    """Names referenced from the module's `if __name__ == "__main__"` block."""
    out: set[str] = set()
    for node in tree.body:
        if not isinstance(node, ast.If):
            continue
        test_names = {n.id for n in ast.walk(node.test) if isinstance(n, ast.Name)} | {
            c.value for c in ast.walk(node.test) if isinstance(c, ast.Constant)
        }
        if not test_names >= _MAIN_GUARD_NAMES:
            continue
        out |= {n.id for n in ast.walk(node) if isinstance(n, ast.Name)}
    return frozenset(out)


def repo_local_public_names(*, sources: Mapping[Path, str]) -> frozenset[tuple[Path, str]]:
    """`(defining path, function name)` pairs public by a repo-LOCAL v178 form.

    `sources` is the repo's first-party NON-TEST universe — the same universe
    `resolve_check_universe()` yields — because v178 clause 1 counts an import
    by non-test first-party code, and a same-repo test importer is scaffolding
    rather than a consumer whose contract the railway protects.
    """
    trees = {rel: ast.parse(source) for rel, source in sources.items()}
    rel_by_module = {_module_name(rel=rel): rel for rel in trees}
    modules = frozenset(rel_by_module)
    functions = {rel: _top_level_functions(tree=tree) for rel, tree in trees.items()}

    public: set[tuple[Path, str]] = set()
    for rel, tree in trees.items():
        current = _module_name(rel=rel)
        aliases = _module_aliases(tree=tree, current=current, modules=modules)
        reached = _name_imports(tree=tree, current=current, modules=modules) | _attribute_reaches(
            tree=tree, current=current, aliases=aliases, modules=modules
        )
        for module, name in reached:
            defining = rel_by_module[module]
            if name in functions[defining]:
                public.add((defining, name))
        for name in _entry_point_names(tree=tree) & _declared_all(tree=tree) & functions[rel]:
            public.add((rel, name))
    return frozenset(public)
