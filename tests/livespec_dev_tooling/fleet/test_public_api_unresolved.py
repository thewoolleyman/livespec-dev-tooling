"""Tests for `livespec_dev_tooling/fleet/_public_api_unresolved.py` and its wiring.

The GRAPH-level cases live here rather than in `test_public_api_graph.py`
because the Red-Green-Replay ritual stages exactly ONE test file per Red, and
this is the file that must record the Red. Against the code as it stood, the
positive fixture below produced no edge, no reach and no finding AT ALL — the
consumption vanished — which is the defect `livespec-dev-tooling-9s2j` names.

There is ONE positive here and the rest are its controls, which is the right
ratio for this row rather than a shortage of cases. The oracle cannot see
`getattr` / `importlib` / string dispatch, so a reach that fired on a name the
module still binds by some other means would MUTE a real row — the item's own
stated failure mode. Most of what follows exists to hold that fence in place.
"""

from __future__ import annotations

import ast
from pathlib import Path

from livespec_dev_tooling.fleet._public_api_graph import (
    MemberSources,
    cross_member_consumption,
)
from livespec_dev_tooling.fleet._public_api_unresolved import (
    bound_names,
    unresolved_reach,
)

__all__: list[str] = []


def sources(*, defining: dict[str, str], consuming: dict[str, str]) -> MemberSources:
    """`MemberSources` from path-string keys, so fixtures read as file trees."""
    return MemberSources(
        defining={Path(path): text for path, text in defining.items()},
        consuming={Path(path): text for path, text in consuming.items()},
    )


_BINDINGS_SOURCE = """
import os
import json as encoder
from pathlib import Path as Location

CONSTANT = 1
annotated: int = 2


class Widget:
    pass


def _private() -> int:
    return 1


async def spun() -> int:
    return 2
"""


def test_every_shape_that_satisfies_a_siblings_import_counts_as_bound() -> None:
    """The noise fence, at its narrowest: bound is NOT the same as public API.

    `_public_api_graph.functions` answers "is this public API here" and drops
    classes, constants and `_`-prefixed helpers. That question cannot say a
    name is GONE — every shape below satisfies a sibling's `import` statement
    at runtime, so convicting one would manufacture a finding against a reach
    the graph already drops on purpose.
    """
    assert bound_names(tree=ast.parse(_BINDINGS_SOURCE)) == frozenset(
        {"os", "encoder", "Location", "CONSTANT", "annotated", "Widget", "_private", "spun"}
    )


def test_a_namespace_that_cannot_be_enumerated_answers_unknown_rather_than_empty() -> None:
    """`None` is "we cannot say", and it must not read as "it defines nothing".

    A star-import re-exports whatever the source module holds and a
    module-level `__getattr__` synthesizes attributes on demand. Neither can be
    enumerated statically, and reporting a missing name against either is the
    `getattr` half of the blind spot this row states rather than hides.
    """
    assert bound_names(tree=ast.parse("from pkg.everything import *\n")) is None
    assert bound_names(tree=ast.parse("def __getattr__(name: str) -> int:\n    return 1\n")) is None


_DEFINER = "pkg/contract.py"
_AFTER_DELETION = "def kept(*, text: str) -> str:\n    return text\n"
_SIBLING = "app/use.py"
_SIBLING_SOURCE = "from pkg.contract import parse_manifest, render_manifest\n"


