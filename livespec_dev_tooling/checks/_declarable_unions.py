"""_declarable_unions — WHICH unions v183's condition-3 carrier may be declared over.

Bound 1's structural gate and bound 3's variant-set staleness detector, split
from `_single_meaning_variants` at the seam between "what may be declared" and
"what a declaration relieves". Every limb here is RE-DERIVED from the parsed
universe on every run; nothing about declarability is read from the declaration.
The declaration supplies only WHICH union is claimed and, for bound 3, the SCOPE
the claim covers.

**THE FOUR LIMBS OF BOUND 1** — (a) the declared name resolves to a module-level
closed union alias in the declared file; (b) every operand resolves to a type
DEFINED in this repo's first-party universe, since a union reaching a foreign or
unresolvable type is not closed from where the claim is being made; (c) every
variant is CONSTRUCTED somewhere in that universe, because a variant nothing ever
produces is not "inhabited and load-bearing" and a decorative failure variant
would otherwise buy the whole union its relief; and (d) CONDITION 2 HOLDS as
COMPUTED, delegated to `_union_consumption`.

**BOUND 3 IS STRICTER THAN ITS MEMBER-2 ANALOGUE, DELIBERATELY.** The declared
variants must EQUAL the operand set as recomputed from source, so ADDING a
variant BREAKS the declaration rather than silently inheriting it. Condition 3
quantifies over every variant, so a declaration that does not enumerate them is a
claim with an unbounded subject, and a variant added by a later editor would
otherwise acquire a guarantee nobody ever made about it. **Enumerating the
variants stores the SCOPE of the semantic claim, never the claim itself.**

## NAMES ARE RESOLVED THROUGH IMPORT BINDINGS HERE, AND THE POLARITY IS WHY

Limbs (b) and (c) resolve through an actual `import` binding rather than matching
a bare name, the discipline `_public_api_consumption` established after a
bare-name oracle was measured wrong on this very repo. Failing to resolve REJECTS
the entry, so under-resolution is the STRICT direction. `_union_consumption`
matches terminally instead, because there the polarity inverts; that module
states its half.

## TWO BOUNDS ARE STATED RATHER THAN LEFT TO BE DISCOVERED

- **ONLY the `A | B` SPELLING IS READ.** A `Union[A, B]` alias, a PEP 695 `type`
  statement, or an operand that is not a plain name is not recognised as a union
  and the entry is REJECTED naming limb (a). That is the strict end — such a repo
  gets no relief rather than unverified relief — but a consumer spelling its union
  another way must re-spell it to declare it.
- **A CONSTRUCTION REACHED AS `<module>.<Variant>(...)` IS NOT READ** by limb (c).
  The variant reads as unconstructed and the declaration is REJECTED, which is
  again the strict end.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks._import_resolution import suffix_index
from livespec_dev_tooling.checks._io_boundary_calls import ModuleFacts
from livespec_dev_tooling.checks._union_consumption import condition_2_holds

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_dev_tooling.config import SingleMeaningVariant

__all__: list[str] = [
    "CONSUMPTION_NOT_EXHAUSTIVE",
    "OPERAND_FOREIGN",
    "UNION_UNRESOLVED",
    "VARIANT_SET_MISMATCH",
    "VARIANT_UNCONSTRUCTED",
    "Universe",
    "build_universe",
    "union_rejections",
]


UNION_UNRESOLVED = (
    "no module-level union alias of that name, spelled `A | B` over plain names, in that file"
)
OPERAND_FOREIGN = "a union operand does not resolve to a type defined in this repo"
VARIANT_UNCONSTRUCTED = "a union variant is constructed nowhere in this repo"
CONSUMPTION_NOT_EXHAUSTIVE = (
    "a consumption site discriminates this union without an exhaustive `match`"
)
VARIANT_SET_MISMATCH = "the declared variants are not the union's operand set as computed"


@dataclass(frozen=True, kw_only=True)
class RejectedVariantDeclaration:
    """One `single_meaning_variants` entry the check MUST hard-fail on, and WHY.

    `rejection` names the limb or bound that refused it, because the remedies
    differ: a limb (a) or bound 3 rejection is a declaration to correct, a limb
    (b), (c) or (d) rejection is a union that has STOPPED being declarable and
    whose returning functions are conversions now owed.
    """

    entry: SingleMeaningVariant
    rejection: str


@dataclass(frozen=True, kw_only=True)
class Universe:
    """The repo's parsed first-party universe plus the bindings resolution needs."""

    trees: dict[Path, ast.Module]
    index: dict[str, frozenset[Path]]
    modules: dict[Path, ModuleFacts]
    classes: frozenset[tuple[Path, str]]
    constructed: frozenset[tuple[Path, str]]


