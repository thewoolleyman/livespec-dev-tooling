"""_check_aggregate_failures — the typed failures of reading the `check:` aggregate.

Three checks read the same two things — the justfile's bare `check:`
recipe and the canonical slug set it is compared against — and each
carried the failures of that read as a bare `None` or an uncaught raise
(livespec-dev-tooling-qndn, epic 8o8e, triage rows 1-3 and 14-15).

A SEPARATE MODULE for two reasons, in order of weight:

1. `_ci_matrix_parse.py` sits at 191 LLOC against a 200 SOFT / 250 HARD
   ceiling, and the conversion adds branches to it. This is the same
   private-sibling split `_pin_walk_failure` and `_ci_matrix_parse` itself
   were born from.
2. `_ci_matrix_parse.py` and `_tool_backed_surfaces.py` carry DELIBERATELY
   DUPLICATED copies of the recipe parsers — permitted under this
   package's bounded-duplication convention, because they are mechanical
   extractors carrying no spec citation. Defining the failure types in
   either one would make the other import from a sibling it is supposed
   to be independent of; defining them TWICE would put two incompatible
   spellings of the same condition on the same failure track. A neutral
   third home does neither.

⛔ This does NOT deduplicate the parsers themselves, which is
livespec-dev-tooling-8o8e.6 and a separate decision. It shares only the
vocabulary the two copies fail in.

THE TYPE IS THE INFORMATION. These carry no `detail` string, unlike
`PinFileUnparseable`: each names exactly one condition with no free
variable to report, and the caller renders its own message. Where a
condition DOES carry a variable — which file, which parse error — the
type carries it.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__: list[str] = [
    "CanonicalOverrideFailure",
    "CanonicalOverrideUnparseable",
    "CanonicalOverrideUnreadable",
    "CheckRecipeAbsent",
    "TargetsArrayAbsent",
    "TargetsArrayFailure",
    "TargetsArrayUnterminated",
    "WorkflowFileUnreadable",
]


@dataclass(frozen=True, kw_only=True)
class CheckRecipeAbsent:
    """The justfile carries no bare `check:` recipe.

    Every caller reports this as its OWN inability — `check_recipe_not_found`,
    "cannot verify tool-backed wiring" — rather than as an ordinary answer it
    acts on, which is what earned it CONVERT over DECLARE (triage §4d-BIS: the
    test is WHOSE failure is being reported).
    """


@dataclass(frozen=True, kw_only=True)
class TargetsArrayAbsent:
    """The `check:` recipe declares no `targets=(...)` array."""


@dataclass(frozen=True, kw_only=True)
class TargetsArrayUnterminated:
    """A `targets=(...)` array opened and was never closed.

    DISTINCT FROM `TargetsArrayAbsent`, and that is the defect this
    conversion exists to fix rather than a taxonomy preference. Both
    conditions used to return the same `None`, and every caller reported
    only the first — so a justfile with an UNTERMINATED targets array was
    diagnosed as one declaring no targets array at all, sending the
    operator to add an array that is already there.
    """


TargetsArrayFailure = TargetsArrayAbsent | TargetsArrayUnterminated


@dataclass(frozen=True, kw_only=True)
class CanonicalOverrideUnreadable:
    """The `--canonical-from` override file's BYTES could not be obtained."""

    path: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class CanonicalOverrideUnparseable:
    """The override file was READ and its bytes are not JSON.

    Kept distinct from unreadable on the same ground as
    `PinFileUnparseable` vs `PinFileUnreadable`: a can't-parse is a
    definitive, reproducible property of the file's committed bytes, while
    a can't-read may be environmental and may not reproduce.
    """

    path: str
    detail: str


CanonicalOverrideFailure = CanonicalOverrideUnreadable | CanonicalOverrideUnparseable


@dataclass(frozen=True, kw_only=True)
class WorkflowFileUnreadable:
    """A workflow file the walk FOUND and could not read the BYTES of.

    An ABSENT or EMPTY `.github/workflows` directory is an ANSWER, not this —
    the ratified missing-file tolerance the pin-walker family established. Only
    failing to obtain bytes from a file the glob just listed is a failure.
    Before the conversion an unreadable workflow raised out of the check;
    reading it as "that file contributes no matrix targets" would have been
    worse, since the parent asserts CI RUNS what the justfile wires and a
    silently-skipped workflow makes a wired slug look unrun.
    """

    path: str
    detail: str
