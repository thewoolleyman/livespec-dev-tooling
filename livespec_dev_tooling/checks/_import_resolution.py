"""_import_resolution — resolve a first-party import to its DEFINING MODULE.

Extracted verbatim from `_public_api_consumption`, which was its only consumer
until livespec v179 member 1 needed the same graph to compute clause (d)'s
callee FIXPOINT. The extraction is deliberate rather than convenient: the
alternative is a second resolver, and **this one already carries two measured
defects that a fresh copy would not inherit the fixes for** — both in the
RELAXING direction, which is the dangerous one for every consumer of this
module. A second copy is how the fleet ends up with eight forks of one rule.

THE TWO DEFECTS, kept here because they are the reason each function is shaped
the way it is:

- **A REPO-ROOT-RELATIVE PATH IS NOT AN IMPORT PATH.** `livespec-dev-tooling`'s
  package root IS its repo root, so the naive reading happens to work here —
  but a LAYERED consumer roots its package deeper
  (`.claude-plugin/scripts/livespec/parse/foo.py` is imported as
  `livespec.parse.foo`), and the naive reading resolves NOTHING there. A check
  that silently resolves nothing is this fleet's own failure mode relocated
  into its oracle. Hence `suffix_index`, and hence ambiguity resolving toward
  MORE candidates rather than fewer.
- **AN ATTRIBUTE BASE MUST RESOLVE THROUGH AN ACTUAL `import` BINDING.**
  `config.pure_trees` on a local `Config` INSTANCE matches the module path
  `livespec_dev_tooling.config` by name, and admitting it manufactured 19
  phantom consumptions in this repo. Hence `attribute_reaches` consults
  `aliases` and never matches a dotted expression against a module path.

Both are the same lesson — READ THE CALLEE, DO NOT MATCH THE NAME — and both
were found INSIDE the oracle written to apply it.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__: list[str] = [
    "attribute_reaches",
    "declared_all",
    "module_aliases",
    "module_name",
    "name_imports",
    "suffix_index",
    "top_level_functions",
]


_INIT_FILENAME = "__init__.py"


def module_name(*, rel: Path) -> str:
    """Dotted module name for a repo-root-relative first-party `.py` path."""
    parts = list(rel.parts)
    if parts[-1] == _INIT_FILENAME:
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].removesuffix(".py")
    return ".".join(parts)


def declared_all(*, tree: ast.Module) -> frozenset[str]:
    """The string members of the module's `__all__`, if it declares one."""
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


def top_level_functions(*, tree: ast.Module) -> frozenset[str]:
    """Names of the module's top-level `def` / `async def` statements."""
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


def suffix_index(*, sources: Mapping[Path, str]) -> dict[str, frozenset[Path]]:
    """Every dotted SUFFIX of every first-party module, mapped to its file(s).

    A repo-root-relative path is NOT an import path. `livespec-dev-tooling`'s
    package root IS its repo root, so `livespec_dev_tooling/config.py` really
    is imported as `livespec_dev_tooling.config` — but a LAYERED consumer roots
    its package deeper (`.claude-plugin/scripts/livespec/parse/foo.py` is
    imported as `livespec.parse.foo`), and a repo-root reading would resolve
    NOTHING there. Silently resolving nothing is the RELAXING direction, which
    is the dangerous one for every consumer of this module.

    Resolution is therefore by dotted suffix. When a suffix is ambiguous
    (two files whose paths end the same way), EVERY candidate is returned and
    every one is treated as reached — doubt resolves toward MORE enforcement,
    never less. That is a far weaker claim than bare-NAME matching, which
    compared only the function name and was measured wrong here.
    """
    index: dict[str, set[Path]] = {}
    for rel in sources:
        parts = module_name(rel=rel).split(".")
        for start in range(len(parts)):
            index.setdefault(".".join(parts[start:]), set()).add(rel)
    return {suffix: frozenset(files) for suffix, files in index.items()}


def module_aliases(
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


def name_imports(
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


def attribute_reaches(
    *, tree: ast.Module, aliases: Mapping[str, str], index: Mapping[str, frozenset[Path]]
) -> set[tuple[str, str]]:
    """`(dotted module, name)` pairs reached as `<module alias>.<name>`.

    The base MUST resolve through `aliases` — a name this module actually bound
    to a module by an `import` — and never by treating any dotted expression
    that happens to match a module path as one. Measured here: `config.pure_trees`
    on a local `Config` INSTANCE matches the module `livespec_dev_tooling.config`
    by name, and admitting it manufactured 19 phantom consumptions in this repo.
    That is this fleet's own "read the callee, do not match the name" lesson
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
