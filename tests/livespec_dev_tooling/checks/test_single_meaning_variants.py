"""Unit test for `checks/_single_meaning_variants` — v183's two source-side bounds.

SPECIFICATION v038 §"Role keys" attaches four bounds to `single_meaning_variants`.
Bound 2 (a written meaning per variant) is the LOADER's and is pinned in
`test_config.py`; bound 4 (a fleet-wide count beside the functions each
declaration relieves) is the central-vantage row's. The two that need the repo's
SOURCE live in this module:

- **BOUND 1, the STRUCTURAL GATE**, four limbs, all RECOMPUTED and storing no
  claim — (a) the name resolves to a module-level closed union alias in the
  declared file; (b) every operand resolves to a first-party type; (c) every
  variant is CONSTRUCTED somewhere in the universe; (d) condition 2 holds as
  COMPUTED.
- **BOUND 3, the VARIANT-SET staleness detector** — the declared variants must
  EQUAL the union's operand set, so adding a variant BREAKS the declaration
  rather than silently inheriting it.

**EVERY REJECTION IS A HARD FAILURE AND IS REPORTED, and the tests assert the
rejection is NAMED rather than that the entry is merely un-relieved.** v183
forecloses both wrong readings by name: neither silently ignored, which would
make a mis-declaration invisible, nor accepted.

⛔ **AND THE KEY IS RELAXING-ONLY, so every test here has a polarity.** A test
that only proved relief would be satisfied by a gate that relieved everything.
Each limb therefore carries a NEGATIVE control: the same union, one limb broken,
REJECTED and relieving nothing.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.checks._single_meaning_variants import (
    CONSUMPTION_NOT_EXHAUSTIVE,
    OPERAND_FOREIGN,
    UNION_UNRESOLVED,
    VARIANT_SET_MISMATCH,
    VARIANT_UNCONSTRUCTED,
    declared_variant_names,
    rejected_variant_declarations,
)
from livespec_dev_tooling.config import SingleMeaningVariant

_UNION = '''
from dataclasses import dataclass
from typing import assert_never


@dataclass(frozen=True, kw_only=True)
class Ok:
    """It holds."""


@dataclass(frozen=True, kw_only=True)
class Bad:
    """It does not."""


Outcome = Ok | Bad


def render(*, flag: bool) -> Outcome:
    """A rendering boundary: the failure originated elsewhere."""
    return Ok() if flag else Bad()


def consume(*, outcome: Outcome) -> int:
    match outcome:
        case Ok():
            return 0
        case Bad():
            return 1
        case _:
            assert_never(outcome)
'''

_DECLARING = Path("pkg/outcome.py")


def _entry(
    *, variant: str, union: str = "Outcome", file: Path = _DECLARING
) -> SingleMeaningVariant:
    return SingleMeaningVariant(
        file=file, union=union, variant=variant, meaning=f"exactly one thing: {variant}"
    )


def _both() -> tuple[SingleMeaningVariant, ...]:
    return (_entry(variant="Ok"), _entry(variant="Bad"))


def test_declared_union_relieves_its_returning_functions() -> None:
    """The gate holds on all four limbs, so `render` leaves the rule's scope."""
    sources = {_DECLARING: _UNION}
    assert rejected_variant_declarations(declared=_both(), sources=sources) == ()
    assert declared_variant_names(declared=_both(), sources=sources, io_trees=()) == frozenset(
        {(_DECLARING, "render")}
    )


def test_absent_declaration_relieves_nothing() -> None:
    """Empty is the STRICT end of this key — v183 says so in terms."""
    sources = {_DECLARING: _UNION}
    assert declared_variant_names(declared=(), sources=sources, io_trees=()) == frozenset()
    assert rejected_variant_declarations(declared=(), sources=sources) == ()


def test_condition_1_boundary_is_not_relieved() -> None:
    """A declared-union return that calls a primitive DIRECTLY stays convicted.

    v183: "It does NOT reach condition 1." The declaration is ACCEPTED — the
    union is still declarable — and the boundary function is simply not among
    the names it relieves. Both halves are asserted, because a gate that
    rejected the whole declaration here would be a different (and wrong) rule.
    """
    source = (
        _UNION
        + '''

def reads(*, path: Path) -> Outcome:
    """Calls a filesystem primitive DIRECTLY — condition 1 FAILS."""
    return Ok() if path.read_text(encoding="utf-8") else Bad()
'''
    )
    sources = {_DECLARING: source}
    assert rejected_variant_declarations(declared=_both(), sources=sources) == ()
    assert declared_variant_names(declared=_both(), sources=sources, io_trees=()) == frozenset(
        {(_DECLARING, "render")}
    )


