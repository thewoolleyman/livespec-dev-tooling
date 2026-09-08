"""_public_api_unresolved — a sibling imports a name this member NO LONGER BINDS.

`_public_api_graph` emits a consumption edge only where an import RESOLVES to a
defining file. So DELETING a function a sibling still imports did not turn its
edge into a violation — the edge VANISHED, and `cross-repo-public-api-declared`
reported nothing at all (`livespec-dev-tooling-9s2j`). The row was silent in
exactly the case that breaks the consumer hardest: an undeclared-but-present
function is a DECLARATION GAP, while a deleted one is an `ImportError` in a
sibling repo at runtime. This module carries the second outcome so the graph can
return it BESIDE its edges, the way unparsed sources already ride beside them.

FIVE FENCES, AND EVERY ONE WAS PAID FOR BY A MEASURED FALSE-POSITIVE
POPULATION. A row that fires on ordinary imports is a row that gets muted,
which is how the real finding is lost:

- **THE CANDIDATE SET MUST BE NON-EMPTY.** A dotted module that resolves nowhere
  in the fleet suffix index is an ordinary stdlib or third-party import and must
  stay silent. `livespec-dev-tooling-xs58` is what makes that fence sufficient:
  before it, a gitignored `.venv/lib/python3.10/site-packages` tree entered a
  member's first-party DEFINING universe through a parameter named `tracked_py`,
  so a vendored `dataclasses.py` made a STDLIB suffix resolve to a "first-party"
  definer. The first attempt at this row carried this exact fence and still
  emitted 1196 findings against one member, every one of them a stdlib name read
  out of a virtualenv. The fence was right; the population was wrong.
- **A BARE TOP-LEVEL SUFFIX IS NOT EVIDENCE OF A CROSS-MEMBER REACH.**
  `suffix_index` maps EVERY dotted suffix of a module path, including its bare
  last component, because resolution must work for a member that roots its
  package deeper than its repo. Fleet-wide that means one member's
  `.../commands/io.py` answers `from io import BytesIO` and its
  `.../test_plugin_structure.py` answers a sibling's same-repo test-helper
  import. MEASURED with the first two fences already in place: 40 names across
  5 members, EVERY one a false claim. Neither file is importable under its bare
  name from another member's tree — Python answers the first from the stdlib and
  the second from the consumer's own rootdir. This is the `livespec_footgun_
  guard` lesson again: a single-component suffix matches every member's copy and
  says nothing about which file was opened.
- **A STDLIB ROOT PACKAGE IS EVIDENCE AGAINST A CROSS-MEMBER REACH.** The fence
  above already removes every single-component collision; this one keeps a
  DOTTED stdlib path (`os.path`, `collections.abc`, `importlib.metadata`) from
  becoming the next one the day a member names two nested directories that way.
  It is a claim about import resolution, not a name blocklist: a member's file
  cannot shadow a stdlib package it does not sit on the path of.
- **ONLY A `from <module> import <name>` REACH MAY CONVICT.** An ATTRIBUTE reach
  is deliberately excluded. `module_aliases` binds a name to a module on
  `from pkg import mod`, and every `mod.<attr>` in that file is then a reach —
  including attributes of an INSTANCE that shares the module's name, the shape
  that manufactured 19 phantom consumptions in this repo before
  `attribute_reaches` was tightened. Those reaches produce no edge today because
  a non-function name resolves to nothing, so admitting them here would convert
  a silent drop into a stream of false ImportError claims. The defect this row
  exists for is an import-time failure; `from X import Y` is where it lives.
- **ANY TOP-LEVEL BINDING SUPPRESSES THE RECORD, not merely a public function.**
  A sibling importing a CLASS, a constant, a re-exported third-party name or a
  `_`-prefixed helper resolves to no defining file either, because the graph's
  defining set is public top-level FUNCTIONS. Convicting on those would report
  every cross-member class import as a broken consumer. So the question this
  module asks is the one the runtime asks: does the module BIND the name at all?

AMBIGUITY RESOLVES TOWARD SILENCE HERE, which is the opposite of the direction
`suffix_index` takes for edges, and the asymmetry is deliberate. An ambiguous
suffix means the row cannot tell WHICH file Python would import; an edge is a
claim that a name is public (doubt toward more enforcement is safe), while this
record is a claim that a sibling is BROKEN AT IMPORT TIME (doubt toward less
noise is safe). So one binding candidate among several suppresses the record.

The analysis is STATIC and cannot see `getattr` / `importlib` / string dispatch,
so a name absent from every binding may still be reachable, and a record here is
a claim about the static import graph rather than about the running program.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__: list[str] = [
    "UnresolvedReach",
    "bound_names",
    "broken_consumer_message",
    "sorted_reaches",
    "unresolved_reach",
]


_STAR_IMPORT = "*"


@dataclass(frozen=True, kw_only=True)
class UnresolvedReach:
    """One name a member imports that the member(s) it resolved to do not bind.

    `defining_members` is plural because an ambiguous dotted suffix resolves
    toward every candidate: the record names each member whose files answered
    the module and none of which bound the name, rather than guessing one.
    """

    consuming_member: str
    consuming_file: Path
    module: str
    name: str
    defining_members: tuple[str, ...]


def _bound_by(*, node: ast.stmt) -> frozenset[str]:
    """The top-level names one statement binds, or nothing when it binds none.

    `If` and `Try` recurse because a module-level `if TYPE_CHECKING:` block and
    a `try: import x / except ImportError:` fallback are both ordinary ways to
    bind a name a sibling may legitimately import; treating either as binding
    nothing would convict on a name the module really does export. Function and
    class BODIES are deliberately not walked — a local variable is not a module
    attribute, and admitting one would suppress a genuine finding.
    """
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return frozenset({node.name})
    if isinstance(node, ast.Import | ast.ImportFrom):
        return frozenset(alias.asname or alias.name.partition(".")[0] for alias in node.names)
    if isinstance(node, ast.If | ast.Try):
        return _bound_in(body=_guarded_body(node=node))
    return _assigned_by(node=node)


def _guarded_body(*, node: ast.If | ast.Try) -> list[ast.stmt]:
    """Every module-level statement a conditional or `try` block guards."""
    if isinstance(node, ast.If):
        return [*node.body, *node.orelse]
    handled = [statement for handler in node.handlers for statement in handler.body]
    return [*node.body, *node.orelse, *node.finalbody, *handled]


def _assigned_by(*, node: ast.stmt) -> frozenset[str]:
    """The names an assignment binds, or nothing when the statement is not one."""
    if isinstance(node, ast.Assign):
        # The targets are WALKED rather than read directly, so `first, second =
        # ...` and `head, *rest = ...` bind their parts. A module constant
        # published by tuple unpacking is rare but real, and reading it as
        # binding nothing would convict a sibling that imports it.
        return frozenset(
            inner.id
            for target in node.targets
            for inner in ast.walk(target)
            if isinstance(inner, ast.Name)
        )
    if isinstance(node, ast.AnnAssign | ast.AugAssign) and isinstance(node.target, ast.Name):
        return frozenset({node.target.id})
    return frozenset()


def _bound_in(*, body: list[ast.stmt]) -> frozenset[str]:
    """Every name the statements in `body` bind."""
    bound: set[str] = set()
    for node in body:
        bound |= _bound_by(node=node)
    return frozenset(bound)


def bound_names(*, tree: ast.Module) -> frozenset[str]:
    """Every name the module binds at its top level, however it binds it.

    A `from x import *` contributes the literal `*`, which `unresolved_reach`
    reads as "this module may bind anything" — the honest answer, since the
    star's members are not knowable from this module's own source.
    """
    return _bound_in(body=tree.body)


def _binds(*, names: frozenset[str], name: str) -> bool:
    """Whether a defining file's binding set answers `name`."""
    return _STAR_IMPORT in names or name in names


