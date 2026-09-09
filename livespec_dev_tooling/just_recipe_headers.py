"""just_recipe_headers — the ONE recognizer for "does this justfile claim `<name>`?".

Three surfaces used to carry their own copy of the same regex: the bump-pin
append guard (`cross_repo/_canonical_reconcile_parse.recipe_header_present`),
the anti-fork body lookup (`checks/canonical_recipe_fidelity`), and the
`_header_count` helper of the reconcile test suite. They agreed only by
coincidence of authorship, and the coincidence was LOAD-BEARING: the append
guard and the fidelity gate must answer "is this recipe already defined?"
IDENTICALLY, or a consumer can be green on the gate and still have a duplicate
recipe appended by its bump — the `just`-parse break that stranded both Driver
repos (`livespec-dev-tooling-3vq`). One definition here removes the drift risk
instead of relying on three copies staying equal.

The recognized DEFINITION forms (all verified against `just` 1.36.0):

- bare `check-foo:`;
- parameterized `check-foo *args:` / `check-foo msg_path:` / `check-foo p="x":`;
- dependency-carrying `check-foo: other-recipe`;
- QUIET-PREFIXED `@check-foo:` — `just`'s per-recipe echo suppression. The
  pre-single-sourcing regex required the name at column 0 and so missed this
  form: a bump appended a bare duplicate and `just` then refused the whole file
  with "Recipe redefined", which is the very bug class the 3vq fix closed for
  the parameterized form and left open for this one.

Beside the definitions, ONE form CLAIMS the name without defining a recipe:

- `alias check-foo := other`. Appending a `check-foo:` recipe next to it is a
  `just` parse error ("Alias redefined as a recipe"), so `recipe_header_present`
  reports the name as taken. It is not a definition, so it contributes no header
  to `recipe_header_count` and offers no body to `recipe_body_offset` — a slug
  carrying only an alias is still MISSING its canonical recipe, which is what
  the fidelity gate should say about it.

And one form deliberately NOT recognized at all:

- `check-foo := "x"`, a VARIABLE ASSIGNMENT. The pre-single-sourcing regex
  false-matched it (the `:` of `:=` completed the pattern), so a bump wired the
  target, skipped the recipe append, and left the consumer with a
  `just check-foo` that dies on "unknown recipe". Variables and recipes are
  separate namespaces in `just`, so the assignment is no obstacle to appending
  the recipe.

Every entry point takes the NAME to look up. The lookahead `(?=[ \\t:])`
requires the character after the name to be whitespace or the colon — never
`-` — so a `check-foo` lookup does NOT match a longer `check-foo-bar:` header
(the prefix-collision guard).

Pure (no I/O): text in, answer out.
"""

from __future__ import annotations

import re

__all__: list[str] = [
    "recipe_body_offset",
    "recipe_header_count",
    "recipe_header_present",
]


def _header_pattern(*, name: str) -> re.Pattern[str]:
    r"""Compile the column-0 recipe-DEFINITION header pattern for `name`.

    `^@?` admits the quiet prefix; `[^\n]*?:` spans the optional
    parameters before the terminating colon. TWO guards keep a variable
    assignment out, and both are needed: the leading negative lookahead drops a
    `name := ...` line before the header body is ever tried, and the trailing
    `(?!=)` stops a `:=` from completing a header when the assignment's VALUE
    also carries a colon (`check-foo := "a:b"`, which the leading lookahead
    already rejects, and any later `:=` on a header line, which it does not).
    """
    escaped = re.escape(name)
    return re.compile(
        rf"^(?!@?{escaped}[ \t]*:=)@?{escaped}(?=[ \t:])[^\n]*?:(?!=)",
        re.MULTILINE,
    )


def _alias_pattern(*, name: str) -> re.Pattern[str]:
    """Compile the column-0 `alias <name> := <target>` pattern for `name`.

    Only the ALIASED name is matched, never the target: `alias other :=
    check-foo` claims `other` and leaves `check-foo` free.
    """
    return re.compile(rf"^alias[ \t]+{re.escape(name)}[ \t]*:=", re.MULTILINE)


def recipe_header_count(*, justfile_text: str, name: str) -> int:
    """Count the column-0 recipe DEFINITIONS of `name` in `justfile_text`.

    A count above 1 is the `just`-parse-breaking redefinition that the bump-pin
    append guard exists to prevent, which is why the count — rather than a bare
    presence bool — is the assertion the reconcile suite makes. A count of 0
    means no definition: an alias or a variable assignment carrying the name
    contributes none (see the module docstring).
    """
    return sum(1 for _ in _header_pattern(name=name).finditer(justfile_text))


def recipe_body_offset(*, justfile_text: str, name: str) -> int | None:
    """Return the offset just past the FIRST `name` header's `:`, or None when undefined.

    The remainder of that header LINE (its dependencies) sits between the
    returned offset and the following newline, so a caller slicing a recipe
    body from here must drop the first line before reading the body proper.
    None means `name` has no recipe definition — including when only an alias
    or a variable assignment carries it.
    """
    match = _header_pattern(name=name).search(justfile_text)
    return None if match is None else match.end()


def recipe_header_present(*, justfile_text: str, name: str) -> bool:
    """Return True when `justfile_text` already CLAIMS `name`.

    Claimed means a recipe definition in ANY form OR an `alias name := ...`:
    each makes appending a fresh `name:` recipe a `just` parse error ("Recipe
    redefined" / "Alias redefined as a recipe"), and that — not "is there a
    recipe" — is the question an append guard is actually asking. A
    `name := "x"` variable assignment is NOT a claim: appending the recipe
    beside it is legal, and suppressing the append there is what leaves the
    consumer with a wired target and no recipe behind it.
    """
    return (
        _header_pattern(name=name).search(justfile_text) is not None
        or _alias_pattern(name=name).search(justfile_text) is not None
    )