def test_union_absent_from_the_declared_file_is_rejected() -> None:
    """LIMB (a): the name must resolve to a module-level union alias in that file."""
    sources = {_DECLARING: _UNION}
    declared = (_entry(variant="Ok", union="Missing"), _entry(variant="Bad", union="Missing"))
    assert [
        item.rejection for item in rejected_variant_declarations(declared=declared, sources=sources)
    ] == [UNION_UNRESOLVED, UNION_UNRESOLVED]
    assert declared_variant_names(declared=declared, sources=sources, io_trees=()) == frozenset()


def test_declared_file_outside_the_universe_is_rejected() -> None:
    """LIMB (a) again: a declaration that outlived its file resolves to nothing."""
    sources = {_DECLARING: _UNION}
    declared = (_entry(variant="Ok", file=Path("pkg/gone.py")),)
    assert [
        item.rejection for item in rejected_variant_declarations(declared=declared, sources=sources)
    ] == [UNION_UNRESOLVED]


def test_non_union_alias_is_rejected() -> None:
    """LIMB (a): a single-name alias is not a union, however it is spelled."""
    sources = {_DECLARING: _UNION + "\nAlias = Ok\n"}
    declared = (_entry(variant="Ok", union="Alias"),)
    assert [
        item.rejection for item in rejected_variant_declarations(declared=declared, sources=sources)
    ] == [UNION_UNRESOLVED]


def test_foreign_operand_is_rejected() -> None:
    """LIMB (b): a union reaching a type this repo does not define is not closed here."""
    source = _UNION.replace("Outcome = Ok | Bad", "Outcome = Ok | Bad | Foreign")
    sources = {_DECLARING: source}
    declared = (*_both(), _entry(variant="Foreign"))
    assert [
        item.rejection for item in rejected_variant_declarations(declared=declared, sources=sources)
    ] == [OPERAND_FOREIGN] * 3
    assert declared_variant_names(declared=declared, sources=sources, io_trees=()) == frozenset()


def test_unconstructed_variant_is_rejected() -> None:
    """LIMB (c): a variant nothing ever produces is not inhabited and load-bearing.

    A decorative failure variant would otherwise buy the whole union its relief
    — the exact shape this epic exists to remove.
    """
    source = _UNION.replace("return Ok() if flag else Bad()", "return Ok()").replace(
        "        case Bad():\n            return 1\n", ""
    )
    sources = {_DECLARING: source}
    assert [
        item.rejection for item in rejected_variant_declarations(declared=_both(), sources=sources)
    ] == [VARIANT_UNCONSTRUCTED] * 2


def test_isinstance_consumption_is_rejected() -> None:
    """LIMB (d): an `isinstance` discrimination is refused EVEN WHERE EXHAUSTIVE.

    v183 gives the mechanical reason rather than a stylistic one:
    `check-assert-never-exhaustiveness` polices `match` statements and CANNOT
    SEE an `isinstance` chain, so a union consumed that way is governed by
    nothing and a newly-added variant falls silently through every site.
    """
    source = (
        _UNION
        + """

def chain(*, outcome: Outcome) -> int:
    if isinstance(outcome, Ok):
        return 0
    return 1
"""
    )
    sources = {_DECLARING: source}
    assert [
        item.rejection for item in rejected_variant_declarations(declared=_both(), sources=sources)
    ] == [CONSUMPTION_NOT_EXHAUSTIVE] * 2
    assert declared_variant_names(declared=_both(), sources=sources, io_trees=()) == frozenset()


def test_wildcard_case_that_does_not_call_assert_never_is_rejected() -> None:
    """LIMB (d): a `case _:` that RETURNS is not the terminator condition 2 names.

    A wildcard arm makes the `match` total to the interpreter while leaving
    `check-assert-never-exhaustiveness` unable to prove anything about a
    newly-added variant — the precise blind spot condition 2 exists to close, and
    the one a reader could mistake for compliance.
    """
    source = (
        _UNION
        + """

def swallows(*, outcome: Outcome) -> int:
    match outcome:
        case Ok():
            return 0
        case _:
            return 1
"""
    )
    sources = {_DECLARING: source}
    assert [
        item.rejection for item in rejected_variant_declarations(declared=_both(), sources=sources)
    ] == [CONSUMPTION_NOT_EXHAUSTIVE] * 2


