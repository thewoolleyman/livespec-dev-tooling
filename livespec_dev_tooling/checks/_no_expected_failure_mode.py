"""_no_expected_failure_mode — livespec v179 member 1, computed not declared.

`livespec` v179 (`non-functional-requirements.md` §"ROP composition") scopes the
Result-return rule to a public function that HAS an expected failure mode. A
function with none has nothing to flow, and a `Result` over it carries an
UNINHABITED failure track whose dead unwraps hide the live ones.

Member 1 decides that MECHANICALLY. A public function has no expected failure
mode when a purely syntactic analysis shows ALL of:

- (a) no `raise` statement;
- (b) no `try` statement;
- (c) no call to an I/O boundary — a module under the consumer's declared
  `io_trees`, or the filesystem / process / network / environment surface;
- (d) every FIRST-PARTY function it calls also satisfies (a)-(d), computed as a
  FIXPOINT over the consumer's own call graph; and
- (e) its `return` annotation is NOT of the form `X | None`.

**IT STORES NO CLAIM, so it cannot erode and cannot become a dumping ground.**
Membership is recomputed from the code on every run: add a `raise`, a `try`, an
I/O call, or a call to a function that has one, and the rule re-arms at that
commit. There is nothing to declare into.

## CLAUSE (d) PROPAGATES (a)-(d), NOT (e) — and the difference is load-bearing

The ratified text says a callee must satisfy "(a)-(d)", not "(a)-(e)". Clause
(e) is about the function's OWN signature — an `X | None` return is a
hand-rolled failure track it exposes to ITS callers — and it does not infect a
caller that handles the `None`. Propagating (e) would disqualify
`denotes_same_release` for calling `tag_version_component`, whose `None` is a
declared legitimate absence (member 2). Reading "(a)-(d)" as "(a)-(e)" is the
easiest way to implement this clause wrong.

## CLAUSE (c) IS NOT A TERMINAL-NAME MATCH, AND THIS REPO PAID TO LEARN IT

Matching call NAMES once flagged ten "total" functions as touching I/O; reading
them showed most hits were `dict.get` / `settings.get` and only three were real.
So the RECEIVER is resolved through an actual `import` binding — `os.environ.get`
is I/O because `os` is, `settings.get` is not because `settings` is a local.
**`get` is not an I/O verb.** The same lesson produced 19 phantom consumptions
inside `_import_resolution`, whose graph this module reuses rather than forks.

**AN INJECTED SEAM IS NOT A BOUNDARY.** `runner.run(...)` on a parameter is the
shape this fleet uses to make I/O testable, and it is the same distinction that
convicted `fetch_manifest` under clause (e) rather than clause (c). So `run` is
deliberately absent from the unresolved-receiver verb set, while `subprocess.run`
is still caught — through its resolved module, where the receiver is known.

## THE ONE PLACE THIS IS NOT CONSERVATIVE, STATED RATHER THAN HIDDEN

For a call whose receiver resolves to NOTHING — `path.read_text()`, where `path`
is a parameter — there is no binding to consult, and only the verb is left. The
analysis consults `_UNRESOLVED_RECEIVER_IO_VERBS` there and treats a non-match
as not-I/O. Treating every such call as doubt instead would disqualify any
function that calls a method on any argument, which is nearly all of them: the
member would exempt approximately nothing and the clause would be defeated
rather than enforced. Everywhere else — an unresolvable CALLEE NAME, an
ambiguous module suffix — doubt disqualifies, per the ratified direction.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks._import_resolution import suffix_index
from livespec_dev_tooling.checks._io_boundary_calls import ModuleFacts, calls_of

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

__all__: list[str] = ["functions_without_expected_failure_mode", "returns_x_or_none"]


@dataclass(frozen=True, kw_only=True)
class _LocalAnalysis:
    """Per-function clause (a), (b), (c) and (e) results, plus the (d) call graph."""

    edges: dict[tuple[Path, str], frozenset[tuple[Path, str]]]
    disqualified: set[tuple[Path, str]]
    x_or_none: set[tuple[Path, str]]


def returns_x_or_none(*, func: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Clause (e): is the return annotation of the form `X | None`?

    PUBLIC to this package because member 2's STRUCTURAL GATE
    (`_declared_absence_returns`, SPECIFICATION v037 bound 1) must gate EXACTLY
    the shape this clause refuses. Two independent readers of the same annotation
    is how a gate and the clause it relieves drift apart.

    Both spellings count — `X | None` parses to a `BinOp`, `Optional[X]` to a
    `Subscript` — because the shape the clause refuses is the hand-rolled
    failure track, not one way of writing it.
    """
    if func.returns is None:
        return False
    rendered = ast.unparse(func.returns)
    # `.strip()` per member is NOT cosmetic: `ast.unparse` renders the union
    # with spaces (`str | None`), so an unstripped comparison misses EVERY
    # `X | None` return — silently exempting the whole shape clause (e) exists
    # to refuse, and making member 2's declaration key unnecessary. Caught by
    # `tag_version_component` coming out exempt when it must not.
    parts = {part.strip() for part in rendered.split("|")}
    return "None" in parts or rendered.startswith(("Optional[", "typing.Optional["))


