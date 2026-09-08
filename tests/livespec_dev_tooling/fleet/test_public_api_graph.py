"""Tests for `livespec_dev_tooling/fleet/_public_api_graph.py`.

Pure: the graph takes source TEXT, so every case here is a few lines of Python
in a dict rather than a tree on disk. The fixtures are shaped after the real
fleet edges — `parse_manifest` consumed by a sibling's hook, `cli_e2e`
consumed by a sibling's test tree — because those are the two v178 forms this
module exists to see, and a synthetic `foo`/`bar` pair would not show that the
asymmetric universes are doing anything.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path

from livespec_dev_tooling.fleet._public_api_graph import (
    MemberSources,
    cross_member_consumption,
)

__all__: list[str] = []


def sources(*, defining: dict[str, str], consuming: dict[str, str]) -> MemberSources:
    """`MemberSources` from path-string keys, so fixtures read as file trees."""
    return MemberSources(
        defining={Path(path): text for path, text in defining.items()},
        consuming={Path(path): text for path, text in consuming.items()},
    )


_LIBRARY = "livespec_dev_tooling/fleet/contract.py"
_LIBRARY_SOURCE = """
def parse_manifest(*, text: str) -> str:
    return text


class ManifestError(Exception):
    pass
"""
_HOOK = ".claude-plugin/hooks/codex_yolo_gate.py"
_HOOK_SOURCE = """
from livespec_dev_tooling.fleet.contract import parse_manifest