def unresolved_reach(
    *,
    member: str,
    rel: Path,
    module: str,
    name: str,
    candidates: frozenset[Path],
    bindings: Mapping[Path, frozenset[str]],
) -> UnresolvedReach | None:
    """The record `member`'s import of `module.name` owes, or None when it owes none.

    `candidates` are the member-qualified defining files the dotted module
    resolved to, and `bindings` maps each such file to the names it binds. Four
    of the module docstring's five fences are applied here in order; the caller
    owns the remaining one — only a `from <module> import <name>` reach reaches
    this function at all.
    """
    if not candidates:
        return None
    if "." not in module or module.partition(".")[0] in sys.stdlib_module_names:
        # A BARE top-level suffix is not evidence of a cross-member reach, and a
        # stdlib ROOT package is evidence against one. MEASURED against the real
        # fleet: `suffix_index` maps every dotted suffix INCLUDING the bare last
        # component, so a member's own `.../io.py` answered `from io import
        # BytesIO` and a `.../test_plugin_structure.py` answered a sibling test
        # helper import — 40 names across 5 members, every one a false claim
        # that a stdlib or same-repo import was broken. Neither is importable
        # under that bare name from another member's tree; Python answers the
        # first from the stdlib and the second from the consumer's own rootdir.
        return None
    if any(
        _binds(names=bindings.get(candidate, frozenset()), name=name) for candidate in candidates
    ):
        return None
    definers = tuple(sorted({candidate.parts[0] for candidate in candidates}))
    if member in definers:
        return None
    return UnresolvedReach(
        consuming_member=member,
        consuming_file=rel,
        module=module,
        name=name,
        defining_members=definers,
    )


def _reach_order(record: UnresolvedReach) -> tuple[str, str, str, str]:
    """Stable ordering, so a row's output does not churn between runs."""
    return (
        record.module,
        record.name,
        record.consuming_member,
        record.consuming_file.as_posix(),
    )


def sorted_reaches(*, records: list[UnresolvedReach]) -> tuple[UnresolvedReach, ...]:
    """`records` in the stable order a row reports them in."""
    return tuple(sorted(records, key=_reach_order))


def broken_consumer_message(*, repo: str, records: tuple[UnresolvedReach, ...]) -> list[str]:
    """The BROKEN-CONSUMER sentence for `repo`, or nothing when it has no records.

    A list rather than an optional string so the row can concatenate it with the
    declaration-gap sentence without a second emptiness test: the two outcomes
    are independent and a member can owe both at once.
    """
    if not records:
        return []
    missing: dict[str, list[str]] = {}
    for record in records:
        missing.setdefault(f"{record.module}::{record.name}", []).append(
            f"{record.consuming_member}:{record.consuming_file.as_posix()}"
        )
    named = "; ".join(
        f"{key} <- {', '.join(sorted(sites))}" for key, sites in sorted(missing.items())
    )
    return [
        f"{repo}: {len(missing)} name(s) a sibling IMPORTS are NO LONGER BOUND here -- "
        f"a BROKEN CONSUMER (an ImportError in that sibling at runtime), NOT a "
        f"declaration gap: {named}."
    ]
