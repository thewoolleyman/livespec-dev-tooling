"""Tests for `livespec_dev_tooling/fleet/_public_api_unresolved.py`.

Pure: every case is a few lines of Python in a string, because the module takes
an `ast.Module` and two mappings and reaches nothing. The cases are shaped
around the module's own fences rather than around its branches — each fence was
paid for by a measured false-positive population, so a test that only walked the
code would not say whether the fence still holds.
"""

from __future__ import annotations

import ast
from pathlib import Path

from livespec_dev_tooling.fleet._public_api_unresolved import (
    UnresolvedReach,
    bound_names,
    broken_consumer_message,
    sorted_reaches,
    unresolved_reach,
)

__all__: list[str] = []


_EVERY_BINDING_SHAPE = '''
"""A module docstring binds nothing, and must not confuse the walk."""

import os.path
import json as encoder
from typing import TYPE_CHECKING

CONSTANT = 1
ANNOTATED: int = 2
COUNTER = 0
COUNTER += 1
first, second = (1, 2)
Widget.size: int = 3


class Widget:
    pass


def compute() -> int:
    return 1


async def fetch() -> int:
    return 2


if TYPE_CHECKING:
    from collections.abc import Mapping
else:
    RUNTIME_ONLY = 3

try:
    import tomllib as loader
except ImportError:
    FALLBACK = 1
else:
    PARSED = True
finally:
    DONE = True
'''


def test_every_top_level_binding_shape_counts_as_binding_the_name() -> None:
    """The question is the RUNTIME's — does the module bind the name at all.

    A sibling legitimately imports classes, constants, aliased imports and names
    bound only inside a module-level `if TYPE_CHECKING:` or a `try/except
    ImportError` fallback. Every one of those resolves to no DEFINING file,
    because the graph's defining set is public top-level FUNCTIONS — so a walk
    that missed any of them would convict a healthy consumer.
    """
    assert bound_names(tree=ast.parse(_EVERY_BINDING_SHAPE)) == frozenset(
        {
            "os",
            "encoder",
            "TYPE_CHECKING",
            "CONSTANT",
            "ANNOTATED",
            "COUNTER",
            "first",
            "second",
            "Widget",
            "compute",
            "fetch",
            "Mapping",
            "RUNTIME_ONLY",
            "loader",
            "FALLBACK",
            "PARSED",
            "DONE",
        }
    )


def test_a_function_body_binds_nothing_at_module_level() -> None:
    """A local variable is not a module attribute.

    The walk deliberately does not descend into function or class bodies: a
    helper's local named `parse_manifest` would otherwise silence a genuine
    finding about a deleted `parse_manifest`.
    """
    source = "def compute() -> int:\n    hidden = 1\n    return hidden\n"
    assert bound_names(tree=ast.parse(source)) == frozenset({"compute"})


def _reach(
    *, name: str, bindings: dict[Path, frozenset[str]], module: str = "pkg.mod"
) -> UnresolvedReach | None:
    """`beta/app.py`'s `from <module> import <name>`, against `bindings`."""
    return unresolved_reach(
        member="beta",
        rel=Path("app.py"),
        module=module,
        name=name,
        candidates=frozenset(bindings),
        bindings=bindings,
    )


def test_a_name_no_candidate_binds_is_a_record_naming_every_member_that_answered() -> None:
    record = _reach(name="compute", bindings={Path("alpha/pkg/mod.py"): frozenset({"other"})})
    assert record == UnresolvedReach(
        consuming_member="beta",
        consuming_file=Path("app.py"),
        module="pkg.mod",
        name="compute",
        defining_members=("alpha",),
    )


def test_an_empty_candidate_set_is_never_a_record() -> None:
    """The stdlib / third-party fence, kept explicit rather than left to a caller.

    A dotted module that resolves nowhere in the fleet suffix index is an
    ordinary `import dataclasses`. The first attempt at this row carried this
    fence and still emitted 1196 findings against one member, because a
    gitignored virtualenv was inside the member's first-party universe and made
    the set NON-empty; `livespec-dev-tooling-xs58` fixed the population, which
    is what makes the fence sufficient on its own.
    """
    assert (
        unresolved_reach(
            member="beta",
            rel=Path("app.py"),
            module="dataclasses",
            name="asdict",
            candidates=frozenset(),
            bindings={},
        )
        is None
    )