manifest = parse_manifest(text="x")
"""


def test_a_sibling_import_is_an_edge_and_a_same_member_import_is_not() -> None:
    """The dx8l shape: a hook in one member importing a library in another.

    The same-member importer in the same fixture is what makes the assertion
    mean something — a graph that emitted both would look identical on a
    one-member fixture.
    """
    graph = cross_member_consumption(
        members={
            "livespec-dev-tooling": sources(
                defining={
                    _LIBRARY: _LIBRARY_SOURCE,
                    "livespec_dev_tooling/fleet/wire.py": _HOOK_SOURCE,
                },
                consuming={
                    _LIBRARY: _LIBRARY_SOURCE,
                    "livespec_dev_tooling/fleet/wire.py": _HOOK_SOURCE,
                },
            ),
            "livespec-orchestrator-beads-fabro": sources(
                defining={_HOOK: _HOOK_SOURCE}, consuming={_HOOK: _HOOK_SOURCE}
            ),
        }
    )
    assert graph.unparsed == ()
    assert [
        (edge.defining_member, edge.function, edge.consuming_member, edge.consuming_file.as_posix())
        for edge in graph.edges
    ] == [
        (
            "livespec-dev-tooling",
            "parse_manifest",
            "livespec-orchestrator-beads-fabro",
            _HOOK,
        )
    ]
    assert graph.edges[0].defining_file == Path(_LIBRARY)
    assert graph.edges[0].uniquely_resolved


def test_an_import_resolves_to_its_defining_module_never_to_a_homonym() -> None:
    """The measured defect: two `fetch_manifest`s, and only one is consumed.

    A bare-name oracle scored BOTH public here and manufactured work against
    the one with zero consumers.
    """
    body = "def fetch_manifest() -> int:\n    return 1\n"
    graph = cross_member_consumption(
        members={
            "alpha": sources(
                defining={
                    "pkg/merged_branch_sweep.py": body,
                    "pkg/fleet_conformance.py": body,
                },
                consuming={},
            ),
            "beta": sources(
                defining={},
                consuming={
                    "app.py": "from pkg.fleet_conformance import fetch_manifest\n",
                },
            ),
        }
    )
    assert [edge.defining_file.as_posix() for edge in graph.edges] == ["pkg/fleet_conformance.py"]


def test_a_cross_repo_test_tree_import_is_a_consumption_but_a_same_repo_one_is_not() -> None:
    """v178 form 2. The consuming universe includes test trees; defining does not."""
    harness = "def assert_coverage(*, path: str) -> None:\n    return None\n"
    consumer = "from livespec_dev_tooling.testing.cli_e2e import assert_coverage\n"
    graph = cross_member_consumption(
        members={
            "livespec-dev-tooling": sources(
                defining={"livespec_dev_tooling/testing/cli_e2e.py": harness},
                consuming={
                    "livespec_dev_tooling/testing/cli_e2e.py": harness,
                    "tests/test_cli_e2e.py": consumer,
                },
            ),
            "livespec-driver-codex": sources(
                defining={}, consuming={"tests/e2e-cli/test_cli_e2e.py": consumer}
            ),
        }
    )
    assert [edge.consuming_member for edge in graph.edges] == ["livespec-driver-codex"]
    assert graph.edges[0].function == "assert_coverage"


def test_a_function_reached_through_a_module_alias_is_an_edge() -> None:
    graph = cross_member_consumption(
        members={
            "alpha": sources(
                defining={"pkg/mod.py": "def compute() -> int:\n    return 1\n"}, consuming={}
            ),
            "beta": sources(
                defining={},
                consuming={"app.py": "import pkg.mod\n\nvalue = pkg.mod.compute()\n"},
            ),
        }
    )
    assert [(edge.defining_member, edge.function) for edge in graph.edges] == [("alpha", "compute")]


def test_a_name_that_is_not_a_top_level_function_is_not_an_edge() -> None:
    """The Result-return rule reaches top-level FUNCTIONS; classes and constants are not.

    The function travels in the SAME import statement as the two non-functions,
    so the assertion discriminates: a graph that emitted nothing and a graph
    that emitted everything both fail it.
    """
    graph = cross_member_consumption(
        members={
            "alpha": sources(
                defining={
                    "pkg/mod.py": (
                        "class Widget:\n    pass\n\n\nVALUE = 1\n\n\n"
                        "def compute() -> int:\n    return 1\n"
                    )
                },
                consuming={},
            ),
            "beta": sources(
                defining={}, consuming={"app.py": "from pkg.mod import VALUE, Widget, compute\n"}
            ),
        }
    )
    assert [edge.function for edge in graph.edges] == ["compute"]


def test_an_underscore_prefixed_function_is_never_an_edge() -> None:
    """v178 clause 0 keeps the `_`-prefix disqualifier, whoever imports it.

    Measured on the real fleet before this was applied: `_check_segment` and
    `_decision` were reported as undeclared public surface across seven
    members.
    """
    graph = cross_member_consumption(
        members={
            "alpha": sources(
                defining={
                    "pkg/mod.py": (
                        "def _helper() -> int:\n    return 1\n\n\n"
                        "def compute() -> int:\n    return _helper()\n"
                    )
                },
                consuming={},
            ),
            "beta": sources(
                defining={}, consuming={"app.py": "from pkg.mod import _helper, compute\n"}
            ),
        }
    )
    assert [edge.function for edge in graph.edges] == ["compute"]


def test_an_import_the_consuming_member_satisfies_itself_crosses_no_boundary() -> None:
    """Installed foreign content: the consumer imports ITS OWN byte-identical copy.

    `.claude/hooks/livespec_footgun_guard.py` ships into most members, and
    `livespec-driver-codex` does `import livespec_footgun_guard` after a
    `sys.path` insert pointing at its own. Python resolves that to the copy on
    the path. Measured: without this rule, that ONE file produced 14 false
    findings across 7 members.
    """
    body = "def main() -> int:\n    return 0\n"
    consumer = "import livespec_footgun_guard\n\nlivespec_footgun_guard.main()\n"
    shared = {"hooks/livespec_footgun_guard.py": body}
    graph = cross_member_consumption(
        members={
            "alpha": sources(defining=shared, consuming=shared),
            "beta": sources(defining=shared, consuming=shared),
            "codex": sources(defining=shared, consuming={**shared, "tests/test_hook.py": consumer}),
        }
    )
    assert graph.edges == ()


def test_the_same_import_is_an_edge_when_the_consumer_ships_no_copy() -> None:
    """The control for the rule above: without a local copy, nothing resolves locally."""
    body = "def main() -> int:\n    return 0\n"
    consumer = "import livespec_footgun_guard\n\nlivespec_footgun_guard.main()\n"
    graph = cross_member_consumption(
        members={
            "alpha": sources(defining={"hooks/livespec_footgun_guard.py": body}, consuming={}),
            "codex": sources(defining={}, consuming={"tests/test_hook.py": consumer}),
        }
    )
    assert [(edge.defining_member, edge.function) for edge in graph.edges] == [("alpha", "main")]


def test_an_ambiguous_suffix_yields_every_candidate_and_says_it_is_ambiguous() -> None:
    """Doubt resolves toward MORE enforcement — and the edge admits the doubt.

    Two members define `pkg/util.py`. An importer of `pkg.util` cannot be
    resolved to one of them from source alone, so both are reported, and a row
    that failed a member on such an edge must be able to say which are which.
    """
    body = "def helper() -> int:\n    return 1\n"
    graph = cross_member_consumption(
        members={
            "alpha": sources(defining={"pkg/util.py": body}, consuming={}),
            "beta": sources(defining={"pkg/util.py": body}, consuming={}),
            "gamma": sources(defining={}, consuming={"app.py": "from pkg.util import helper\n"}),
        }
    )
    assert [edge.defining_member for edge in graph.edges] == ["alpha", "beta"]
    assert not any(edge.uniquely_resolved for edge in graph.edges)


def test_a_source_that_will_not_parse_is_named_rather_than_raised_or_dropped() -> None:
    """One invalid file must not kill a nine-member sweep, and must not vanish.

    Both sides are covered: an unparsed DEFINING file contributes no functions
    and an unparsed CONSUMING file contributes no imports, so either one
    shrinks the graph. A shrunken graph that says nothing reads as "the fleet
    is clean" — the exact summary shape this epic exists to remove.
    """
    graph = cross_member_consumption(
        members={
            "alpha": sources(
                defining={
                    "pkg/broken.py": "def (:\n",
                    "pkg/mod.py": "def compute() -> int:\n    return 1\n",
                },
                consuming={"pkg/broken.py": "def (:\n"},
            ),
            "beta": sources(
                defining={},
                consuming={
                    "app.py": "from pkg.mod import compute\n",
                    "also_broken.py": "class ??\n",
                },
            ),
        }
    )
    assert [(item.member, item.file.as_posix()) for item in graph.unparsed] == [
        ("alpha", "pkg/broken.py"),
        ("alpha", "pkg/broken.py"),
        ("beta", "also_broken.py"),
    ]
    assert [edge.function for edge in graph.edges] == ["compute"]


def test_edges_are_ordered_so_a_rows_output_does_not_churn() -> None:
    body = "def helper() -> int:\n    return 1\n"
    consumer = "from pkg.zeta import helper\nfrom pkg.alpha import helper as other\n"
    graph = cross_member_consumption(
        members={
            "zulu": sources(defining={"pkg/zeta.py": body, "pkg/alpha.py": body}, consuming={}),
            "beta": sources(defining={}, consuming={"app.py": consumer}),
        }
    )
    assert [edge.defining_file.as_posix() for edge in graph.edges] == [
        "pkg/alpha.py",
        "pkg/zeta.py",
    ]


_DISCOVERY = "livespec_dev_tooling/testing/_cli_e2e_discovery.py"
_DISCOVERY_SOURCE = """
def discover_fixtures(*, fixtures_root: str) -> str:
    return fixtures_root