def _local_analysis(
    *,
    trees: Mapping[Path, ast.Module],
    modules: Mapping[Path, ModuleFacts],
    index: Mapping[str, frozenset[Path]],
    io_trees: tuple[Path, ...],
) -> _LocalAnalysis:
    """Per-function clauses (a), (b), (c), (e) plus the call edges (d) walks."""
    edges: dict[tuple[Path, str], frozenset[tuple[Path, str]]] = {}
    disqualified: set[tuple[Path, str]] = set()
    x_or_none: set[tuple[Path, str]] = set()
    for rel, tree in trees.items():
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            key = (rel, node.name)
            if any(isinstance(inner, ast.Raise | ast.Try) for inner in ast.walk(node)):
                disqualified.add(key)
            if returns_x_or_none(func=node):
                x_or_none.add(key)
            outcome = calls_of(
                func=node,
                facts=modules[rel],
                index=index,
                modules=modules,
                io_trees=io_trees,
            )
            edges[key] = outcome.edges
            if outcome.disqualifies:
                disqualified.add(key)
    return _LocalAnalysis(edges=edges, disqualified=disqualified, x_or_none=x_or_none)


def _propagate(*, analysis: _LocalAnalysis) -> set[tuple[Path, str]]:
    """Clause (d): the least fixpoint of disqualification over the call graph.

    A callee absent from `edges` is a function this analysis never saw — a
    nested def, a method, a name that resolved to a module outside the
    universe. That is doubt, so it disqualifies its caller.
    """
    disqualified = set(analysis.disqualified)
    changed = True
    while changed:
        changed = False
        for key, callees in analysis.edges.items():
            if key in disqualified:
                continue
            if any(callee not in analysis.edges or callee in disqualified for callee in callees):
                disqualified.add(key)
                changed = True
    return disqualified


def functions_without_expected_failure_mode(
    *, sources: Mapping[Path, str], io_trees: tuple[Path, ...]
) -> frozenset[tuple[Path, str]]:
    """`(defining path, function name)` pairs livespec v179 member 1 exempts.

    Recomputed from `sources` on every call — it stores no claim, so there is
    nothing to go stale and nothing to declare into. The result is the
    COMPLEMENT of a least fixpoint: a function is disqualified when (a), (b),
    (c) or an unresolvable callee disqualifies it locally, or when any
    first-party callee is disqualified. Clause (e) is applied LAST and is NOT
    propagated — the ratified text says a callee must satisfy "(a)-(d)".
    """
    trees = {rel: ast.parse(source) for rel, source in sources.items()}
    index = suffix_index(sources=sources)
    modules = {rel: ModuleFacts(rel=rel, tree=tree, index=index) for rel, tree in trees.items()}
    analysis = _local_analysis(trees=trees, modules=modules, index=index, io_trees=io_trees)
    disqualified = _propagate(analysis=analysis)
    return frozenset(
        key for key in analysis.edges if key not in disqualified and key not in analysis.x_or_none
    )
