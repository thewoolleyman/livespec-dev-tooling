"""_union_consumption — what one site DOES to a union: discriminate it, or not.

The condition-2 half of livespec v183's rendering-boundary clause. Split from
`_single_meaning_variants` at the seam between the two questions — this module
answers "what does this site do to the union", that one answers "what do the
bounds conclude" — the same split `_io_boundary_calls` and
`_no_expected_failure_mode` already draw for member 1's clause (c).

**CONDITION 2 VERBATIM:** a consumer MUST discriminate the union with a `match`
statement terminating in `case _: assert_never(<subject>)`. A chain of
independent `if isinstance(...)` tests does NOT satisfy it and is NOT sanctioned,
EVEN WHERE IT IS EXHAUSTIVE TODAY.

⛔ **THE REASON IS MECHANICAL RATHER THAN STYLISTIC, and it is why this module
reads what it reads.** `check-assert-never-exhaustiveness` polices `match`
statements and CANNOT SEE an `isinstance` chain, so a union consumed that way is
governed by nothing and a newly-added variant falls silently through every site.
Condition 2 exists to move consumption sites INSIDE an existing check's field of
view, not to add a new check or a new severity.

## ⛔ NAMES ARE MATCHED TERMINALLY HERE, AND THAT IS THE OPPOSITE DISCIPLINE FROM ITS CALLER

`_single_meaning_variants` resolves operand and construction names through import
bindings, because failing to resolve REJECTS the declaration and under-resolution
is therefore the strict direction. Here the polarity inverts: failing to SEE a
consumption site leaves it unchecked, which is the RELAXING direction. So a
terminal-name match is used deliberately — an `isinstance` spelled
`isinstance(x, _context.RowPass)` is still seen, and matching an unrelated
homonym merely demands exhaustiveness of a `match` this rule set already requires
it of everywhere.

⚠️ **AND THE VANTAGE IS LOCAL, WHICH v183 STATES RATHER THAN HIDES.** Condition 2
quantifies over EVERY consumer and consumption is measured FLEET-WIDE, while this
runs inside ONE checkout. A governed sibling's non-exhaustive consumption is
structurally invisible here and is the central-vantage row's obligation.
"""

from __future__ import annotations

import ast
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__: list[str] = ["condition_2_holds", "terminal_name"]


def terminal_name(*, node: ast.expr) -> str:
    """The last dotted segment of a name expression, ignoring any subscript."""
    return ast.unparse(node).split("[", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


def _isinstance_over(*, node: ast.Call, variants: frozenset[str]) -> bool:
    """Does this call test membership of one of `variants` via `isinstance`?

    ANY such test refuses the union, not only a demonstrated CHAIN of them. The
    key this feeds is relaxing-only, so doubt about whether a lone test is a
    discrimination or a narrowing guard must TIGHTEN.
    """
    if not (isinstance(node.func, ast.Name) and node.func.id == "isinstance"):
        return False
    candidates = [
        element
        for argument in node.args[1:2]
        for element in (argument.elts if isinstance(argument, ast.Tuple) else [argument])
    ]
    return any(terminal_name(node=element) in variants for element in candidates)


def _match_over(*, node: ast.Match, variants: frozenset[str]) -> bool:
    """Does this `match` discriminate one of `variants` by a class pattern?"""
    return any(
        isinstance(pattern, ast.MatchClass) and terminal_name(node=pattern.cls) in variants
        for case in node.cases
        for pattern in ast.walk(case.pattern)
    )


def _exhaustive(*, node: ast.Match) -> bool:
    """Does this `match` terminate in `case _: assert_never(...)`?

    The same structural terminator `check-assert-never-exhaustiveness` requires,
    read here because condition 2 exists precisely to keep a sanctioned union's
    consumption sites inside THAT check's field of view.

    No empty-`cases` guard: the grammar requires at least one `case` block, so a
    zero-case `match` never parses. Defensive code for an unreachable state is
    what a 100% coverage gate exists to keep out.
    """
    last = node.cases[-1]
    pattern = last.pattern
    if not (isinstance(pattern, ast.MatchAs) and pattern.pattern is None and pattern.name is None):
        return False
    if len(last.body) != 1 or not isinstance(last.body[0], ast.Expr):
        return False
    call = last.body[0].value
    return isinstance(call, ast.Call) and terminal_name(node=call.func) == "assert_never"


def condition_2_holds(*, trees: Mapping[Path, ast.Module], variants: frozenset[str]) -> bool:
    """Does EVERY locally visible consumption site discriminate `variants` exhaustively?

    A site is a `match` naming a variant in a class pattern, or an `isinstance`
    test naming one. The first refuses unless it terminates in `assert_never`;
    the second refuses outright.
    """
    for tree in trees.values():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _isinstance_over(node=node, variants=variants):
                return False
            if (
                isinstance(node, ast.Match)
                and _match_over(node=node, variants=variants)
                and not _exhaustive(node=node)
            ):
                return False
    return True
