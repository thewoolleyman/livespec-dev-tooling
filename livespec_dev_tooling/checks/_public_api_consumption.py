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

    from livespec_dev_tooling.config import CrossRepoPublicApi

__all__: list[str] = [
    "declared_public_names",
    "repo_local_public_names",
    "stale_declarations",
]


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


def _suffix_index(*, sources: Mapping[Path, str]) -> dict[str, frozenset[Path]]:
    """Every dotted SUFFIX of every first-party module, mapped to its file(s).

    A repo-root-relative path is NOT an import path. `livespec-dev-tooling`'s
    package root IS its repo root, so `livespec_dev_tooling/config.py` really
    is imported as `livespec_dev_tooling.config` — but a LAYERED consumer roots
    its package deeper (`.claude-plugin/scripts/livespec/parse/foo.py` is
    imported as `livespec.parse.foo`), and a repo-root reading would resolve
    NOTHING there. Silently resolving nothing is the RELAXING direction, which
    is the dangerous one for this check.

    Resolution is therefore by dotted suffix. When a suffix is ambiguous
    (two files whose paths end the same way), EVERY candidate is returned and
    every one is treated as consumed — doubt resolves toward MORE enforcement,
    never less. That is a far weaker claim than bare-NAME matching, which
    compared only the function name and was measured wrong here.
    """
    index: dict[str, set[Path]] = {}
    for rel in sources:
        parts = _module_name(rel=rel).split(".")
        for start in range(len(parts)):
            index.setdefault(".".join(parts[start:]), set()).add(rel)
    return {suffix: frozenset(files) for suffix, files in index.items()}


def _module_aliases(
    *, tree: ast.Module, current: str, index: Mapping[str, frozenset[Path]]
) -> dict[str, str]:
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
                if submodule in index:
                    aliases[alias.asname or alias.name] = submodule
    return aliases


def _name_imports(
    *, tree: ast.Module, current: str, index: Mapping[str, frozenset[Path]]
) -> set[tuple[str, str]]:
    """`(dotted module, name)` pairs this module imports by NAME."""
    out: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        target = _import_from_target(node=node, current=current)
        if target not in index:
            continue
        for alias in node.names:
            if f"{target}.{alias.name}" in index or alias.name == "*":
                continue
            out.add((target, alias.name))
    return out


def _attribute_reaches(
    *, tree: ast.Module, aliases: Mapping[str, str], index: Mapping[str, frozenset[Path]]
) -> set[tuple[str, str]]:
    """`(dotted module, name)` pairs reached as `<module alias>.<name>`.

    The base MUST resolve through `aliases` — a name this module actually bound
    to a module by an `import` — and never by treating any dotted expression
    that happens to match a module path as one. Measured here: `config.pure_trees`
    on a local `Config` INSTANCE matches the module `livespec_dev_tooling.config`
    by name, and admitting it manufactured 19 phantom consumptions in this repo.
    That is this thread's own "read the callee, do not match the name" lesson
    recurring inside the oracle written to apply it.
    """
    out: set[tuple[str, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        target = aliases.get(ast.unparse(node.value))
        if target is not None and target in index:
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
    index = _suffix_index(sources=sources)
    functions = {rel: _top_level_functions(tree=tree) for rel, tree in trees.items()}

    public: set[tuple[Path, str]] = set()
    for rel, tree in trees.items():
        current = _module_name(rel=rel)
        aliases = _module_aliases(tree=tree, current=current, index=index)
        reached = _name_imports(tree=tree, current=current, index=index) | _attribute_reaches(
            tree=tree, aliases=aliases, index=index
        )
        for dotted, name in reached:
            for defining in index[dotted]:
                if defining != rel and name in functions[defining]:
                    public.add((defining, name))
        for name in _entry_point_names(tree=tree) & _declared_all(tree=tree) & functions[rel]:
            public.add((rel, name))
    return frozenset(public)


def _resolved_declarations(
    *, declared: tuple[CrossRepoPublicApi, ...], sources: Mapping[Path, str]
) -> tuple[frozenset[tuple[Path, str]], tuple[CrossRepoPublicApi, ...]]:
    """Split declared entries into the ones that resolve and the ones that do not."""
    functions = {
        rel: _top_level_functions(tree=ast.parse(source)) for rel, source in sources.items()
    }
    resolved: set[tuple[Path, str]] = set()
    stale: list[CrossRepoPublicApi] = []
    for entry in declared:
        if entry.function in functions.get(entry.file, frozenset()):
            resolved.add((entry.file, entry.function))
        else:
            stale.append(entry)
    return frozenset(resolved), tuple(stale)


def declared_public_names(
    *, declared: tuple[CrossRepoPublicApi, ...], sources: Mapping[Path, str]
) -> frozenset[tuple[Path, str]]:
    """The `cross_repo_public_api` entries that resolve to a real top-level function.

    v178 measures consumption FLEET-WIDE, and forms 2 and 4 — plus form 1's
    sibling half — are invisible from inside one checkout. This is the declared
    stand-in, and it is TIGHTENING-ONLY (SPECIFICATION v036 §"Role keys"): the
    caller UNIONS it with the repo-local set, so an absent declaration removes
    nothing.
    """
    resolved, _ = _resolved_declarations(declared=declared, sources=sources)
    return resolved


def stale_declarations(
    *, declared: tuple[CrossRepoPublicApi, ...], sources: Mapping[Path, str]
) -> tuple[CrossRepoPublicApi, ...]:
    """Declared entries whose file or function no longer exists.

    SPECIFICATION v036 makes this a HARD failure rather than a warning: a
    declaration that outlives its subject is the defect class this rule set
    exists to remove, and the whole point of the key is to stand in for a
    measurement the local check cannot take.
    """
    _, stale = _resolved_declarations(declared=declared, sources=sources)
    return stale
