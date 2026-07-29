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
