"""_public_api_unresolved — a sibling still imports a name that is no longer there.

`_public_api_graph` builds a consumption EDGE only where an import resolves to a
file that still DEFINES the name. So when the definition is DELETED while a
sibling's import stays, there is nothing left to build an edge FROM: the
consumption did not become a violation, it VANISHED, and
`cross-repo-public-api-declared` reported nothing at all
(`livespec-dev-tooling-9s2j`).

THE ROW WAS SILENT IN EXACTLY THE CASE THAT BREAKS THE CONSUMER HARDEST. An
undeclared-but-present function is a DECLARATION GAP — the sibling still works,
and the definer owes a declaration. A DELETED one is an `ImportError` in the
sibling repo at runtime. This module carries the second outcome so it survives
the drop, BESIDE the edges for the same reason `UnparsedSource` is: a graph
that shrinks silently reads as a clean fleet.

⛔ TWO WAYS THE RESOLUTION COMES BACK EMPTY, AND ONLY ONE OF THEM IS A FINDING.
The dotted module still resolving to a sibling's file that no longer defines the
name is this defect. A dotted module that resolves NOWHERE in the fleet index is
a stdlib or third-party import and is not a fleet concern at all — it never even
reaches here, because `name_imports` and `attribute_reaches` both drop a target
absent from the index before any edge resolution runs. `unresolved_reach` still
answers None for an empty candidate set rather than relying on that, because a
silence that depends on a caller's invariant is one refactor from becoming noise.

⚠️ THE NOISE FENCE IS THE POINT, NOT A CAVEAT. This oracle cannot see `getattr`
/ `importlib` / string dispatch, and a row that fired on every dynamic or
legitimately-removed import is how a real row gets MUTED. So the question asked
here is the NARROWEST one that still catches the defect: does the module the
import resolves to BIND the name at all? Not "is it a public top-level
function" — a class, a constant, an `_`-prefixed helper and a re-exported name
all satisfy the sibling's `import` statement at runtime, so convicting any of
them would manufacture exactly the noise the item warns about, against reaches
`_public_api_graph` already drops on purpose.

`bound_names` therefore OVER-COLLECTS, and every error it makes is in the SILENT
direction: it walks the whole tree rather than module scope alone, so a name
bound only inside a function counts as bound; and it refuses to answer AT ALL
for a module carrying a star-import or a module-level `__getattr__`, both of
which can serve a name no static read can enumerate. A file that did not parse
is absent from the bindings map and is likewise treated as unanswerable, because
"we could not read it" is not "it does not define this".
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

__all__: list[str] = [
    "UnresolvedReach",
    "bound_names",
    "broken_consumer_note",
    "broken_consumers",
    "ordered_reaches",
    "unresolved_reach",
]

# A module whose namespace either of these appears in cannot be enumerated
# statically: `*` re-exports whatever the source module holds, and a
# module-level `__getattr__` (PEP 562) synthesizes attributes on demand — the
# `getattr` half of the blind spot this row states rather than hides.
_UNENUMERABLE = frozenset({"*", "__getattr__"})


@dataclass(frozen=True, kw_only=True)
class UnresolvedReach:
    """A name a sibling imports that the module it resolves to no longer binds.

    This is NOT a kind of edge and must never be rendered as one. An edge says
    "this member defines a function another member consumes"; a reach says "a
    sibling's import will not resolve", which is a defect in the DEFINING
    member measured from the CONSUMING side.

    `defining_members` names the members whose files the dotted module resolved
    to — the ones that owe the deleted definition — and is a tuple rather than
    a single name because an ambiguous dotted suffix resolves toward EVERY
    candidate here exactly as it does for an edge.
    """

    consuming_member: str
    consuming_file: Path
    module: str
    name: str
    defining_members: tuple[str, ...]


def bound_names(*, tree: ast.Module) -> frozenset[str] | None:
    """Every name this module binds, or None when its namespace is not enumerable.

    The question is deliberately "does an `import` of this name succeed", not
    "is this a public top-level function" — see the module docstring's noise
    fence. Functions, classes, assignments and imported names all count, and
    None means the answer is unknowable rather than empty.
    """
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Import):
            names.update(alias.asname or alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.update(alias.asname or alias.name for alias in node.names)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
    if names & _UNENUMERABLE:
        return None
    return frozenset(names)


def unresolved_reach(
    *,
    consuming: Path,
    reach: tuple[str, str],
    candidates: frozenset[Path],
    bindings: Mapping[Path, frozenset[str] | None],
) -> UnresolvedReach | None:
    """The record for a reach whose resolved files no longer bind the name, else None.

    `consuming` is the MEMBER-QUALIFIED path of the consuming file, split the
    same way `ConsumptionEdge` splits its defining side. `reach` is the
    `(dotted module, name)` pair `_edges_for` iterates.

    Returning None is the silent path, and every shape that is not the deleted
    definition takes it: no candidate at all (the third-party import, case b),
    a candidate whose namespace cannot be enumerated, and a candidate that
    still binds the name by any means.
    """
    module, name = reach
    if not candidates:
        return None
    for candidate in candidates:
        bound = bindings.get(candidate)
        if bound is None or name in bound:
            return None
    return UnresolvedReach(
        consuming_member=consuming.parts[0],
        consuming_file=Path(*consuming.parts[1:]),
        module=module,
        name=name,
        defining_members=tuple(sorted({candidate.parts[0] for candidate in candidates})),
    )


def _reach_order(reach: UnresolvedReach) -> tuple[str, str, str, str]:
    """Stable ordering, so a row's output does not churn between runs."""
    return (reach.consuming_member, reach.consuming_file.as_posix(), reach.module, reach.name)


