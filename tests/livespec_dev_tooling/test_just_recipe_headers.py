"""Outside-in test for `livespec_dev_tooling/just_recipe_headers.py`.

The single-sourced answer to "does this justfile already claim `<name>`?", now
consumed by all three surfaces that used to carry their own copy of the regex:
the bump-pin append guard (`cross_repo/_canonical_reconcile_parse`), the
anti-fork body lookup (`checks/canonical_recipe_fidelity`), and the reconcile
suite's `_header_count` helper.

Per form, the behavior this suite pins (each verified against real `just`
1.36.0 by the review that filed `livespec-dev-tooling-74a`):

- bare / parameterized / dependency-carrying headers are definitions;
- `@check-foo:` (the quiet prefix) is a definition — missing it made a bump
  append a bare duplicate, which `just` rejects as "Recipe redefined";
- `alias check-foo := other` CLAIMS the name (appending beside it is "Alias
  redefined as a recipe") without defining a recipe;
- `check-foo := "x"` is a VARIABLE ASSIGNMENT and claims nothing — reading it
  as a definition suppressed the recipe append and left the consumer with a
  wired target and an "unknown recipe" at runtime;
- the prefix-collision guard: `check-foo-bar:` is not `check-foo`.

The module is imported through `importlib` inside each test, behind an
assertion that its file exists, so the pre-implementation Red is a genuine
assertion failure rather than a collection error.

Coverage target: 100% line + branch of `just_recipe_headers.py`.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from types import ModuleType

__all__: list[str] = []


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "livespec_dev_tooling" / "just_recipe_headers.py"


def _recognizer() -> ModuleType:
    """Import the shared recognizer, asserting first that its module file exists."""
    assert _MODULE_PATH.is_file(), (
        "the single-sourced recipe-header recognizer must live at "
        "livespec_dev_tooling/just_recipe_headers.py"
    )
    return importlib.import_module("livespec_dev_tooling.just_recipe_headers")


def test_bare_header_is_present_and_counted_once() -> None:
    """The plain `check-foo:` definition is present, counted once, and offers a body."""
    module = _recognizer()
    text = "check-foo:\n    uv run python -m livespec_dev_tooling.checks.foo\n"
    assert module.recipe_header_present(justfile_text=text, name="check-foo") is True
    assert module.recipe_header_count(justfile_text=text, name="check-foo") == 1
    assert module.recipe_body_offset(justfile_text=text, name="check-foo") is not None


def test_parameterized_and_dependency_header_forms_are_definitions() -> None:
    """Parameter lists and dependency lists on the header are still definitions.

    `check-red-green-replay *args:` is the exact form both Driver repos
    hand-define; a recognizer blind to it re-appends the recipe.
    """
    module = _recognizer()
    for header in (
        "check-foo *args:",
        "check-foo msg_path:",
        'check-foo p="x":',
        "check-foo: check-bar",
    ):
        text = f"{header}\n    echo body\n"
        assert (
            module.recipe_header_count(justfile_text=text, name="check-foo") == 1
        ), f"{header!r} is a recipe definition"


def test_quiet_prefixed_header_is_recognized() -> None:
    """`@check-foo:` — just's per-recipe echo suppression — is a definition.

    The residual gap the single-sourcing closes: unrecognized, a bump appends a
    bare `check-foo:` beside it and `just` refuses the file with
    "Recipe redefined".
    """
    module = _recognizer()
    text = "@check-foo:\n    uv run python -m livespec_dev_tooling.checks.foo\n"
    assert module.recipe_header_present(justfile_text=text, name="check-foo") is True
    assert module.recipe_header_count(justfile_text=text, name="check-foo") == 1
    offset = module.recipe_body_offset(justfile_text=text, name="check-foo")
    assert offset is not None
    assert text[:offset] == "@check-foo:"


def test_alias_claims_the_name_without_defining_a_recipe() -> None:
    """An alias takes the name (so nothing may be appended) but defines no recipe.

    `just` rejects a recipe appended beside an alias of the same name with
    "Alias redefined as a recipe", so the append guard must see the name as
    taken. The fidelity gate asks a different question — is there a canonical
    recipe BODY — and for an alias the honest answer is still no.
    """
    module = _recognizer()
    text = "check-other:\n    echo hi\n\nalias check-foo := check-other\n"
    assert module.recipe_header_present(justfile_text=text, name="check-foo") is True
    assert module.recipe_header_count(justfile_text=text, name="check-foo") == 0
    assert module.recipe_body_offset(justfile_text=text, name="check-foo") is None


def test_alias_target_name_is_not_claimed_by_the_alias() -> None:
    """`alias other := check-foo` claims `other`, leaving `check-foo` unclaimed."""
    module = _recognizer()
    text = "alias other := check-foo\n"
    assert module.recipe_header_present(justfile_text=text, name="check-foo") is False


def test_variable_assignment_is_not_a_recipe_definition() -> None:
    """`check-foo := "x"` is a variable, not a recipe, even when its value holds a colon.

    The false match this closes wired the target and skipped the append, so
    `just check-foo` died on "unknown recipe". Variables and recipes are
    separate namespaces, so the assignment is no reason to withhold the recipe.
    """
    module = _recognizer()
    for assignment in ('check-foo := "x"', 'check-foo:="x"', 'check-foo := "a:b"'):
        text = f"{assignment}\n\ncheck-bar:\n    echo hi\n"
        assert (
            module.recipe_header_present(justfile_text=text, name="check-foo") is False
        ), f"{assignment!r} claims nothing"
        assert module.recipe_header_count(justfile_text=text, name="check-foo") == 0
        assert module.recipe_body_offset(justfile_text=text, name="check-foo") is None


def test_prefix_collision_does_not_match_a_longer_name() -> None:
    """A `check-foo` lookup does not match a `check-foo-bar:` header."""
    module = _recognizer()
    text = "check-foo-bar:\n    echo hi\n"
    assert module.recipe_header_present(justfile_text=text, name="check-foo") is False
    assert module.recipe_header_count(justfile_text=text, name="check-foo") == 0


def test_indented_line_is_not_a_recipe_header() -> None:
    """A recipe header sits at column 0; an indented body line naming it is not one."""
    module = _recognizer()
    text = "check:\n    just check-foo\n"
    assert module.recipe_header_present(justfile_text=text, name="check-foo") is False


def test_duplicate_definitions_are_counted_across_forms() -> None:
    """Two definitions — one quiet, one bare — count as two, the redefinition signal."""
    module = _recognizer()
    text = "@check-foo:\n    echo one\n\ncheck-foo:\n    echo two\n"
    assert module.recipe_header_count(justfile_text=text, name="check-foo") == 2


def test_body_offset_lands_just_past_the_header_colon() -> None:
    """The offset skips the header's `:` and leaves its dependency remainder in place."""
    module = _recognizer()
    text = "check-foo *args: check-bar\n    echo body\n"
    offset = module.recipe_body_offset(justfile_text=text, name="check-foo")
    assert offset is not None
    assert text[offset:] == " check-bar\n    echo body\n"