def _flatten(*, node: ast.expr) -> tuple[str, ...] | None:
    """The operand names of an `A | B | C` expression, or None if it is not one."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        left = _flatten(node=node.left)
        right = _flatten(node=node.right)
        return None if left is None or right is None else left + right
    return (node.id,) if isinstance(node, ast.Name) else None


def _operands(*, tree: ast.Module, union: str) -> tuple[str, ...]:
    """Limb (a): the operands of `union`'s MODULE-LEVEL alias, or `()`.

    Scoped to `tree.body` rather than `ast.walk`: an assignment inside a function
    body is a local binding no annotation elsewhere resolves through, and reading
    those would let a consumer declare a union nothing outside that body can name.
    """
    for node in tree.body:
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value = node.value
        else:
            continue
        if union in targets and value is not None:
            flat = _flatten(node=value)
            return flat if flat is not None and len(flat) > 1 else ()
    return ()


def _resolve_type(
    *,
    name: str,
    rel: Path,
    modules: Mapping[Path, ModuleFacts],
    index: Mapping[str, frozenset[Path]],
    classes: frozenset[tuple[Path, str]],
) -> frozenset[Path]:
    """Every first-party file that could DEFINE the class `name` as seen from `rel`.

    Resolved through the import binding, never by bare name — the discipline
    `_public_api_consumption` established after a bare-name oracle was measured
    wrong on this very repo.
    """
    if (rel, name) in classes:
        return frozenset({rel})
    dotted = modules[rel].imported_names.get(name)
    if dotted is None:
        return frozenset()
    return frozenset(
        defining for defining in index.get(dotted, frozenset()) if (defining, name) in classes
    )


def _constructed_types(
    *,
    trees: Mapping[Path, ast.Module],
    modules: Mapping[Path, ModuleFacts],
    index: Mapping[str, frozenset[Path]],
    classes: frozenset[tuple[Path, str]],
) -> frozenset[tuple[Path, str]]:
    """Limb (c)'s raw material: every `(defining file, class)` pair CONSTRUCTED."""
    out: set[tuple[Path, str]] = set()
    for rel, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                out |= {
                    (defining, node.func.id)
                    for defining in _resolve_type(
                        name=node.func.id,
                        rel=rel,
                        modules=modules,
                        index=index,
                        classes=classes,
                    )
                }
    return frozenset(out)


def build_universe(*, sources: Mapping[Path, str]) -> Universe:
    """Parse the universe once — every limb reads the same trees and bindings."""
    trees = {rel: ast.parse(source) for rel, source in sources.items()}
    index = suffix_index(sources=sources)
    modules = {rel: ModuleFacts(rel=rel, tree=tree, index=index) for rel, tree in trees.items()}
    classes = frozenset(
        (rel, node.name)
        for rel, tree in trees.items()
        for node in tree.body
        if isinstance(node, ast.ClassDef)
    )
    return Universe(
        trees=trees,
        index=index,
        modules=modules,
        classes=classes,
        constructed=_constructed_types(trees=trees, modules=modules, index=index, classes=classes),
    )


def _all_constructed(*, defining: Mapping[str, frozenset[Path]], universe: Universe) -> bool:
    """Limb (c): is every variant CONSTRUCTED at one of the files defining it?"""
    return all(
        any((candidate, name) in universe.constructed for candidate in files)
        for name, files in defining.items()
    )


def _declarability_rejection(
    *,
    operands: tuple[str, ...],
    defining: Mapping[str, frozenset[Path]],
    declared: frozenset[str],
    universe: Universe,
) -> str | None:
    """Limbs (b)-(d) and bound 3, in the order whose diagnosis is most actionable.

    Limb (b) precedes bound 3 so a union reaching a foreign type is reported as
    an unclosed union rather than as a scope mismatch the operator would then
    "fix" by declaring the foreign variant.
    """
    if not all(defining.values()):
        return OPERAND_FOREIGN
    if declared != frozenset(operands):
        return VARIANT_SET_MISMATCH
    if not _all_constructed(defining=defining, universe=universe):
        return VARIANT_UNCONSTRUCTED
    if not condition_2_holds(trees=universe.trees, variants=frozenset(operands)):
        return CONSUMPTION_NOT_EXHAUSTIVE
    return None


def _union_rejection(
    *, file: Path, union: str, declared: frozenset[str], universe: Universe
) -> str | None:
    """The limb or bound this union fails, or None when it is declarable.

    Every limb is RE-DERIVED here from the parsed universe. Nothing about
    declarability is read from the declaration; the declaration supplies only
    WHICH union is claimed and, for bound 3, the SCOPE the claim covers.
    """
    tree = universe.trees.get(file)
    operands = _operands(tree=tree, union=union) if tree is not None else ()
    if not operands:
        return UNION_UNRESOLVED
    defining = {
        name: _resolve_type(
            name=name,
            rel=file,
            modules=universe.modules,
            index=universe.index,
            classes=universe.classes,
        )
        for name in operands
    }
    return _declarability_rejection(
        operands=operands, defining=defining, declared=declared, universe=universe
    )


def union_rejections(
    *, declared: tuple[SingleMeaningVariant, ...], universe: Universe
) -> dict[tuple[Path, str], str]:
    """Each declared union keyed to the limb it fails, omitting the ones that hold.

    Entries are grouped into per-UNION scopes first, because bound 3 is a claim
    about the SET of declared variants and cannot be decided one entry at a time.
    """
    scopes: dict[tuple[Path, str], set[str]] = {}
    for entry in declared:
        scopes.setdefault((entry.file, entry.union), set()).add(entry.variant)
    out: dict[tuple[Path, str], str] = {}
    for (file, union), variants in scopes.items():
        rejection = _union_rejection(
            file=file, union=union, declared=frozenset(variants), universe=universe
        )
        if rejection is not None:
            out[(file, union)] = rejection
    return out
