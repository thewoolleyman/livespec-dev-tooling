"""_public_api_graph — which functions are consumed ACROSS a member boundary.

livespec v178 defines public API as CONSUMED ACROSS A BOUNDARY, measured
FLEET-WIDE. `checks/_public_api_consumption` owns the half one checkout can
compute; this module owns the half it structurally CANNOT — a sibling's
import. A repo-local oracle would have classified `parse_manifest` as
non-public: the exact function whose conversion turned a sibling's master RED
(`livespec-dev-tooling-dx8l`).

RESOLUTION IS MODULE-QUALIFIED AND THE RESOLVER IS THE SHARED ONE.
`checks/_import_resolution` already carries the fixes for two measured
defects, BOTH in the relaxing direction; a second copy is how the fleet ends
up with eight forks of one rule. The bare-name shortcut was measured wrong on
this very question: it scored `merged_branch_sweep.fetch_manifest` public on
two consumers that both import a DIFFERENT `fetch_manifest`, and produced 51
false `parse_argv` hits against a sibling homonym.

THE TWO UNIVERSES ARE ASYMMETRIC, AND THAT IS v178's SHAPE RATHER THAN AN
OVERSIGHT. The DEFINING side is a member's first-party NON-TEST universe — the
set `resolve_check_universe()` yields, because that is what the Result-return
rule scopes. The CONSUMING side ALSO includes test trees, because v178 form 2
is a cross-repo TEST import: four siblings' test trees consume
`testing.cli_e2e` today. A same-repo test importer is still not a consumer,
and that falls out for free — only edges BETWEEN members are emitted.

A MEMBER THAT CAN SATISFY AN IMPORT ITSELF IS NOT REACHING ACROSS A BOUNDARY,
and this is not a refinement — the first real fleet measurement produced 14
false findings against 7 members without it. `.claude/hooks/
livespec_footgun_guard.py` is INSTALLED FOREIGN CONTENT: a byte-identical copy
ships in most members. `livespec-driver-codex` does `import
livespec_footgun_guard` after a `sys.path` insert pointing at ITS OWN copy, and
the bare suffix matched every member's. Python resolves that import to the
copy on the path, so when the consuming member is itself among the candidates
the import is LOCAL and no cross-member edge exists at all. Reporting one would
fail a sibling for a file the consumer never opens.

CLAUSE 0 IS APPLIED HERE RATHER THAN LEFT TO EACH CONSUMER. v178 keeps the
`_`-prefix disqualifier, so an `_`-prefixed function is never public API no
matter who imports it. The same measurement produced findings against
`_check_segment` and `_decision` before this was applied.

AMBIGUITY IS REPORTED RATHER THAN HIDDEN. `suffix_index` resolves an ambiguous
dotted suffix toward EVERY candidate rather than guessing, because doubt must
resolve toward more enforcement. Inside one repo that is purely the tightening
direction and needs no report. FLEET-WIDE it can name member A as the definer
of something a homonym in member B actually defines, and a row that failed a
member on such an edge without saying so would manufacture exactly the
confidently-wrong finding this epic exists to remove. So every edge carries
whether its target resolved to ONE defining file.

A SOURCE THAT WILL NOT PARSE IS A NAMED BLIND SPOT, NOT A SILENT DROP. Nine
members' trees are read here, and one syntactically invalid file must not
propagate a raise through a nine-member sweep — the shape
`livespec-dev-tooling-9sl0` removed from `pin_autodiscovery.discover`. Nor may
it vanish: an unparsed DEFINING file contributes no functions and an unparsed
CONSUMING file contributes no imports, so either one shrinks the graph
silently. They are returned beside the edges so the row can say so.

The analysis is STATIC and cannot see `getattr` / `importlib` / string
dispatch — a blind spot v178 states rather than leaves to be discovered.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks._import_resolution import (
    attribute_reaches,
    module_aliases,
    module_name,
    name_imports,
    suffix_index,
    top_level_functions,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from livespec_dev_tooling.config import Config

__all__: list[str] = [
    "ConsumptionEdge",
    "ConsumptionGraph",
    "FleetConsumption",
    "MemberSources",
    "UnparsedSource",
    "cross_member_consumption",
]


@dataclass(frozen=True, kw_only=True)
class MemberSources:
    """One member's two source universes, keyed by repo-root-relative path.

    `defining` is what the Result-return rule scopes — first-party, non-test.
    `consuming` is who may reach across a boundary, which includes the test
    trees `defining` excludes. They are separate fields rather than one set
    plus a predicate because the asymmetry is the CONTRACT, and a single
    universe filtered at the point of use is how it would drift.
    """

    defining: Mapping[Path, str]
    consuming: Mapping[Path, str]


@dataclass(frozen=True, kw_only=True)
class ConsumptionEdge:
    """One function defined in one member and reached from another.

    `uniquely_resolved` is False when the import's dotted suffix matched more
    than one defining file across the fleet. The edge is still emitted — doubt
    resolves toward more enforcement — but a consumer of this graph must be
    able to say "and this one is ambiguous" rather than assert it flatly.
    """

    defining_member: str
    defining_file: Path
    function: str
    consuming_member: str
    consuming_file: Path
    uniquely_resolved: bool


@dataclass(frozen=True, kw_only=True)
class UnparsedSource:
    """A source file the graph could not read, and therefore did not measure."""

    member: str
    file: Path
    detail: str


@dataclass(frozen=True, kw_only=True)
class ConsumptionGraph:
    """Every cross-member consumption, plus what could not be measured."""

    edges: tuple[ConsumptionEdge, ...]
    unparsed: tuple[UnparsedSource, ...]


@dataclass(frozen=True, kw_only=True)
class FleetConsumption:
    """The fleet graph plus every per-member input it was computed over.

    Carried as ONE value because a row consuming it is called once per member
    and must not recompute a nine-member graph nine times. `unavailable` is
    part of the value rather than a side channel: a member whose tree or
    config could not be read contributed NOTHING to the graph, and a consumer
    that cannot tell that member from a clean one would report the fleet as
    conformant on the strength of not having looked.
    """

    graph: ConsumptionGraph
    sources: Mapping[str, MemberSources]
    configs: Mapping[str, Config]
    unavailable: Mapping[str, str]


def _qualified(*, member: str, rel: Path) -> Path:
    """`rel` prefixed with its member, so one index can span the whole fleet.

    The member name is carried as a leading PATH component so `module_name`
    turns it into a leading dotted component. Member names hold hyphens
    (`livespec-dev-tooling`), which cannot appear in a Python module path, so
    the prefix can never itself be matched by an import — it only keeps two
    members' identical relative paths apart in one index.
    """
    return Path(member) / rel


def _parsed(
    *, member: str, sources: Mapping[Path, str], into: list[UnparsedSource]
) -> dict[Path, ast.Module]:
    """Parse each source, recording rather than raising on the ones that fail."""
    trees: dict[Path, ast.Module] = {}
    for rel, text in sources.items():
        try:
            trees[rel] = ast.parse(text)
        except SyntaxError as invalid:
            # NARROW, and the only failure `ast.parse` has on a `str` input.
            # Nine members' trees flow through here; one invalid file must not
            # kill the sweep, and must not vanish either.
            into.append(UnparsedSource(member=member, file=rel, detail=str(invalid)))
    return trees


def _public_functions(*, tree: ast.Module) -> frozenset[str]:
    """The module's top-level functions minus the `_`-prefixed ones.

    v178 clause 0 keeps the `_`-prefix disqualifier: an `_`-prefixed function
    is never public API no matter who imports it. Applied HERE rather than left
    to each consumer of the graph, because a consumer that forgot would report
    a private helper as an undeclared public surface — which the first real
    fleet measurement did, against `_check_segment` and `_decision`.
    """
    return frozenset(name for name in top_level_functions(tree=tree) if not name.startswith("_"))


@dataclass(frozen=True, kw_only=True)
class _DefiningFacts:
    """What the defining side of the fleet contributes to edge resolution.

    `reexports` is the half `functions` alone cannot answer: a name a file
    IMPORTS from another first-party module and re-exports is not among that
    file's own definitions, so a reach resolved to the facade would be dropped
    without it.
    """

    index: dict[str, frozenset[Path]]
    functions: dict[Path, frozenset[str]]
    reexports: dict[Path, dict[str, str]]


def _defining_index(
    *, members: Mapping[str, MemberSources], unparsed: list[UnparsedSource]
) -> _DefiningFacts:
    """The fleet-wide suffix index, each defining file's functions, and its re-exports."""
    texts: dict[Path, str] = {}
    functions: dict[Path, frozenset[str]] = {}
    trees_by_file: dict[Path, ast.Module] = {}
    for member, sources in members.items():
        trees = _parsed(member=member, sources=sources.defining, into=unparsed)
        for rel, tree in trees.items():
            qualified = _qualified(member=member, rel=rel)
            texts[qualified] = sources.defining[rel]
            functions[qualified] = _public_functions(tree=tree)
            trees_by_file[qualified] = tree
    index = suffix_index(sources=texts)
    reexports = {
        qualified: {
            name: dotted
            for dotted, name in name_imports(
                tree=tree, current=module_name(rel=qualified), index=index
            )
        }
        for qualified, tree in trees_by_file.items()
    }
    return _DefiningFacts(index=index, functions=functions, reexports=reexports)