"""
_FACADE = "livespec_dev_tooling/testing/cli_e2e.py"
_FACADE_SOURCE = """
from livespec_dev_tooling.testing._cli_e2e_discovery import discover_fixtures

__all__: list[str] = ["discover_fixtures", "run_round_trip"]


def run_round_trip(*, root: str) -> str:
    return root
"""
_E2E = "tests/e2e-cli/test_cli_e2e.py"
_E2E_SOURCE = """
from livespec_dev_tooling.testing import cli_e2e

fixtures = cli_e2e.discover_fixtures(fixtures_root="x")
"""


def test_a_reexported_function_is_an_edge_against_the_module_that_defines_it() -> None:
    """The measured blind spot: a re-export made a real consumption vanish.

    Four siblings reach `_cli_e2e_discovery.discover_fixtures` as
    `cli_e2e.discover_fixtures`, and the graph emitted NO edge — the reach
    resolved to `cli_e2e.py`, the name was not DEFINED there, and it was
    dropped with no second resolution to the module that does define it. The
    `run_round_trip` reach in the same fixture is the discriminator: it IS
    defined in the facade, so it was always seen, and a graph that still only
    reports that one has not been fixed.
    """
    graph = cross_member_consumption(
        members={
            "livespec-dev-tooling": sources(
                defining={_DISCOVERY: _DISCOVERY_SOURCE, _FACADE: _FACADE_SOURCE},
                consuming={_DISCOVERY: _DISCOVERY_SOURCE, _FACADE: _FACADE_SOURCE},
            ),
            "livespec-driver-codex": sources(
                defining={},
                consuming={_E2E: _E2E_SOURCE + "\nround_trip = cli_e2e.run_round_trip(root='r')\n"},
            ),
        }
    )
    assert graph.unparsed == ()
    assert [
        (edge.defining_file.as_posix(), edge.function, edge.uniquely_resolved)
        for edge in graph.edges
    ] == [
        (_DISCOVERY, "discover_fixtures", True),
        (_FACADE, "run_round_trip", True),
    ]


def test_a_reexport_the_consuming_member_satisfies_itself_still_crosses_no_boundary() -> None:
    """Following a re-export must not defeat the local-copy guard.

    The guard that stops an installed foreign copy producing a false edge is
    applied to the reach's FIRST resolution. A hop that re-resolves elsewhere
    must not smuggle the consumer's own copy back in as a cross-member edge.
    """
    graph = cross_member_consumption(
        members={
            "livespec-dev-tooling": sources(
                defining={_DISCOVERY: _DISCOVERY_SOURCE, _FACADE: _FACADE_SOURCE},
                consuming={_DISCOVERY: _DISCOVERY_SOURCE, _FACADE: _FACADE_SOURCE},
            ),
            "livespec-driver-codex": sources(
                defining={_DISCOVERY: _DISCOVERY_SOURCE, _FACADE: _FACADE_SOURCE},
                consuming={_E2E: _E2E_SOURCE},
            ),
        }
    )
    assert graph.edges == ()


def test_a_reexport_cycle_terminates_and_emits_nothing() -> None:
    """Two facades re-exporting each other, and neither defines the name.

    A naive follow-the-re-export walk recurses forever here. It must
    terminate, and it must not invent an edge against a module that only
    forwards the name.
    """
    left = "from pkg.right import spin\n"
    right = "from pkg.left import spin\n"
    graph = cross_member_consumption(
        members={
            "zulu": sources(
                defining={"pkg/left.py": left, "pkg/right.py": right},
                consuming={"pkg/left.py": left, "pkg/right.py": right},
            ),
            "beta": sources(defining={}, consuming={"app.py": "from pkg.left import spin\n"}),
        }
    )
    assert graph.edges == ()


_MODULE = "pkg/mod.py"
_STILL_DEFINES = "def compute() -> int:\n    return 1\n"
_DELETED = "def other() -> int:\n    return 2\n"
_IMPORTS_COMPUTE = "from pkg.mod import compute\n\nvalue = compute()\n"


def test_a_deleted_function_a_sibling_still_imports_is_a_record_not_an_absent_edge() -> None:
    """The 9s2j defect: the edge VANISHED instead of convicting.

    `alpha` keeps `pkg/mod.py` and deletes `compute` from it; `beta` still
    imports `compute` from it. An edge is built only where an import RESOLVES
    to a defining file, so the reach produced NOTHING — silence in the case
    that breaks the consumer hardest, since this is an `ImportError` in `beta`
    at runtime rather than a declaration gap.

    The record rides BESIDE the edges, which the first assertion states as a
    fact about the graph's shape rather than leaving to an attribute access:
    the collection has to exist for a row to be able to report it.
    """
    graph = cross_member_consumption(
        members={
            "alpha": sources(defining={_MODULE: _DELETED}, consuming={_MODULE: _DELETED}),
            "beta": sources(defining={}, consuming={"app.py": _IMPORTS_COMPUTE}),
        }
    )
    assert "unresolved" in {field.name for field in fields(graph)}
    assert graph.edges == ()
    assert [
        (
            record.consuming_member,
            record.consuming_file.as_posix(),
            record.module,
            record.name,
            record.defining_members,
        )
        for record in graph.unresolved
    ] == [("beta", "app.py", "pkg.mod", "compute", ("alpha",))]


def test_the_same_fixture_yields_an_edge_and_no_record_while_the_function_is_present() -> None:
    """The discriminator: restore `compute` and the record becomes an ordinary edge.

    Without it the assertion above would also pass against a graph that emitted
    a record for every reach it saw.
    """
    graph = cross_member_consumption(
        members={
            "alpha": sources(
                defining={_MODULE: _STILL_DEFINES}, consuming={_MODULE: _STILL_DEFINES}
            ),
            "beta": sources(defining={}, consuming={"app.py": _IMPORTS_COMPUTE}),
        }
    )
    assert [(edge.defining_member, edge.function) for edge in graph.edges] == [("alpha", "compute")]
    assert graph.unresolved == ()


def test_a_name_that_is_present_but_not_a_public_function_is_neither_edge_nor_record() -> None:
    """The two outcomes must stay distinguishable, and this is the boundary.

    A class, a constant and a `_`-prefixed helper each resolve to NO defining
    file — the defining set is public top-level FUNCTIONS — so a record keyed on
    "no defining file" rather than on "no binding" would convict every
    cross-member class import as a broken consumer.
    """
    graph = cross_member_consumption(
        members={
            "alpha": sources(
                defining={
                    _MODULE: (
                        "class Widget:\n    pass\n\n\nVALUE = 1\n\n\n"
                        "def _helper() -> int:\n    return 1\n"
                    )
                },
                consuming={},
            ),
            "beta": sources(
                defining={},
                consuming={"app.py": "from pkg.mod import VALUE, Widget, _helper\n"},
            ),
        }
    )
    assert graph.edges == ()
    assert graph.unresolved == ()


def test_a_module_that_resolves_nowhere_in_the_fleet_is_neither_edge_nor_record() -> None:
    """The ordinary stdlib / third-party import, which must stay silent.

    `dataclasses` is the measured name: the first attempt at this row reported
    `dataclasses::asdict` and 1195 siblings of it against one member, every one
    read out of a gitignored virtualenv that had entered that member's
    first-party universe (`livespec-dev-tooling-xs58`).
    """
    graph = cross_member_consumption(
        members={
            "alpha": sources(defining={_MODULE: _STILL_DEFINES}, consuming={}),
            "beta": sources(
                defining={},
                consuming={"app.py": "from dataclasses import asdict\nfrom pkg.gone import lost\n"},
            ),
        }
    )
    assert graph.edges == ()
    assert graph.unresolved == ()


def test_a_stdlib_import_a_members_own_file_happens_to_answer_is_not_a_record() -> None:
    """The measured false-positive family, reproduced end-to-end on the graph.

    `suffix_index` maps every dotted suffix INCLUDING the bare last component,
    so a member's `pkg/io.py` really does answer `from io import BytesIO` — the
    candidate set is NOT empty and the emptiness fence alone does not cover it.
    Measured on the real fleet: `io`, `types` and `dataclasses` produced 40
    names across 5 members before the bare-suffix fence.
    """
    graph = cross_member_consumption(
        members={
            "alpha": sources(defining={"pkg/io.py": _STILL_DEFINES}, consuming={}),
            "beta": sources(defining={}, consuming={"app.py": "from io import BytesIO\n"}),
        }
    )
    assert graph.edges == ()
    assert graph.unresolved == ()


def test_an_attribute_reach_for_a_missing_name_is_not_a_record() -> None:
    """Only a `from <module> import <name>` reach may convict.

    `module_aliases` binds a name to a module on `from pkg import mod`, and
    every `mod.<attr>` in that file is then a reach — including an attribute of
    an INSTANCE that shares the module's name, the shape that manufactured 19
    phantom consumptions in this repo. Those reaches produce no edge today, so
    admitting them here would convert a silent drop into false ImportError
    claims about names no import statement ever mentions.
    """
    graph = cross_member_consumption(
        members={
            "alpha": sources(defining={_MODULE: _DELETED}, consuming={}),
            "beta": sources(
                defining={},
                consuming={"app.py": "import pkg.mod\n\nvalue = pkg.mod.compute()\n"},
            ),
        }
    )
    assert graph.edges == ()
    assert graph.unresolved == ()


def test_a_module_the_consuming_member_defines_itself_is_neither_edge_nor_record() -> None:
    """The PRE-HOP guard, re-asserted for the second outcome.

    Without it one byte-identical installed hook produced 14 false findings
    across 7 members. A record emitted on a path that guard would have skipped
    would reintroduce exactly that population, one deleted name at a time.
    """
    shared = {_MODULE: _DELETED}
    graph = cross_member_consumption(
        members={
            "alpha": sources(defining=shared, consuming=shared),
            "beta": sources(defining=shared, consuming={**shared, "app.py": _IMPORTS_COMPUTE}),
        }
    )
    assert graph.edges == ()
    assert graph.unresolved == ()


def test_a_reexport_hop_landing_in_the_consuming_member_is_neither_edge_nor_record() -> None:
    """The POST-HOP guard, re-asserted for the second outcome.

    `pkg/facade.py` belongs to `alpha` alone, so the pre-hop guard does not
    fire and the reach genuinely leaves `beta`. The re-export then resolves
    into a module `beta` also ships, and Python satisfies the name from
    `beta`'s own copy — so the reach is local after all, and neither outcome
    may be emitted.
    """
    facade = "from pkg.mod import compute\n\n__all__: list[str] = ['compute']\n"
    graph = cross_member_consumption(
        members={
            "alpha": sources(
                defining={_MODULE: _STILL_DEFINES, "pkg/facade.py": facade},
                consuming={_MODULE: _STILL_DEFINES, "pkg/facade.py": facade},
            ),
            "beta": sources(
                defining={_MODULE: _STILL_DEFINES},
                consuming={
                    _MODULE: _STILL_DEFINES,
                    "app.py": "from pkg.facade import compute\n",
                },
            ),
        }
    )
    assert graph.edges == ()
    assert graph.unresolved == ()
