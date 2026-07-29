"""_declared_absence_returns — livespec v179 member 2, the DECLARED `X | None` absence.

Member 1 (`_no_expected_failure_mode`) refuses the whole `X | None` shape via its
clause (e), because whether a `None` models a FAILURE or a legitimate ABSENCE is
a semantic question no AST can answer. Member 2 is the narrow DECLARED relief for
that refusal: the consumer names each such function in the `total_absence_returns`
role key, with a written reason, and `public_api_result_typed` treats it as
outside the Result-return rule.

## THIS MODULE OWNS BOUNDS 1 AND 3, AND THEY ARE ONE DETECTOR

SPECIFICATION v037 §"Role keys" attaches four bounds to the key. Bound 2 (a
written reason) is the LOADER's, enforced at parse time. Bound 4 (a fleet-wide
count) is the central-vantage row's. The two that need the repo's SOURCE are
here, and they are deliberately computed together because they are the same
question asked twice:

- **BOUND 1, the STRUCTURAL GATE** — the key reaches ONLY a function annotated
  `X | None`. A declared entry naming a function of any other shape is REJECTED.
- **BOUND 3, the STALENESS DETECTOR** — a declared entry must still resolve to
  an existing top-level function of that name in that file.

**BOTH HARD-FAIL, AND NEITHER IS A WARNING.** The ratified text says so in those
words for bound 3. The reason is one key over and one day old:
`cross_repo_public_api`'s detector rejected TWO of six first-draft entries the
day it shipped, both authored from a CONSUMER's import statement without reading
the DEFINITION. Had it warned, both would have shipped.

**AND SILENTLY IGNORING A MIS-DECLARED ENTRY IS THE OTHER WRONG ANSWER, ruled out
by name in the ratified bullet.** Dropping an entry whose function is not
`X | None` would satisfy the letter of "the key reaches only `X | None`" while
making the mis-declaration invisible — a declaration that appears to do something
and does not, which is the manufactured-confidence shape this epic exists to
remove. So a rejected entry is REPORTED, not skipped.

## ⛔ THE POLARITY IS THE OPPOSITE OF ITS SIBLING KEY'S

`cross_repo_public_api` is TIGHTENING-ONLY: it can only ADD names to the rule's
scope, so an absent declaration is SAFE. This key REMOVES names, so an absent
declaration is the STRICT end and a WRONG declaration is the dangerous one. The
tightening-only argument is NOT available here and must not be carried across
because the two keys are otherwise parallel. What bounds this key is bound 1: the
declarable SET is a syntactic property of the code, recomputed every run, not the
consumer's choice.

## ONE RESIDUAL IS UNGUARDED — stated here rather than left to be discovered

If a declared function's `None` shifts meaning from ABSENCE to FAILURE while
KEEPING the `X | None` shape, nothing here fires: bound 3 catches a shape change,
not a semantic one. That is the honest cost of member 2, it is ratified as such
upstream, and it is why the key is gated to one annotation shape and required to
carry a reason a reviewer can check.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks._import_resolution import top_level_functions
from livespec_dev_tooling.checks._no_expected_failure_mode import returns_x_or_none

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from livespec_dev_tooling.config import TotalAbsenceReturn

__all__: list[str] = [
    "RejectedDeclaration",
    "declared_absence_names",
    "rejected_declarations",
]


UNRESOLVED = "no top-level function of that name in that file"
NOT_ABSENCE_SHAPED = "the function's return annotation is not of the form `X | None`"


@dataclass(frozen=True, kw_only=True)
class RejectedDeclaration:
    """One `total_absence_returns` entry the check MUST hard-fail on, and WHICH bound.

    `rejection` distinguishes bound 3 (`UNRESOLVED` — the declaration outlived
    its subject) from bound 1 (`NOT_ABSENCE_SHAPED` — the entry never qualified,
    or the function was refactored out of the shape). One detector, two named
    diagnoses, because the remedies differ: the first is a stale entry to delete,
    the second is either a mis-declaration to withdraw or a conversion now owed.
    """

    entry: TotalAbsenceReturn
    rejection: str


def _absence_shaped(*, tree: ast.Module) -> frozenset[str]:
    """Top-level function names in `tree` whose return annotation is `X | None`.

    Reuses member 1's `returns_x_or_none` rather than reading annotations a third
    time. That is not only DRY: bound 1 must gate exactly the shape clause (e)
    refuses, and two independent readers of the same annotation is how the gate
    and the clause drift apart. Member 1 already handles both spellings
    (`X | None` and `Optional[X]`) and already carries the `.strip()` that a
    space-rendering `ast.unparse` demands.
    """
    return frozenset(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and returns_x_or_none(func=node)
    )


def _split(
    *, declared: tuple[TotalAbsenceReturn, ...], sources: Mapping[Path, str]
) -> tuple[frozenset[tuple[Path, str]], tuple[RejectedDeclaration, ...]]:
    """Partition declared entries into the ones that hold and the ones that fail."""
    trees = {rel: ast.parse(source) for rel, source in sources.items()}
    functions = {rel: top_level_functions(tree=tree) for rel, tree in trees.items()}
    absence = {rel: _absence_shaped(tree=tree) for rel, tree in trees.items()}
    accepted: set[tuple[Path, str]] = set()
    rejected: list[RejectedDeclaration] = []
    for entry in declared:
        if entry.function not in functions.get(entry.file, frozenset()):
            rejected.append(RejectedDeclaration(entry=entry, rejection=UNRESOLVED))
        elif entry.function not in absence[entry.file]:
            rejected.append(RejectedDeclaration(entry=entry, rejection=NOT_ABSENCE_SHAPED))
        else:
            accepted.add((entry.file, entry.function))
    return frozenset(accepted), tuple(rejected)


def declared_absence_names(
    *, declared: tuple[TotalAbsenceReturn, ...], sources: Mapping[Path, str]
) -> frozenset[tuple[Path, str]]:
    """`(defining path, function name)` pairs v179 member 2 puts outside the rule.

    Only entries that pass BOTH bound 1 and bound 3 are returned. A rejected
    entry exempts NOTHING — it is reported by `rejected_declarations` and fails
    the check — so a mis-declaration cannot quietly buy an exemption it does not
    qualify for.
    """
    accepted, _ = _split(declared=declared, sources=sources)
    return accepted


def rejected_declarations(
    *, declared: tuple[TotalAbsenceReturn, ...], sources: Mapping[Path, str]
) -> tuple[RejectedDeclaration, ...]:
    """Declared entries that violate bound 1 or bound 3, each with its diagnosis.

    A non-empty result MUST fail the consuming check. SPECIFICATION v037 makes
    both bounds hard failures and says of bound 3, verbatim, that it "MUST NOT be
    a warning".
    """
    _, rejected = _split(declared=declared, sources=sources)
    return rejected