def cross_member_consumption(*, members: Mapping[str, MemberSources]) -> ConsumptionGraph:
    """Every `(defining member, file, function)` reached from a DIFFERENT member.

    Same-member reaches are dropped rather than never computed: they are the
    half `checks/_public_api_consumption` already owns from inside the
    checkout, and recomputing them here would put one rule in two places.
    """
    unparsed: list[UnparsedSource] = []
    facts = _defining_index(members=members, unparsed=unparsed)
    edges: list[ConsumptionEdge] = []
    for member, sources in members.items():
        trees = _parsed(member=member, sources=sources.consuming, into=unparsed)
        for rel, tree in trees.items():
            current = module_name(rel=_qualified(member=member, rel=rel))
            aliases = module_aliases(tree=tree, current=current, index=facts.index)
            reached = name_imports(
                tree=tree, current=current, index=facts.index
            ) | attribute_reaches(tree=tree, aliases=aliases, index=facts.index)
            edges.extend(_edges_for(member=member, rel=rel, reached=reached, facts=facts))
    return ConsumptionGraph(edges=tuple(sorted(edges, key=_edge_order)), unparsed=tuple(unparsed))


def _through_reexports(
    *, start: Path, name: str, facts: _DefiningFacts
) -> tuple[frozenset[Path], bool]:
    """Files DEFINING `name`, reached from `start` by following re-exports.

    A facade that re-exports a name defines nothing itself, so a reach that
    lands on it must be re-resolved to the module the name comes FROM.
    MEASURED: without this, four siblings' consumption of
    `_cli_e2e_discovery.discover_fixtures` through `cli_e2e` produced NO edge
    at all — not against the facade, not against the definer — because
    `_edges_for` dropped the reach the moment the facade did not define it.

    The walk is BOUNDED BY A VISITED SET rather than by a hop limit: a
    re-export cycle is a real shape (two modules importing each other's names)
    and an arbitrary depth cap would silently stop resolving a legitimate
    chain. It returns whether every hop resolved to exactly ONE candidate, so
    an ambiguity introduced by the re-export is reported the same way an
    ambiguity in the original reach is — `uniquely_resolved` must not become
    optimistic just because the answer took an extra hop.
    """
    defining: set[Path] = set()
    unique = True
    seen: set[Path] = set()
    frontier = [start]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        if name in facts.functions.get(current, frozenset()):
            defining.add(current)
            continue
        dotted = facts.reexports.get(current, {}).get(name)
        if dotted is None:
            continue
        candidates = facts.index.get(dotted, frozenset())
        unique = unique and len(candidates) == 1
        frontier.extend(candidates)
    return frozenset(defining), unique


