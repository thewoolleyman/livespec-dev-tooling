"""_public_api_consumption — which top-level functions are CONSUMED ACROSS A BOUNDARY.

`livespec` v178 (`non-functional-requirements.md` section "ROP composition") replaced
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

from livespec_dev_tooling.checks._import_resolution import (
    attribute_reaches,
    declared_all,
    module_aliases,
    module_name,
    name_imports,
    suffix_index,
    top_level_functions,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_dev_tooling.config import CrossRepoPublicApi

__all__: list[str] = [
    "declared_public_names",
    "repo_local_public_names",
    "stale_declarations",
]


_MAIN_GUARD_NAMES = frozenset({"__name__", "__main__"})


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
    index = suffix_index(sources=sources)
    functions = {rel: top_level_functions(tree=tree) for rel, tree in trees.items()}

    public: set[tuple[Path, str]] = set()
    for rel, tree in trees.items():
        current = module_name(rel=rel)
        aliases = module_aliases(tree=tree, current=current, index=index)
        reached = name_imports(tree=tree, current=current, index=index) | attribute_reaches(
            tree=tree, aliases=aliases, index=index
        )
        for dotted, name in reached:
            for defining in index[dotted]:
                if defining != rel and name in functions[defining]:
                    public.add((defining, name))
        for name in _entry_point_names(tree=tree) & declared_all(tree=tree) & functions[rel]:
            public.add((rel, name))
    return frozenset(public)


def _resolved_declarations(
    *, declared: tuple[CrossRepoPublicApi, ...], sources: Mapping[Path, str]
) -> tuple[frozenset[tuple[Path, str]], tuple[CrossRepoPublicApi, ...]]:
    """Split declared entries into the ones that resolve and the ones that do not."""
    functions = {
        rel: top_level_functions(tree=ast.parse(source)) for rel, source in sources.items()
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
    stand-in, and it is TIGHTENING-ONLY (SPECIFICATION v036 section "Role keys"): the
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
