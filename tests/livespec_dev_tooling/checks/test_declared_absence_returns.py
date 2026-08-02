"""Unit test for `checks/_declared_absence_returns` — v179 member 2's two source bounds.

SPECIFICATION v037 section "Role keys" attaches four bounds to `total_absence_returns`.
Bound 2 (a written reason) is the loader's and is pinned in `test_config.py`;
bound 4 (a fleet-wide count) is the central-vantage row's. The two that need the
repo's SOURCE live in this module and are pinned here:

- **BOUND 1, the structural gate** — only an `X | None` annotation is declarable.
- **BOUND 3, the staleness detector** — a declaration must still resolve.

**BOTH ARE HARD FAILURES, AND THE TESTS ASSERT THE REJECTION IS REPORTED rather
than that the entry is merely un-exempted.** Silently dropping a mis-declared
entry would satisfy the letter of bound 1 while making the mis-declaration
invisible — the exact wrong reading the ratified bullet forecloses by name.
"""

from __future__ import annotations

from pathlib import Path

from livespec_dev_tooling.checks._declared_absence_returns import (
    NOT_ABSENCE_SHAPED,
    UNRESOLVED,
    declared_absence_names,
    rejected_declarations,
)
from livespec_dev_tooling.config import TotalAbsenceReturn

_ABSENCE_SOURCE = '''
def tag_part(*, tag: str) -> str | None:
    """A tag may legitimately have no version component."""
    return None


def optional_spelled(*, tag: str) -> Optional[str]:
    """The other spelling of the same shape."""
    return None


def total(*, x: int) -> int:
    raise NotImplementedError
'''


def _entry(*, file: str, function: str) -> TotalAbsenceReturn:
    return TotalAbsenceReturn(file=Path(file), function=function, reason="a legitimate absence")


def test_absence_shaped_declaration_is_accepted() -> None:
    """A declared `X | None` resolves and is put outside the rule."""
    sources = {Path("pkg/a.py"): _ABSENCE_SOURCE}
    declared = (_entry(file="pkg/a.py", function="tag_part"),)
    assert declared_absence_names(declared=declared, sources=sources) == frozenset(
        {(Path("pkg/a.py"), "tag_part")}
    )
    assert rejected_declarations(declared=declared, sources=sources) == ()


def test_optional_spelling_is_also_declarable() -> None:
    """`Optional[X]` is the same shape, so bound 1 admits it.

    Reusing member 1's `returns_x_or_none` is what makes this hold: the gate must
    admit exactly what clause (e) refuses, and clause (e) refuses both spellings.
    """
    sources = {Path("pkg/a.py"): _ABSENCE_SOURCE}
    declared = (_entry(file="pkg/a.py", function="optional_spelled"),)
    assert declared_absence_names(declared=declared, sources=sources) == frozenset(
        {(Path("pkg/a.py"), "optional_spelled")}
    )


def test_non_absence_shape_is_rejected_not_ignored() -> None:
    """BOUND 1 — declaring a non-`X | None` function REPORTS a rejection.

    The assertion that matters is the second one. A `declared_absence_names` that
    merely omits the entry would satisfy the letter of "the key reaches only
    `X | None`" while making the mis-declaration invisible, which the ratified
    bullet rules out by name: "neither silently ignored nor accepted".
    """
    sources = {Path("pkg/a.py"): _ABSENCE_SOURCE}
    declared = (_entry(file="pkg/a.py", function="total"),)
    assert declared_absence_names(declared=declared, sources=sources) == frozenset()
    rejected = rejected_declarations(declared=declared, sources=sources)
    assert [(r.entry.function, r.rejection) for r in rejected] == [("total", NOT_ABSENCE_SHAPED)]


def test_vanished_function_is_rejected_as_stale() -> None:
    """BOUND 3 — a declaration that outlived its subject fails, naming the entry."""
    sources = {Path("pkg/a.py"): _ABSENCE_SOURCE}
    declared = (_entry(file="pkg/a.py", function="deleted_long_ago"),)
    rejected = rejected_declarations(declared=declared, sources=sources)
    assert [(r.entry.function, r.rejection) for r in rejected] == [("deleted_long_ago", UNRESOLVED)]


def test_vanished_file_is_rejected_as_stale() -> None:
    """BOUND 3 — a declared file outside the universe fails rather than KeyError-ing.

    This is the shape the sibling key's detector actually caught twice on its
    first day: an entry authored from a CONSUMER's import statement, naming a
    path that never defined the function.
    """
    sources = {Path("pkg/a.py"): _ABSENCE_SOURCE}
    declared = (_entry(file="pkg/gone.py", function="tag_part"),)
    rejected = rejected_declarations(declared=declared, sources=sources)
    assert [(r.entry.function, r.rejection) for r in rejected] == [("tag_part", UNRESOLVED)]


def test_empty_declaration_exempts_nothing() -> None:
    """An absent declaration is the STRICT end of this key, not the relaxed one.

    The opposite polarity from the union role keys, where an empty value BLINDED
    the consuming check. Here empty means the rule reaches everything, so a reader
    carrying the `pure_trees = []` intuition has it backwards.
    """
    sources = {Path("pkg/a.py"): _ABSENCE_SOURCE}
    assert declared_absence_names(declared=(), sources=sources) == frozenset()
    assert rejected_declarations(declared=(), sources=sources) == ()


def test_mixed_declaration_accepts_the_valid_and_rejects_the_rest() -> None:
    """One good entry does not launder a bad one, and one bad entry does not void a good one."""
    sources = {Path("pkg/a.py"): _ABSENCE_SOURCE}
    declared = (
        _entry(file="pkg/a.py", function="tag_part"),
        _entry(file="pkg/a.py", function="total"),
        _entry(file="pkg/a.py", function="deleted_long_ago"),
    )
    assert declared_absence_names(declared=declared, sources=sources) == frozenset(
        {(Path("pkg/a.py"), "tag_part")}
    )
    assert {
        (r.entry.function, r.rejection)
        for r in rejected_declarations(declared=declared, sources=sources)
    } == {("total", NOT_ABSENCE_SHAPED), ("deleted_long_ago", UNRESOLVED)}