def _edges_for(
    *, member: str, rel: Path, reached: set[tuple[str, str]], facts: _DefiningFacts
) -> list[ConsumptionEdge]:
    """The cross-member edges one consuming file's reaches produce."""
    found: list[ConsumptionEdge] = []
    for dotted, name in reached:
        candidates = facts.index[dotted]
        if any(candidate.parts[0] == member for candidate in candidates):
            # The consuming member defines this module ITSELF, so Python
            # resolves the import to its own copy and nothing crosses a
            # boundary. Measured: without this, one byte-identical installed
            # hook produced 14 false findings across 7 members, because a
            # bare-name import satisfied locally matched every member's copy.
            # ⛔ APPLIED BEFORE the re-export walk, deliberately: a hop that
            # re-resolved elsewhere must not smuggle the consumer's own copy
            # back in as a cross-member edge.
            continue
        defining_files: set[Path] = set()
        hops_unique = True
        for candidate in candidates:
            reached_defining, candidate_unique = _through_reexports(
                start=candidate, name=name, facts=facts
            )
            defining_files |= reached_defining
            hops_unique = hops_unique and candidate_unique
        if any(defining.parts[0] == member for defining in defining_files):
            # The re-export led back into the CONSUMING member, which the
            # pre-hop guard could not see because the FACADE belongs to the
            # sibling alone. Python satisfies the name from the consumer's own
            # copy, so nothing crosses a boundary — and the test is `any`, not
            # a per-file skip: emitting the sibling's copy while skipping the
            # consumer's would fail a member for a file it never opens, which
            # is the 14-false-findings shape the pre-hop guard exists to stop.
            continue
        for defining in sorted(defining_files):
            found.append(
                ConsumptionEdge(
                    defining_member=defining.parts[0],
                    defining_file=Path(*defining.parts[1:]),
                    function=name,
                    consuming_member=member,
                    consuming_file=rel,
                    uniquely_resolved=len(candidates) == 1 and hops_unique,
                )
            )
    return found


def _edge_order(edge: ConsumptionEdge) -> tuple[str, str, str, str, str]:
    """Stable ordering, so a row's output does not churn between runs."""
    return (
        edge.defining_member,
        edge.defining_file.as_posix(),
        edge.function,
        edge.consuming_member,
        edge.consuming_file.as_posix(),
    )
