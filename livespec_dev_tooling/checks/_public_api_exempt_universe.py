"""_public_api_exempt_universe — the ONE assembly of the two universes `_scan` reads.

`public_api_result_typed._scan` needs two `(defining path, function name)` sets
before it can convict anything: the PUBLIC set (v178, computed plus declared) and
the EXEMPT set (v179 member 1 computed, v179 member 2 declared, v183's declared
single-meaning variants). Assembling them is FIVE reader calls — two for the
public set, three for the exempt one — whose ARGUMENT WIRING is the whole content:
which declaration key feeds which reader, and which of them also needs `io_trees`.

## ⛔ WHY THIS IS A MODULE AND NOT FOUR LINES INSIDE `_scan`

Because a SECOND caller exists, and hand-rolling the assembly for it has already
cost a measured wrong answer. The armed measurement — `_scan`'s body with the
`pure_trees` scan universe swapped for `resolve_check_universe()` and the
`_`-prefixed FILE skip dropped — is how this fleet re-derives which modules are
worth converting. Every time it has been written it has been written by COPYING
this assembly, and the copy went stale: a third `total |= …` line landed here
(v183's `declared_variant_names`) and the copy did not follow, so the re-derivation
reported `livespec-dev-tooling` at 18 offenders instead of 3. FIFTEEN phantom
offenders, from a copy that was correct on the day it was written.

The defect is not that someone copied carelessly. It is that a copy EXISTS: an
exempt set assembled twice has two answers the moment either side gains a member,
and the wrong one loses quietly — a phantom offender looks exactly like a real one.
So this module is the single implementation and both callers import it. Adding a
fifth contribution here reaches every caller by construction; that is the property
being bought, and it is the only reason to pay for the indirection.

## WHAT IS *NOT* HERE

The SCAN universe. `_scan` walks `pure_trees`; the armed measurement walks the
git-derived first-party set. That difference is exactly what makes the second
caller a different measurement rather than a duplicate of the check, so it stays
at each caller. What is shared is the part that must never differ.

Nothing here reports, and nothing here decides an exit code: the three declaration
keys' REJECTIONS hard-fail in `public_api_result_typed._report_bad_declarations`,
which runs before `_scan` and is the check's own obligation. A rejected entry
contributes nothing to the sets below — the readers already drop it — so a caller
that skips the reporting gets a correct exempt set and no diagnostic, never a
laundered declaration.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from livespec_dev_tooling.checks._declared_absence_returns import declared_absence_names
from livespec_dev_tooling.checks._no_expected_failure_mode import (
    functions_without_expected_failure_mode,
)
from livespec_dev_tooling.checks._public_api_consumption import (
    declared_public_names,
    repo_local_public_names,
)
from livespec_dev_tooling.checks._single_meaning_variants import declared_variant_names

if TYPE_CHECKING:
    from collections.abc import Mapping

    from livespec_dev_tooling.config import Config

__all__: list[str] = [
    "PublicAndExemptNames",
    "resolve_public_and_exempt_names",
]


@dataclass(frozen=True, kw_only=True)
class PublicAndExemptNames:
    """The two `(defining path, function name)` universes, carried together.

    They travel as one value because they are only ever meaningful together: the
    exempt set is a SUBTRACTION FROM the public set, so a caller holding one
    without the other cannot say anything about an offender. Returning a pair of
    bare frozensets would let a caller bind them in the wrong order — both have
    the same type — and nothing would notice.
    """

    public: frozenset[tuple[Path, str]]
    exempt: frozenset[tuple[Path, str]]


def resolve_public_and_exempt_names(
    *, config: Config, sources: Mapping[Path, str]
) -> PublicAndExemptNames:
    """Assemble the public and exempt universes over the CONSUMPTION set `sources`.

    `sources` is the git-derived first-party non-test set, NOT the scanned trees.
    A consumer of a pure-layer function generally lives outside the pure layer, so
    deriving consumption from the scanned trees alone would miss most of it — and
    missing consumption is the RELAXING direction.
    """
    public = repo_local_public_names(sources=sources) | declared_public_names(
        declared=config.cross_repo_public_api, sources=sources
    )
    # v179 member 1, recomputed here on EVERY run rather than declared. Its
    # universe is the same git-derived set as the consumption graph's, because
    # clause (d)'s fixpoint walks the whole call graph — a callee outside the
    # analysed set is doubt, and doubt disqualifies.
    exempt = functions_without_expected_failure_mode(sources=sources, io_trees=config.io_trees)
    # v179 MEMBER 2, DECLARED rather than computed, unioned with member 1's computed
    # set. The two are DISJOINT BY CONSTRUCTION — member 1's clause (e) refuses
    # every `X | None`, and that is the only shape bound 1 admits — so the union
    # adds exactly the declared absences, cannot let a declaration mask a member-1
    # result, and cannot let a member-1 result launder an invalid declaration. An
    # entry that FAILS bound 1 or bound 3 contributes nothing here; it fails the
    # check outright in `main()`.
    exempt |= declared_absence_names(declared=config.total_absence_returns, sources=sources)
    # livespec v183's SANCTIONED ALTERNATIVE SPELLING at a rendering boundary,
    # DECLARED per variant in `single_meaning_variants` and gated by
    # `checks/_declarable_unions`. It joins the same exempt set, but it is NOT a
    # third member of v179: nothing is exempted from the railway here — a
    # declared union already HAS the property the rule secures, and condition 1
    # TIGHTENS the obligation at the leaf rather than relaxing it. A function
    # returning a declared union that calls a primitive DIRECTLY is subtracted
    # inside `declared_variant_names` and stays convicted.
    exempt |= declared_variant_names(
        declared=config.single_meaning_variants, sources=sources, io_trees=config.io_trees
    )
    return PublicAndExemptNames(public=public, exempt=exempt)