def test_a_bare_top_level_suffix_is_never_a_record() -> None:
    """The measured one: `suffix_index` maps the bare last component too.

    A member's own `.../commands/io.py` answers `from io import BytesIO`, and a
    `.../test_plugin_structure.py` answers a sibling's same-repo test-helper
    import. With the other fences already in place that produced 40 names across
    5 members, every one of them false — neither file is importable under its
    bare name from another member's tree.
    """
    assert (
        _reach(name="BytesIO", module="io", bindings={Path("alpha/x/io.py"): frozenset()}) is None
    )
    assert (
        _reach(
            name="_make_claude_tree",
            module="test_plugin_structure",
            bindings={Path("alpha/x/test_plugin_structure.py"): frozenset()},
        )
        is None
    )


def test_a_dotted_stdlib_path_is_never_a_record() -> None:
    """A member's nested directories cannot shadow a package they do not sit on.

    The bare-suffix fence already removes every single-component collision. This
    one keeps a DOTTED stdlib path from becoming the next `io` the day a member
    happens to name two nested directories `collections/abc`.
    """
    assert (
        _reach(
            name="Mapping",
            module="collections.abc",
            bindings={Path("alpha/vendor/collections/abc.py"): frozenset()},
        )
        is None
    )


def test_one_binding_candidate_among_several_suppresses_the_record() -> None:
    """Ambiguity resolves toward SILENCE here, the opposite direction from an edge.

    An edge claims a name is public, so doubt toward more enforcement is safe.
    This record claims a sibling is BROKEN AT IMPORT TIME, so doubt toward less
    noise is safe — the row cannot tell which of two homonym files Python would
    actually import.
    """
    assert (
        _reach(
            name="compute",
            bindings={
                Path("alpha/pkg/mod.py"): frozenset({"other"}),
                Path("gamma/pkg/mod.py"): frozenset({"compute"}),
            },
        )
        is None
    )


def test_a_star_import_means_the_module_may_bind_anything() -> None:
    """`from x import *` hides its members from this module's own source."""
    assert _reach(name="compute", bindings={Path("alpha/pkg/mod.py"): frozenset({"*"})}) is None


def test_a_module_the_consuming_member_answers_itself_is_never_a_record() -> None:
    """The record is a CROSS-member claim; a local answer crosses no boundary."""
    assert _reach(name="compute", bindings={Path("beta/pkg/mod.py"): frozenset({"other"})}) is None


def test_records_are_ordered_so_a_rows_output_does_not_churn() -> None:
    def record(*, module: str, name: str, member: str, file: str) -> UnresolvedReach:
        return UnresolvedReach(
            consuming_member=member,
            consuming_file=Path(file),
            module=module,
            name=name,
            defining_members=("alpha",),
        )

    ordered = sorted_reaches(
        records=[
            record(module="pkg.zeta", name="a", member="beta", file="b.py"),
            record(module="pkg.alpha", name="b", member="beta", file="a.py"),
            record(module="pkg.alpha", name="b", member="beta", file="Z.py"),
        ]
    )
    assert [(item.module, item.consuming_file.as_posix()) for item in ordered] == [
        ("pkg.alpha", "Z.py"),
        ("pkg.alpha", "a.py"),
        ("pkg.zeta", "b.py"),
    ]


def test_the_message_names_every_missing_name_and_every_consuming_site() -> None:
    """One line per missing name, so an operator can fix without re-running."""
    sites = [
        UnresolvedReach(
            consuming_member=member,
            consuming_file=Path(file),
            module="pkg.mod",
            name="compute",
            defining_members=("lib",),
        )
        for member, file in (("app", "b/use.py"), ("app", "a/use.py"))
    ]
    assert broken_consumer_message(repo="lib", records=tuple(sites)) == [
        "lib: 1 name(s) a sibling IMPORTS are NO LONGER BOUND here -- a BROKEN CONSUMER "
        "(an ImportError in that sibling at runtime), NOT a declaration gap: "
        "pkg.mod::compute <- app:a/use.py, app:b/use.py."
    ]


def test_a_member_with_no_records_contributes_no_sentence() -> None:
    """A list rather than an optional string, so the row concatenates unconditionally."""
    assert broken_consumer_message(repo="lib", records=()) == []