def ordered_reaches(*, reaches: Iterable[UnresolvedReach]) -> tuple[UnresolvedReach, ...]:
    """`reaches` in the stable order a row reports them in."""
    return tuple(sorted(reaches, key=_reach_order))


def broken_consumers(
    *, reaches: Iterable[UnresolvedReach], repo: str
) -> tuple[UnresolvedReach, ...]:
    """The reaches `repo` OWES — the ones whose dotted module resolved into its files.

    Attribution is to the DEFINING side, matching the declaration-gap half the
    row already computes: the row is called once per member and asks what that
    member owes, and a deleted definition is owed by whoever deleted it. The
    CONSUMING member is the one that breaks, so it is NAMED by the finding
    rather than convicted by it — it did nothing wrong, and failing it would
    hand the remedy to the one repo that cannot apply it.
    """
    return tuple(reach for reach in reaches if repo in reach.defining_members)


def broken_consumer_note(*, repo: str, broken: tuple[UnresolvedReach, ...]) -> str:
    """The BROKEN-CONSUMER half of the row's finding, or "" when there is none.

    Worded so it cannot be read as the declaration-gap half. Conflating the two
    destroys the point of the row: "this member defines it but does not declare
    it" is a declaration gap the sibling survives, and its remedy is a
    declaration; "a sibling imports a name this member no longer defines" is an
    `ImportError` in that sibling, and no declaration can fix it.

    ⚠️ IT STATES ITS OWN LIMIT rather than asserting completeness, because a row
    that overclaims is a row that gets muted. The reading is STATIC in both
    directions: a name supplied dynamically would not be seen as present, and a
    consumer reaching this member through `getattr` / `importlib` / string
    dispatch would not be seen at all.
    """
    if not broken:
        return ""
    sites = sorted(
        f"{reach.module}::{reach.name} <- {reach.consuming_member}:"
        f"{reach.consuming_file.as_posix()}"
        for reach in broken
    )
    return (
        f"{repo}: {len(broken)} name(s) a sibling IMPORTS are NO LONGER DEFINED here -- a "
        f"BROKEN CONSUMER (an ImportError in that sibling at runtime), NOT a declaration "
        f"gap: {'; '.join(sites)}. Restore the definition or fix the consuming import; "
        f"declaring it cannot help. Read statically, so a definition supplied dynamically "
        f"would not be seen as present, and this list is not exhaustive. "
    )
