"""The consumption measurement's failure track — `livespec-dev-tooling-qndn.14`.

`cross_member_consumption` returned a bare `ConsumptionGraph`, and that single
spelling carried two different answers. One was "nine members' sources all
parsed, and this is what the fleet consumes". The other was "one member shipped
a file I could not read, so this is what the fleet consumes ACCORDING TO the
files I could" — a strictly smaller edge set, because an unparsed DEFINING file
contributes no functions and an unparsed CONSUMING file contributes no imports.

THE COLLAPSE WAS NOT INERT, and it is the reason livespec v186 refuses to
relieve this function. `_parsed`'s `except SyntaxError: into.append(...)` is an
in-band CENSUS rather than a discharge: the failure is expected, it is real, and
it reached the caller as an ordinary FIELD on the value. A field can be left
unread; a failure track cannot. A shrunken graph that says nothing reads as "the
fleet is clean", which is the summary shape the ROP epic exists to remove.

The census itself stays IN the graph, which is the half this conversion does NOT
change: `_rows_public_api_conformance` reports per-member blind spots out of
`graph.unparsed` and excludes those files from its local-public set, and moving
the list onto the failure payload would put one list in two places. The partial
graph therefore travels ON the failure track — the invalid file must not kill a
nine-member sweep — while no longer wearing a whole measurement's spelling.

It rides `Result`, not `IOResult`, and that is deliberate. This function is
handed source TEXT and performs no I/O at all; `_member_sources` is the seam
that reads the disk and is honestly `IOResult` already. Claiming an effect this
one does not have would blur that distinction rather than sharpen it.
"""

from __future__ import annotations

from pathlib import Path

from returns.result import Failure, Success

from livespec_dev_tooling.fleet._public_api_graph import (
    MemberSources,
    cross_member_consumption,
)

__all__: list[str] = []

# The two names `checks/public_api_result_typed` accepts as railway-typed, and
# the terminal-name reduction it applies before comparing. Restated here rather
# than imported so this file pins the PROPERTY the shipped detector reads,
# independently of that module continuing to exist in its current shape.
_RAILWAY_RETURN_NAMES = frozenset({"Result", "IOResult"})

_LIBRARY = "pkg/contract.py"
_LIBRARY_SOURCE = "def parse_manifest(*, text: str) -> str:\n    return text\n"
_CONSUMER = "hooks/gate.py"
_CONSUMER_SOURCE = "from pkg.contract import parse_manifest\n\nparse_manifest(text='x')\n"
_BROKEN = "pkg/broken.py"
_BROKEN_SOURCE = "def (:\n"


def _terminal_return_name(*, rendered: str) -> str:
    """`Result[ConsumptionGraph, PartialConsumption]` → `Result`.

    Mirrors `public_api_result_typed._annotation_head_name`: drop the
    subscript, then drop any dotted qualifier.
    """
    return rendered.split("[", maxsplit=1)[0].rsplit(".", maxsplit=1)[-1]


def _fleet(*, definer: dict[str, str], consumer: dict[str, str]) -> dict[str, MemberSources]:
    """Two members: one defines `parse_manifest`, the other reaches for it.

    The same shape in every case below, so the only thing that varies between
    the success and the failure case is whether a source parses.
    """
    return {
        "alpha": MemberSources(
            defining={Path(path): text for path, text in definer.items()},
            consuming={Path(path): text for path, text in definer.items()},
        ),
        "beta": MemberSources(
            defining={},
            consuming={Path(path): text for path, text in consumer.items()},
        ),
    }


def test_the_consumption_measurement_is_railway_typed() -> None:
    """THE CONVERSION ITSELF: the public answer may not be a bare value.

    `checks/public_api_result_typed` reads a function as on the railway when its
    return annotation's terminal name is `Result` or `IOResult`. That check is a
    NO-OP in this repository — `pure_trees` is declared `not_applicable` — so
    nothing mechanical here would notice a regression to the bare
    `ConsumptionGraph` this used to return. This is the arming that stands in
    for it until the scan universe is.
    """
    rendered = str(cross_member_consumption.__annotations__["return"])

    assert _terminal_return_name(rendered=rendered) in _RAILWAY_RETURN_NAMES, (
        f"cross_member_consumption must return a Result/IOResult so the unparsed census "
        f"has a track to ride; got the bare annotation {rendered!r}"
    )


def test_a_fleet_whose_sources_all_parse_is_a_success_carrying_the_graph() -> None:
    """The whole measurement, which must not share a spelling with a partial one."""
    outcome = cross_member_consumption(
        members=_fleet(definer={_LIBRARY: _LIBRARY_SOURCE}, consumer={_CONSUMER: _CONSUMER_SOURCE})
    )

    assert isinstance(outcome, Success)
    graph = outcome.unwrap()
    assert graph.unparsed == ()
    assert [(edge.defining_member, edge.function) for edge in graph.edges] == [
        ("alpha", "parse_manifest")
    ]


def test_a_source_that_will_not_parse_puts_the_measurement_on_the_failure_track() -> None:
    """The partial measurement, named as one rather than answering as a whole.

    The fixture is the success case with ONE file added, so the assertion
    discriminates: the same fleet, the same edge, and the only difference is a
    file `ast.parse` refuses.
    """
    outcome = cross_member_consumption(
        members=_fleet(
            definer={_LIBRARY: _LIBRARY_SOURCE, _BROKEN: _BROKEN_SOURCE},
            consumer={_CONSUMER: _CONSUMER_SOURCE},
        )
    )

    assert isinstance(outcome, Failure)
    assert [(item.member, item.file.as_posix()) for item in outcome.failure().graph.unparsed] == [
        ("alpha", _BROKEN),
        ("alpha", _BROKEN),
    ]


def test_the_failure_track_still_carries_every_edge_the_readable_files_yielded() -> None:
    """One invalid file must not kill a nine-member sweep.

    The pre-conversion contract that the railway must NOT quietly repeal: the
    graph rides ON the failure, so a row consuming it keeps measuring the eight
    members whose sources were fine. A `Failure` carrying nothing would be the
    raise-through-the-sweep shape `livespec-dev-tooling-9sl0` removed, arriving
    by a different door.
    """
    outcome = cross_member_consumption(
        members=_fleet(
            definer={_LIBRARY: _LIBRARY_SOURCE, _BROKEN: _BROKEN_SOURCE},
            consumer={_CONSUMER: _CONSUMER_SOURCE},
        )
    )

    assert isinstance(outcome, Failure)
    assert [(edge.defining_member, edge.function) for edge in outcome.failure().graph.edges] == [
        ("alpha", "parse_manifest")
    ]