def test_annotated_union_alias_is_read() -> None:
    """LIMB (a): `Outcome: TypeAlias = Ok | Bad` is the same declaration to a reader.

    Differing on the annotation would be a rule with two answers, the defect
    `returns_x_or_none` already records for the `X | None` shape.
    """
    source = _UNION.replace("Outcome = Ok | Bad", "Outcome: TypeAlias = Ok | Bad")
    sources = {_DECLARING: source}
    assert rejected_variant_declarations(declared=_both(), sources=sources) == ()
    assert declared_variant_names(declared=_both(), sources=sources, io_trees=()) == frozenset(
        {(_DECLARING, "render")}
    )


def test_non_exhaustive_match_consumption_is_rejected() -> None:
    """LIMB (d): a `match` over the union must terminate in `assert_never`."""
    source = (
        _UNION
        + """

def partial(*, outcome: Outcome) -> int:
    match outcome:
        case Ok():
            return 0
        case Bad():
            return 1
"""
    )
    sources = {_DECLARING: source}
    assert [
        item.rejection for item in rejected_variant_declarations(declared=_both(), sources=sources)
    ] == [CONSUMPTION_NOT_EXHAUSTIVE] * 2


def test_undeclared_variant_breaks_the_declaration() -> None:
    """BOUND 3: adding a variant BREAKS the declaration rather than inheriting it.

    Stricter than member 2's bound 3 and deliberately so: condition 3 quantifies
    over EVERY variant, so a declaration that does not enumerate them is a claim
    with an unbounded subject.
    """
    sources = {_DECLARING: _UNION}
    declared = (_entry(variant="Ok"),)
    assert [
        item.rejection for item in rejected_variant_declarations(declared=declared, sources=sources)
    ] == [VARIANT_SET_MISMATCH]
    assert declared_variant_names(declared=declared, sources=sources, io_trees=()) == frozenset()


def test_declared_variant_absent_from_the_union_breaks_the_declaration() -> None:
    """BOUND 3 the other way: a declared variant the union no longer carries."""
    sources = {_DECLARING: _UNION}
    declared = (*_both(), _entry(variant="Retired"))
    assert [
        item.rejection for item in rejected_variant_declarations(declared=declared, sources=sources)
    ] == [VARIANT_SET_MISMATCH] * 3


def test_relief_reaches_an_importing_file() -> None:
    """A union is declared ONCE and relieves returns wherever it is imported.

    The carrier is per-UNION precisely so one claim is not held in many places;
    this is the measured shape that made it so — all of this repo's offenders
    return the SAME union from many modules.
    """
    consumer = '''
from pkg.outcome import Bad, Ok, Outcome


def elsewhere(*, flag: bool) -> Outcome:
    """Returns the imported union."""
    return Ok() if flag else Bad()
'''
    sources = {_DECLARING: _UNION, Path("pkg/other.py"): consumer}
    assert declared_variant_names(declared=_both(), sources=sources, io_trees=()) == frozenset(
        {(_DECLARING, "render"), (Path("pkg/other.py"), "elsewhere")}
    )


def test_same_named_union_in_another_file_is_not_relieved() -> None:
    """A homonym union in a file that does NOT import the declared one is untouched.

    Name-matching errs toward relieving what nobody declared, and relief is the
    RELAXING direction. The resolution is through the import binding, as it is
    everywhere else in this package.
    """
    homonym = '''
from dataclasses import dataclass


@dataclass(frozen=True, kw_only=True)
class Ok:
    """A different Ok."""


@dataclass(frozen=True, kw_only=True)
class Bad:
    """A different Bad."""


Outcome = Ok | Bad


def local(*, flag: bool) -> Outcome:
    """Returns a DIFFERENT union that happens to share the name."""
    return Ok() if flag else Bad()
'''
    sources = {_DECLARING: _UNION, Path("pkg/homonym.py"): homonym}
    assert declared_variant_names(declared=_both(), sources=sources, io_trees=()) == frozenset(
        {(_DECLARING, "render")}
    )
