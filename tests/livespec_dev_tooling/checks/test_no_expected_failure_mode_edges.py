"""Edge cases of the v179 member-1 analysis, beside its main fixture file.

Split from `test_no_expected_failure_mode.py` rather than appended to it: that
file is the Red-recorded half of a Red→Green pair, and the byte-identity rule
binds it. The split is the repo's existing `*_edges.py` idiom.

Each case here is a distinct RESOLUTION path through clause (c) or (d) — the
five ways a call can be classified that the main file's fixtures do not reach.
None is coverage ceremony: every one of them decides whether a real function in
this repo is exempt.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.checks._no_expected_failure_mode import (
    functions_without_expected_failure_mode,
)

__all__: list[str] = []


_A = Path("pkg/a.py")
_B = Path("pkg/b.py")
_SHIM = Path("pkg/facade.py")


def _exempt(*, sources: dict[Path, str]) -> frozenset[tuple[Path, str]]:
    return functions_without_expected_failure_mode(sources=sources, io_trees=())


def test_an_unannotated_return_is_not_disqualified_by_clause_e() -> None:
    """Clause (e) asks about the ANNOTATION; an absent one is not `X | None`.

    Reading a missing annotation as the union would disqualify every
    unannotated function in the fleet at once — a far larger claim than the
    clause makes, and one no ratified text supports.
    """
    assert (_A, "f") in _exempt(sources={_A: "def f(*, n):\n    return n\n"})


def test_an_io_builtin_call_disqualifies() -> None:
    """`open(...)` is an I/O boundary even though it resolves to no module."""
    source = "def f(*, name: str) -> str:\n    return open(name).name\n"
    assert (_A, "f") not in _exempt(sources={_A: source})


def test_a_bare_name_imported_from_an_io_module_disqualifies() -> None:
    """`from os import getenv` then `getenv(...)` — the BINDING carries the module.

    The call site is a bare `Name` with no receiver to resolve, so the
    classification has to come from the import that bound it. Missing this path
    would let `from os import ...` launder every environment read past
    clause (c).
    """
    source = "from os import getenv\n\n\ndef f() -> str:\n    return getenv('X') or ''\n"
    assert (_A, "f") not in _exempt(sources={_A: source})


def test_a_first_party_attribute_call_creates_a_call_edge() -> None:
    """`import pkg.a` then `pkg.a.walks()` is an EDGE, not an opaque call.

    Without the edge the fixpoint cannot see through a module-style import, and
    `world_gate_check_slugs -> canonical_check_slugs` in this repo is reached
    by exactly this spelling in other modules.
    """
    sources = {
        _A: "import pkgutil\n\n\ndef walks() -> list[str]:\n    return [m.name for m in pkgutil.iter_modules(['x'])]\n",
        _B: "import pkg.a\n\n\ndef outer() -> int:\n    return len(pkg.a.walks())\n",
    }
    assert (_B, "outer") not in _exempt(sources=sources)


def test_a_call_target_that_is_neither_a_name_nor_an_attribute_disqualifies() -> None:
    """A call on a call — `factory()()` — is unresolvable by construction.

    Doubt disqualifies, so the analysis demands a `Result` that may not have
    been needed rather than excusing one that was.
    """
    source = "def f(*, factory: object) -> int:\n    return factory()()\n"
    assert (_A, "f") not in _exempt(sources={_A: source})


def test_a_call_through_a_reexport_shim_still_reaches_the_definer() -> None:
    """A facade that re-exports a name defines nothing, so the reach must re-resolve.

    ⛔ THIS IS THE FAIL-OPEN DIRECTION, WHICH THE RATIFIED DESIGN FORECLOSES
    EVERYWHERE ELSE. `_name_call` takes the `dotted is not None` branch for ANY
    imported name and derives edges from `_first_party_edges`; when the import
    routes through a shim, the shim defines nothing, so NO edge was produced —
    and that branch never falls through to the "doubt disqualifies" arm, which
    is only reached for a name that was not imported at all. The caller was
    therefore ACQUITTED by a resolution failure.

    MEASURED in `livespec-orchestrator-beads-fabro`: three functions reaching
    disqualified callees through `commands/_dispatcher_plan.py` — a 277-line
    aggregator that re-exports `parse_run_status` from `_dispatcher_run_status`
    — escaped conviction. All three are `_`-prefixed, so closing this can only
    ADD offenders as their public callers convict through them.

    `fleet/_public_api_graph.py` carries this exact fix already
    (`_through_reexports`, worth 5 consumption edges when it landed); this
    module is the second copy that did not get it — the `i04f` shape.
    """
    sources = {
        _A: "def leaf(*, name: str) -> str:\n    return open(name).name\n",
        _SHIM: "from pkg.a import leaf\n\n__all__: list[str] = ['leaf']\n",
        _B: "from pkg.facade import leaf\n\n\ndef outer() -> str:\n    return leaf(name='x')\n",
    }
    # `leaf` is disqualified by clause (c) via the `open` builtin, so `outer`
    # must be disqualified THROUGH it by clause (d)'s fixpoint.
    assert (_A, "leaf") not in _exempt(sources=sources)
    assert (_B, "outer") not in _exempt(sources=sources)


def test_a_reexport_chain_resolves_through_more_than_one_hop() -> None:
    """caller -> facade -> aggregator -> definer, which is the real fleet shape.

    `livespec-orchestrator-beads-fabro` reaches `parse_float` as
    `commands/* -> effects/__init__.py -> effects/_attempt.py`, and a
    single-hop fix would leave every deeper chain still laundering its reach.
    """
    mid = Path("pkg/mid.py")
    sources = {
        _A: "def leaf(*, name: str) -> str:\n    return open(name).name\n",
        mid: "from pkg.a import leaf\n\n__all__: list[str] = ['leaf']\n",
        _SHIM: "from pkg.mid import leaf\n\n__all__: list[str] = ['leaf']\n",
        _B: "from pkg.facade import leaf\n\n\ndef outer() -> str:\n    return leaf(name='x')\n",
    }
    assert (_B, "outer") not in _exempt(sources=sources)


def test_a_self_referential_reexport_terminates() -> None:
    """A module importing a name from ITSELF must not spin the walk.

    A re-export cycle is a REAL shape, so the walk is bounded by a VISITED SET
    rather than a hop limit — for the reason
    `_public_api_graph._through_reexports` records: an arbitrary depth cap
    would silently stop resolving a legitimate chain, which is the fail-open
    direction wearing a safety measure's clothing.

    ⚠️ THIS TEST PASSES BOTH BEFORE AND AFTER THE FIX, AND THAT IS THE POINT —
    it is a guard on the NEW code, not a demonstration of the defect. Without
    the visited set it does not fail, it HANGS. The reach resolves to nothing
    because no module defines the name, which is the same answer the analysis
    gave before the walk existed: the walk must not turn an unresolvable name
    into an infinite loop.
    """
    loop = Path("pkg/loop.py")
    sources = {
        loop: "from pkg.loop import leaf\n\n__all__: list[str] = ['leaf']\n",
        _B: "from pkg.loop import leaf\n\n\ndef outer() -> str:\n    return leaf(name='x')\n",
    }
    assert (_B, "outer") in _exempt(sources=sources)
