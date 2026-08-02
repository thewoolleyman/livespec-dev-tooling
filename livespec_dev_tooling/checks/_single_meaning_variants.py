"""_single_meaning_variants — livespec v183, condition 3's DECLARED carrier.

`livespec` v183 (`non-functional-requirements.md` section "ROP composition") sanctions a
CLOSED DISCRIMINATED UNION as an alternative railway spelling AT A RENDERING
BOUNDARY when three conditions hold. Conditions 1 and 2 are mechanizable, so they
BECOME the gate and stay COMPUTED; condition 3 — no variant carries two meanings —
is SEMANTIC and no static analysis can decide it, exactly as member 1 clause (e)
states of the `X | None` shape. The consumer therefore DECLARES condition 3 in the
`single_meaning_variants` role key, ONE ENTRY PER VARIANT, and this module is what
that declaration DOES.

## ⛔ THE RECOMPUTE IS THE ONLY THING SEPARATING THIS KEY FROM A DECLARED-EMPTY ESCAPE

This key is RELAXING-ONLY: it REMOVES functions from the Result-return rule's
scope. That is the same shape as the `pure_trees = []` declared-empty escape this
rule set exists to remove, and the tightening-only argument that bounds
`cross_repo_public_api` is NOT available here and MUST NOT be carried across on
the strength of the two being otherwise parallel. What makes this key legitimate
is ONE property, stated in the ratified text and implemented in
`_declarable_unions`: **the gate RE-DERIVES declarability from source on every run
and stores NO claim.** Bound 3 enumerates variants to store the claim's SCOPE
only, and diffs that scope against the code each run. **A declaration that is ever
TRUSTED rather than RE-DERIVED is this epic's founding defect re-created by its
own fix.**

## WHERE THE FOUR BOUNDS LIVE

Bound 2 (a written meaning per variant) is the LOADER's, enforced at parse time.
Bound 4 (the fleet-wide count, beside the number of FUNCTIONS each declaration
relieves) is the central-vantage row's. Bound 1's structural gate and bound 3's
variant-set staleness detector are `_declarable_unions`'. This module holds what
remains: which FUNCTIONS an accepted declaration relieves, and the reporting of
every rejected entry.

**EVERY REJECTION HARD-FAILS AND IS REPORTED.** v183 forecloses both wrong
readings by name: an entry failing any limb is neither silently ignored — which
would make a mis-declaration invisible, the manufactured-confidence shape this
epic exists to remove — nor accepted.

## ⛔ WHAT A DECLARATION DOES NOT DO

It does NOT reach condition 1. Condition 1 is a property of the FUNCTION, is
recomputed every run, and the ratified text forbids using the rendering-boundary
clause to avoid converting a leaf: a function returning a declared union that
calls a side-effecting primitive DIRECTLY remains convicted and MUST convert.
`declared_variant_names` therefore subtracts those functions, reusing
`_io_boundary_calls.calls_of` — the SHIPPED reader that resolves the receiver
through an import binding and already carves out the injected seam — rather than
forking a second reader. Two readers of one predicate is how a gate and the
clause it relieves drift apart.

It does NOT reach condition 2 either, which is a LIMB of the gate: a union whose
consumption drifts to an `isinstance` chain STOPS BEING DECLARABLE and its
declaration is REJECTED, rather than the declaration carrying it forward.

## ONE RESIDUAL IS UNGUARDED — the same one v183 records

Conditions 2 and 3 both quantify over EVERY consumer, and consumption is measured
FLEET-WIDE while this check runs inside ONE checkout. Limb (d) therefore computes
condition 2 over the LOCAL vantage only. A governed sibling consuming a declared
union non-exhaustively is invisible here, and catching it is the central-vantage
row's obligation under the same split-enforcement discipline v183 already ratifies
for the fleet-wide public-API criterion. Between a declaration and that row's next
run, a sibling's non-exhaustive consumption is unguarded.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks._declarable_unions import (
    CONSUMPTION_NOT_EXHAUSTIVE,
    OPERAND_FOREIGN,
    UNION_UNRESOLVED,
    VARIANT_SET_MISMATCH,
    VARIANT_UNCONSTRUCTED,
    Universe,
    build_universe,
    union_rejections,
)
from livespec_dev_tooling.checks._io_boundary_calls import calls_of
from livespec_dev_tooling.checks._union_consumption import terminal_name

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_dev_tooling.config import SingleMeaningVariant

# The five rejection reasons are RE-EXPORTED rather than redefined: the gate
# decides them and this module reports them, so one spelling must serve both.
__all__: list[str] = [
    "CONSUMPTION_NOT_EXHAUSTIVE",
    "OPERAND_FOREIGN",
    "UNION_UNRESOLVED",
    "VARIANT_SET_MISMATCH",
    "VARIANT_UNCONSTRUCTED",
    "RejectedVariantDeclaration",
    "declared_variant_names",
    "rejected_variant_declarations",
]


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


def _returns_union(
    *,
    func: ast.FunctionDef | ast.AsyncFunctionDef,
    rel: Path,
    file: Path,
    union: str,
    universe: Universe,
) -> bool:
    """Does `func` return the union DECLARED in `file`, resolved through imports?"""
    if func.returns is None or terminal_name(node=func.returns) != union:
        return False
    if rel == file:
        return True
    dotted = universe.modules[rel].imported_names.get(union)
    return dotted is not None and file in universe.index.get(dotted, frozenset())


def declared_variant_names(
    *,
    declared: tuple[SingleMeaningVariant, ...],
    sources: Mapping[Path, str],
    io_trees: tuple[Path, ...],
) -> frozenset[tuple[Path, str]]:
    """`(defining path, function name)` pairs v183's condition-3 carrier relieves.

    Only unions passing EVERY limb of bound 1 and bound 3 relieve anything — a
    rejected entry relieves NOTHING, so a mis-declaration cannot quietly buy an
    exemption it does not qualify for.

    ⛔ AND CONDITION 1 IS SUBTRACTED HERE. A function returning a declared union
    that calls a side-effecting primitive DIRECTLY stays convicted: the ratified
    text forbids using this clause to avoid converting a leaf, and that
    subtraction is what makes the gate NON-VACUOUS in both directions rather than
    a relief that can only relieve.
    """
    universe = build_universe(sources=sources)
    rejected = union_rejections(declared=declared, universe=universe)
    accepted = {
        (entry.file, entry.union) for entry in declared if (entry.file, entry.union) not in rejected
    }
    out: set[tuple[Path, str]] = set()
    for file, union in accepted:
        for rel, tree in universe.trees.items():
            for node in tree.body:
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if not _returns_union(
                    func=node, rel=rel, file=file, union=union, universe=universe
                ):
                    continue
                if not calls_of(
                    func=node,
                    facts=universe.modules[rel],
                    index=universe.index,
                    modules=universe.modules,
                    io_trees=io_trees,
                ).disqualifies:
                    out.add((rel, node.name))
    return frozenset(out)


def rejected_variant_declarations(
    *, declared: tuple[SingleMeaningVariant, ...], sources: Mapping[Path, str]
) -> tuple[RejectedVariantDeclaration, ...]:
    """Declared entries whose union fails bound 1 or bound 3, each with its diagnosis.

    A non-empty result MUST fail the consuming check. v183 makes every limb a
    hard failure naming the entry AND the limb, and rules out both alternatives
    by name: silently ignoring the entry would make the mis-declaration
    invisible, and accepting it would grant relief nothing computed.

    EVERY entry of a rejected union is reported, not one per union. The claim is
    carried per variant, so the operator's remedy is per variant too.
    """
    universe = build_universe(sources=sources)
    rejected = union_rejections(declared=declared, universe=universe)
    return tuple(
        RejectedVariantDeclaration(entry=entry, rejection=rejected[(entry.file, entry.union)])
        for entry in declared
        if (entry.file, entry.union) in rejected
    )
