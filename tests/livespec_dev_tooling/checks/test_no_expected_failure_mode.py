"""Unit test for `checks/_no_expected_failure_mode.py` — livespec v179 member 1.

Fixture-driven on purpose. `check-public-api-result-typed` still scans ZERO
files in this repo (it is `pure_trees`-scoped), so nothing here is exercised by
a `just check` run and a green aggregate is NOT evidence any of it works.

Two of these tests exist because they caught a real defect while the analysis
was being written, and both are recorded as such rather than as coverage:

- `test_an_x_or_none_return_is_disqualified_despite_a_total_body` — `ast.unparse`
  renders a union WITH SPACES (`str | None`), so an unstripped membership test
  missed EVERY `X | None` return. The clause silently exempted the exact shape
  it exists to refuse, which would also have made member 2's declaration key
  unnecessary.
- `test_a_callee_that_reaches_io_disqualifies_its_caller` — clause (d) is the
  whole reason this member is computed rather than declared, and a body-only
  implementation passes every other test in this file.
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


def test_a_total_function_has_no_expected_failure_mode() -> None:
    """Plain value in, plain value out: no raise, no try, no I/O, no `X | None`."""
    assert (_A, "add") in _exempt(sources={_A: "def add(*, n: int) -> int:\n    return n + 1\n"})


def test_a_raise_disqualifies() -> None:
    """Clause (a). A raise disqualifies whatever the raise MEANS.

    v179 exempts nothing that raises — domain-meaningful, a framework protocol,
    or a report of a caller's wiring bug alike.
    """
    source = "def f(*, n: int) -> int:\n    if n < 0:\n        raise ValueError(n)\n    return n\n"
    assert (_A, "f") not in _exempt(sources={_A: source})


def test_a_try_disqualifies() -> None:
    """Clause (b). A `try` is a seam handling an expected failure."""
    source = "def f(*, n: int) -> int:\n    try:\n        return n\n    finally:\n        pass\n"
    assert (_A, "f") not in _exempt(sources={_A: source})


def test_an_io_module_call_disqualifies() -> None:
    """Clause (c) with a RESOLVED receiver: `os.environ.get` is I/O because `os` is."""
    source = "import os\n\n\ndef f() -> str:\n    return os.environ.get('X') or ''\n"
    assert (_A, "f") not in _exempt(sources={_A: source})


def test_a_mapping_get_on_a_local_is_not_io() -> None:
    """`settings.get(...)` is NOT I/O — the receiver is a parameter, not a module.

    A terminal-name match once flagged ten total functions as touching I/O and
    only three were real; most hits were exactly this shape. `get` is not an
    I/O verb, and this is the test that keeps it from becoming one.
    """
    source = "def f(*, settings: dict[str, str]) -> str:\n    return settings.get('k') or ''\n"
    assert (_A, "f") in _exempt(sources={_A: source})


def test_a_method_call_on_an_injected_seam_is_not_io() -> None:
    """`runner.run(...)` on a parameter is a SEAM, not a boundary.

    This fleet injects its I/O so it can be tested hermetically, and the same
    distinction convicted `fetch_manifest` under clause (e) rather than clause
    (c). Reading an injected seam as a boundary would disqualify the pattern the
    railway is composed with.
    """
    source = "def f(*, runner: object) -> int:\n    return runner.run(args=[])\n"
    assert (_A, "f") in _exempt(sources={_A: source})


def test_an_unresolvable_callee_disqualifies() -> None:
    """Doubt disqualifies: a parameter holding a callable is not resolvable.

    The analysis's own failure mode must be to DEMAND a `Result` that was not
    needed, never to excuse one that was.
    """
    source = "def f(*, make: object) -> int:\n    return make()\n"
    assert (_A, "f") not in _exempt(sources={_A: source})


def test_an_x_or_none_return_is_disqualified_despite_a_total_body() -> None:
    """Clause (e) refuses the SHAPE, without asking what the `None` means.

    Whether a `None` models a failure or a legitimate absence is a semantic
    question no AST can answer, so the syntactic member refuses the whole shape
    — and member 2's declaration key is what relieves that, narrowly.

    Both spellings are asserted because `ast.unparse` renders the union WITH
    SPACES; a membership test that forgot to strip missed every one of them and
    exempted the exact shape this clause exists to refuse.
    """
    sources = {
        _A: "def piped(*, s: str) -> str | None:\n    return s or None\n",
        _B: "from typing import Optional\n\n\ndef legacy(*, s: str) -> Optional[str]:\n    return s or None\n",
    }
    exempt = _exempt(sources=sources)
    assert (_A, "piped") not in exempt and (_B, "legacy") not in exempt


def test_a_callee_that_reaches_io_disqualifies_its_caller() -> None:
    """CLAUSE (d), the whole point: the caller's OWN body is clean.

    `outer` has no raise, no try, no I/O and no `X | None`. A body-only reading
    calls it total — which is exactly what an experienced hand reading did to
    `classify_role_key_declarations`, and what this repo's own ledger did to
    `canonical_check_slugs`. Only the fixpoint sees the walk one call away.
    """
    sources = {
        _A: "import pkgutil\n\n\ndef walks() -> list[str]:\n    return [m.name for m in pkgutil.iter_modules(['x'])]\n",
        _B: "from pkg.a import walks\n\n\ndef outer() -> int:\n    return len(walks())\n",
    }
    exempt = _exempt(sources=sources)
    assert (_A, "walks") not in exempt and (_B, "outer") not in exempt


def test_disqualification_propagates_transitively() -> None:
    """The fixpoint is a FIXPOINT, not one hop.

    A two-hop chain is the shortest case a single-pass implementation gets
    wrong, and `world_gate_check_slugs -> canonical_check_slugs ->
    _discover_slugs` is exactly that chain in this repo.
    """
    sources = {
        _A: (
            "import pkgutil\n\n\n"
            "def walks() -> list[str]:\n    return [m.name for m in pkgutil.iter_modules(['x'])]\n\n\n"
            "def middle() -> int:\n    return len(walks())\n\n\n"
            "def outer() -> int:\n    return middle()\n"
        ),
    }
    assert (_A, "outer") not in _exempt(sources=sources)


def test_a_callee_returning_x_or_none_does_not_disqualify_its_caller() -> None:
    """Clause (d) propagates (a)-(d), NOT (e) — the ratified text says so.

    An `X | None` return is a hand-rolled failure track a function exposes to
    ITS callers; it does not infect a caller that handles the `None`. Reading
    "(a)-(d)" as "(a)-(e)" would disqualify `denotes_same_release` for calling
    `tag_version_component`, whose `None` is a declared legitimate absence.
    """
    sources = {
        _A: "def maybe(*, s: str) -> str | None:\n    return s or None\n",
        _B: "from pkg.a import maybe\n\n\ndef caller(*, s: str) -> bool:\n    return maybe(s=s) is not None\n",
    }
    exempt = _exempt(sources=sources)
    assert (_A, "maybe") not in exempt and (_B, "caller") in exempt


def test_a_declared_io_tree_module_is_an_io_boundary() -> None:
    """Clause (c)'s FIRST limb: a module under the consumer's declared `io_trees`."""
    sources = {
        Path("pkg/io/reader.py"): "def read_it() -> str:\n    return ''\n",
        _B: "from pkg.io.reader import read_it\n\n\ndef caller() -> str:\n    return read_it()\n",
    }
    exempt = functions_without_expected_failure_mode(sources=sources, io_trees=(Path("pkg/io"),))
    assert (_B, "caller") not in exempt