def test_a_function_deleted_out_from_under_a_sibling_is_an_unresolved_reach() -> None:
    """THE DEFECT. `pkg/contract.py` remains; the names the sibling imports do not.

    Before this outcome existed the graph reported NOTHING here: the reach
    resolved to a real defining file, the walk found neither name in it, and
    `_edges_for` dropped the consumption instead of convicting on it. Silence
    in exactly the case that breaks the consumer hardest — an undeclared
    function is a declaration gap, a deleted one is an `ImportError` in a
    sibling repo at runtime.

    Two missing names in one import statement, because the reach set is
    unordered: a single one would pass against an implementation that emits in
    whatever order the set iterates.
    """
    graph = cross_member_consumption(
        members={
            "lib": sources(
                defining={_DEFINER: _AFTER_DELETION}, consuming={_DEFINER: _AFTER_DELETION}
            ),
            "app": sources(defining={}, consuming={_SIBLING: _SIBLING_SOURCE}),
        }
    )
    assert graph.edges == ()
    assert [
        (reach.consuming_member, reach.consuming_file.as_posix(), reach.module, reach.name)
        for reach in graph.unresolved
    ] == [
        ("app", _SIBLING, "pkg.contract", "parse_manifest"),
        ("app", _SIBLING, "pkg.contract", "render_manifest"),
    ]
    assert graph.unresolved[0].defining_members == ("lib",)


_STILL_BOUND = (
    "from pkg.helpers import forwarded\n"
    "\n"
    "\n"
    "VERSION = 1\n"
    "\n"
    "\n"
    "class Manifest:\n"
    "    pass\n"
    "\n"
    "\n"
    "def _private() -> int:\n"
    "    return 1\n"
)


def test_a_name_the_module_still_binds_some_other_way_is_never_a_broken_reach() -> None:
    """NEGATIVE CONTROL — the four shapes that produce no edge and no reach either.

    Each of these reaches is already dropped by the graph: a class and a
    constant are not top-level functions, an `_`-prefixed name is disqualified
    by v178 clause 0, and a re-exported name is defined elsewhere. All four are
    still BOUND, so every one of them imports fine and none is this defect.
    Convicting them is how a real row gets muted.
    """
    graph = cross_member_consumption(
        members={
            "lib": sources(defining={_DEFINER: _STILL_BOUND}, consuming={_DEFINER: _STILL_BOUND}),
            "app": sources(
                defining={},
                consuming={
                    _SIBLING: "from pkg.contract import VERSION, Manifest, _private, forwarded\n"
                },
            ),
        }
    )
    assert graph.edges == ()
    assert graph.unresolved == ()


def test_a_definer_whose_namespace_cannot_be_enumerated_is_never_convicted() -> None:
    """NEGATIVE CONTROL — the `getattr` blind spot, held at the GRAPH level.

    `pkg/contract.py` re-exports a star, so the names the sibling imports may
    well be there and no static read can say otherwise. Reporting them missing
    would be the oracle asserting a completeness it does not have, which is
    exactly how the item says a real row gets muted.
    """
    star = "from pkg.everything import *\n"
    graph = cross_member_consumption(
        members={
            "lib": sources(defining={_DEFINER: star}, consuming={_DEFINER: star}),
            "app": sources(defining={}, consuming={_SIBLING: _SIBLING_SOURCE}),
        }
    )
    assert graph.edges == ()
    assert graph.unresolved == ()


def test_a_module_outside_the_fleet_index_stays_silent() -> None:
    """NEGATIVE CONTROL — case (b): a stdlib or third-party import is not a fleet concern.

    `tomllib` resolves nowhere in the index, so no member owes anything and
    there is nothing to report. The `kept` import in the same fixture is the
    discriminator: the fleet-resolvable reach beside it still produces its
    edge, so a graph that had simply stopped resolving would fail this.
    """
    graph = cross_member_consumption(
        members={
            "lib": sources(defining={_DEFINER: _AFTER_DELETION}, consuming={}),
            "app": sources(
                defining={},
                consuming={
                    _SIBLING: "from tomllib import loads\nfrom pkg.contract import kept\n",
                },
            ),
        }
    )
    assert [edge.function for edge in graph.edges] == ["kept"]
    assert graph.unresolved == ()


