"""Edge case for `_public_api_graph`'s re-export walk: the hop that lands HOME.

Separate from `test_public_api_graph.py` because that file is the Red-recorded
one of this change's Red-Green-Replay pair and is byte-identity-bound; a case
discovered while making the Green leg pass cannot be added to it.

The case is NOT the same as the local-copy guard already covered there. That
guard fires when the consuming member defines the module the reach RESOLVES to,
before any hop happens. This one fires when it does not — the facade belongs to
the sibling alone — and the re-export then hops into a module the consumer DOES
ship. A hop can change which member answers, so the boundary question has to be
re-asked after it.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.fleet._public_api_graph import (
    MemberSources,
    cross_member_consumption,
)

__all__: list[str] = []

_IMPL_SOURCE = """
def probe(*, at: str) -> str:
    return at
"""
_FACADE_SOURCE = """
from pkg.impl import probe

__all__: list[str] = ["probe"]
"""
_CONSUMER_SOURCE = """
from pkg.facade import probe

answer = probe(at="here")
"""


def _sources(*, defining: dict[str, str], consuming: dict[str, str]) -> MemberSources:
    return MemberSources(
        defining={Path(path): text for path, text in defining.items()},
        consuming={Path(path): text for path, text in consuming.items()},
    )


def test_a_reexport_hop_landing_in_the_consuming_member_crosses_no_boundary() -> None:
    """`beta` reaches `alpha`'s facade, whose re-export resolves back into `beta`.

    `pkg/facade.py` exists ONLY in `alpha`, so the pre-hop guard does not fire —
    the reach genuinely leaves `beta`. Following the re-export then finds
    `pkg/impl.py` in BOTH members, and Python would satisfy `beta`'s import from
    `beta`'s own copy. Emitting an edge against `alpha`'s copy would fail a
    sibling for a file the consumer never opens, which is the 14-false-findings
    shape the pre-hop guard exists to prevent.
    """
    graph = cross_member_consumption(
        members={
            "alpha": _sources(
                defining={"pkg/impl.py": _IMPL_SOURCE, "pkg/facade.py": _FACADE_SOURCE},
                consuming={"pkg/impl.py": _IMPL_SOURCE, "pkg/facade.py": _FACADE_SOURCE},
            ),
            "beta": _sources(
                defining={"pkg/impl.py": _IMPL_SOURCE},
                consuming={"pkg/impl.py": _IMPL_SOURCE, "app.py": _CONSUMER_SOURCE},
            ),
        }
    )
    assert graph.unparsed == ()
    assert graph.edges == ()


def test_the_same_reach_is_an_edge_when_the_consumer_ships_no_copy_of_the_impl() -> None:
    """The discriminator: drop `beta`'s own `pkg/impl.py` and the edge appears.

    Without this, the assertion above would also pass against a graph that had
    simply stopped following re-exports at all.
    """
    graph = cross_member_consumption(
        members={
            "alpha": _sources(
                defining={"pkg/impl.py": _IMPL_SOURCE, "pkg/facade.py": _FACADE_SOURCE},
                consuming={"pkg/impl.py": _IMPL_SOURCE, "pkg/facade.py": _FACADE_SOURCE},
            ),
            "beta": _sources(defining={}, consuming={"app.py": _CONSUMER_SOURCE}),
        }
    )
    assert [
        (edge.defining_member, edge.defining_file.as_posix(), edge.function) for edge in graph.edges
    ] == [("alpha", "pkg/impl.py", "probe")]