def test_a_reach_that_resolved_to_no_file_at_all_is_silent() -> None:
    """The same case (b), asserted at the seam rather than through the graph.

    `name_imports` and `attribute_reaches` both drop a target absent from the
    index, so the graph never hands an empty candidate set down. The guard is
    kept anyway, and tested here, because a silence that rests on a caller's
    invariant is one refactor away from becoming noise.
    """
    assert (
        unresolved_reach(
            consuming=Path("app/app/use.py"),
            reach=("tomllib", "loads"),
            candidates=frozenset(),
            bindings={},
        )
        is None
    )


_HOOK_BODY = "def main() -> int:\n    return 0\n"
_HOOK = "hooks/livespec_footgun_guard.py"
_IMPL_SOURCE = "def probe(*, at: str) -> str:\n    return at\n"
_FACADE_SOURCE = 'from pkg.impl import probe\n\n__all__: list[str] = ["probe"]\n'


def test_the_pre_hop_guard_still_yields_neither_an_edge_nor_a_reach() -> None:
    """NEGATIVE CONTROL — the 14-false-findings shape, on the guard that runs FIRST.

    `codex` ships its own byte-identical copy of the installed hook, so Python
    satisfies the import locally and nothing crosses a boundary. The name it
    imports is bound in NEITHER copy, so an unresolved reach emitted before
    this guard — or instead of it — would fail seven members for a file the
    consumer never opens, which is precisely the shape the guard exists to
    prevent.
    """
    shared = {_HOOK: _HOOK_BODY}
    graph = cross_member_consumption(
        members={
            "alpha": sources(defining=shared, consuming=shared),
            "codex": sources(
                defining=shared,
                consuming={
                    **shared,
                    "tests/test_hook.py": "from livespec_footgun_guard import removed\n",
                },
            ),
        }
    )
    assert graph.edges == ()
    assert graph.unresolved == ()


def test_the_post_hop_guard_still_yields_neither_an_edge_nor_a_reach() -> None:
    """NEGATIVE CONTROL — the same shape on the guard the re-export walk needs.

    `pkg/facade.py` exists only in `alpha`, so the pre-hop guard cannot fire —
    the reach genuinely leaves `beta`. Following the re-export lands in
    `pkg/impl.py`, which BOTH members ship, and Python would satisfy `beta`'s
    import from `beta`'s own copy. The reach resolves, so it is not this defect
    either, and the graph must stay silent on both counts.
    """
    graph = cross_member_consumption(
        members={
            "alpha": sources(
                defining={"pkg/impl.py": _IMPL_SOURCE, "pkg/facade.py": _FACADE_SOURCE},
                consuming={"pkg/impl.py": _IMPL_SOURCE, "pkg/facade.py": _FACADE_SOURCE},
            ),
            "beta": sources(
                defining={"pkg/impl.py": _IMPL_SOURCE},
                consuming={
                    "pkg/impl.py": _IMPL_SOURCE,
                    "app.py": "from pkg.facade import probe\n",
                },
            ),
        }
    )
    assert graph.edges == ()
    assert graph.unresolved == ()


def test_the_existing_edge_surface_is_untouched_by_the_third_outcome() -> None:
    """NO REGRESSION — the ambiguous suffix and the unparsed source both still report.

    `uniquely_resolved` and `unparsed` are the two places the graph already
    admits doubt rather than hiding it. A third outcome that quietly changed
    either would trade one silent shrink for another.
    """
    body = "def helper() -> int:\n    return 1\n"
    graph = cross_member_consumption(
        members={
            "alpha": sources(defining={"pkg/util.py": body}, consuming={}),
            "beta": sources(defining={"pkg/util.py": body}, consuming={}),
            "gamma": sources(
                defining={"pkg/broken.py": "def (:\n"},
                consuming={"app.py": "from pkg.util import helper\n"},
            ),
        }
    )
    assert [
        (edge.defining_member, edge.function, edge.uniquely_resolved) for edge in graph.edges
    ] == [("alpha", "helper", False), ("beta", "helper", False)]
    assert [(item.member, item.file.as_posix()) for item in graph.unparsed] == [
        ("gamma", "pkg/broken.py")
    ]
    assert graph.unresolved == ()
