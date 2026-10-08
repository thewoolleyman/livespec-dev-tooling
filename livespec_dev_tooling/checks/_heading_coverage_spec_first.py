"""_heading_coverage_spec_first — the bounded spec-first admission of new debt.

Ratified into this repository's `SPECIFICATION/non-functional-requirements.md`
at v067, as the ONE exception to the shrink-only rule the sibling directions
enforce:

> A new register key MAY be admitted as spec-first debt ONLY when the same
> authored change introduces its exact H2 heading into the governed live
> specification, that heading and its coverage key are both absent from the
> comparable pre-change `HEAD` specification and coverage registry, the new
> coverage row declares `test: "TODO"` with a nonempty `work_item` and an
> acknowledgment that a real test at the required tier is owed, and mechanical
> regeneration supplies the matching owner and a `first_seen` date. The
> exception MUST NOT admit a pre-existing heading, real-test-to-TODO
> regression, orphan or dangling key, registry-only addition, or
> missing/mismatched owner or acknowledgment. Removing any existing H2 heading
> in the same specification file in that change MUST disqualify new debt in
> that file: replacement headings require real coverage, so renaming cannot
> reset debt.

WHY AN EXCEPTION EXISTS AT ALL, AND WHY IT IS THIS NARROW. The shrink-only
direction reads the SET of register keys and nothing else, so it cannot tell a
laundered entry from the one shape a spec-first repository legitimately
produces: a ratification lands a new `## Scenario:` heading, `heading_coverage`
demands a coverage row for it the same commit, and no real test can exist yet
because the implementation item has not run. Without the exception that commit
is unlandable and the only way out is to stop writing specifications first.

Every condition is therefore read from REPOSITORY DATA at two revisions — the
governed spec file and the coverage registry, in the working tree and at `HEAD`
— so there is nothing for an author to assert. That is what separates an
exception from an exemption list: the admission cannot be requested, only
earned, and the evidence that earns it is the same evidence a reviewer reads.

THE REMOVAL DISQUALIFIER IS FILE-SCOPED, NOT KEY-SCOPED, AND THAT IS THE
POINT. Read key by key, a RENAME is indistinguishable from a legitimate
spec-first addition: the new heading really is absent from `HEAD`, its coverage
key really is new, and its row really is owned and acknowledged. What tells
them apart lives in the other half of the same diff — the H2 heading the
specification file LOST — so the disqualifier asks of the FILE "did anything
leave?" rather than of the key "is this one new?". Without it, every covered
heading in the repository is one rename away from being reissued as fresh debt
with the clock restarted, which is a cheaper launder than any the shrink-only
direction was built to stop.

THE OWNER IS CHECKED ON BOTH SIDES BECAUSE A MATCH IS THE EVIDENCE OF
MECHANICAL GENERATION. The generator synchronizes a register entry's
`work_item` from its live coverage row, so two nonempty owners that DISAGREE
are proof the entry was not generated — and the clause admits only generated
rows.

THE ACKNOWLEDGMENT IS READ FOR CONTENT, THROUGH THE ONE RATIFIED PREDICATE.
This file previously read the coverage row's `reason` for PRESENCE only, on the
reasoning that whether an acknowledgment says the right thing is
`heading_coverage`'s judgement and deciding it twice would give a repository
two places to disagree about one rule. That reasoning was wrong, and it was
wrong in the direction that costs something: the clause makes the required-tier
acknowledgment a CONDITION OF THE ADMISSION, so presence-only does not avoid a
disagreement — it MANUFACTURES one. Measured on three fixtures identical in
every other condition, the ratchet admitted `not testable` and `a unit test is
owed` while `heading_coverage` refused both on the same row, and the admission
is the verdict that wins: it silences this check's own growth direction and
banks the row into the shrink-only register. Two surfaces, opposite verdicts,
one row.

The repair is not a second rule but the SAME one, read twice: the content
judgement is delegated to `reason_defect`, the public predicate
`_heading_coverage_reason_predicate` already exports and `heading_coverage`'s
reason guard already consumes. One predicate with two readers agrees by
construction; two predicates agree by coincidence. The refusal carries that
predicate's own `(defect, evidence)` pair rather than restating it, which is
also the "identify the failed evidence" half of the clause — a bare growth
finding would send an author to re-check the heading, the owner and the removal
disqualifier, every one of which they satisfied.

An ABSENT or blank `reason` is a different state and keeps its old treatment:
there is no wording to judge, so the growth direction's own finding is the
whole report. Only a reason that is declared and REFUSED earns a finding of its
own, and only when every other condition held — otherwise the report would name
the acknowledgment as deciding a key that some earlier condition had already
settled.

⛔ THE H2 SET IS RESTATED HERE RATHER THAN SHARED WITH `heading_coverage`. That
check's `_extract_h2_headings` is module-private and serves a different walk —
every template-declared spec file at every spec-tree root, in the working tree
only — while this module reads ONE named file at TWO revisions. Importing a
private name across a module boundary is refused by `private_calls` and by
pyright's `reportPrivateUsage`, and promoting one shared scanner would couple
the debt ratchet to the coverage check it has no other relationship with. The
two MAY disagree only in the fail-closed direction: a heading this scanner
misses is a heading whose debt is REFUSED, never one silently admitted.

UNAVAILABLE EVIDENCE REFUSES AND SAYS SO — IT IS NOT A SILENT NO. All three
reads can fail: `HEAD` may carry no copy of the specification file (a change
that creates one outright), no coverage registry at all, or the working-tree
copy may be unopenable. Each leaves the eligibility question UNANSWERED, so
the admission is refused — and the refusal alone is not enough. Refusing in
the same words as the decided refusals sends an author looking for a condition
they did not fail, so the comparison that could not be made is reported by
name. The other half matters more: unavailable evidence that PASSED would make
every admission obtainable by removing the evidence against it, which is
cheaper than satisfying a single one of the conditions.

FIRST ADOPTION ASKS NO ADMISSION QUESTION, which is why the evidence report
cannot red the commit that adopts the ratchet. The caller reaches this module
only when `HEAD`'s debt REGISTER is comparable; at adoption it is not, growth
is unjudged, and `grown` is never computed — so there is no key whose
eligibility an evidence failure could be reported about.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in this tree; the one diagnostic here
flows through the vendored structlog, which the caller configures.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

# Carried rather than inherited from an importer: without it the vendored
# `returns` resolves only because some module up the import chain happens to
# carry the preamble, which is a property of the caller rather than of this file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._heading_coverage_reason_predicate import (  # noqa: E402
    reason_defect,
)
from livespec_dev_tooling.heading_coverage_debt import (  # noqa: E402
    COVERAGE_PATH,
    head_rows,
    head_text,
    register_key,
    todo_rows,
)

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `heading_coverage_debt_register.py`, so pyright's per-file analysis
# does not flag them unused across the package boundary.
__all__: list[str] = [
    "SpecFirstDecision",
    "SpecFirstFinding",
    "report_spec_first_violations",
    "spec_first_admitted",
]


# One message per finding CODE: refusing in the same words would send the reader
# of either one looking for the other's cause.
_MESSAGES = {
    "spec_first_evidence_unavailable": (
        "heading-coverage-debt.json entry adds a register key whose new-heading eligibility "
        "this run cannot establish: the `evidence` field names the comparison against HEAD "
        "that could not be made. Per livespec-dev-tooling's "
        'SPECIFICATION/non-functional-requirements.md §"Scenario-tier coverage" an unavailable '
        "or unreadable comparison REFUSES the bounded spec-first admission rather than "
        "establishing it — commit the governed specification file and the coverage registry, "
        "or restore the copy this run could not read"
    ),
    "spec_first_acknowledgment_refused": (
        "heading-coverage.json row satisfies every other condition of the bounded spec-first "
        "admission, but its `reason` is not the required-tier acknowledgment that admission is "
        "conditioned on — `reason_defect` names what it asserted or omitted, `evidence` the "
        "wording that failed. Per livespec-dev-tooling's "
        'SPECIFICATION/non-functional-requirements.md §"Scenario-tier coverage" it MUST '
        "acknowledge that a real test at the required tier is owed, judged by the one predicate "
        "`heading_coverage` applies to the same row — rewrite it to name the owed test and tier"
    ),
}


def _h2_headings(*, source: str) -> frozenset[str]:
    """The exact H2 headings in `source`, trailing whitespace stripped.

    A `### ` line does not start with `## ` and so is excluded without a second
    test; the registry's `heading` field carries the `## ` prefix verbatim, which
    is what makes an EXACT comparison possible rather than a prefix match.
    """
    return frozenset(
        stripped
        for stripped in (line.rstrip() for line in source.splitlines())
        if stripped.startswith("## ")
    )


def _live_headings(*, cwd: Path, spec_root: str, spec_file: str) -> frozenset[str] | None:
    """The working-tree H2 set of a governed spec file; `None` when it cannot be read.

    `None` is the UNREADABLE answer and never an empty set: a spec file this run
    cannot open proves nothing about whether a heading is new, and reading it as
    "no headings" would refuse every admission while LOOKING like a verdict
    about the heading.
    """
    try:
        source = (cwd / spec_root / spec_file).read_text(encoding="utf-8")
    except OSError:
        return None
    return _h2_headings(source=source)


def _head_headings(*, cwd: Path, spec_root: str, spec_file: str) -> frozenset[str] | None:
    """The `HEAD` H2 set of a governed spec file; `None` when HEAD carries no copy.

    The mirror of `_live_headings` on the other revision, and the same
    distinction: `None` means no comparison is possible — not a repository, no
    such blob, a spec file this change creates outright — which cannot establish
    that a heading is new.
    """
    committed = head_text(cwd=cwd, path=Path(spec_root) / spec_file)
    if isinstance(committed, IOFailure):
        return None
    return _h2_headings(source=unsafe_perform_io(committed.unwrap()))


def _keys(*, rows: list[dict[str, object]]) -> frozenset[tuple[str, str, str]]:
    """The register keys `rows` carries; unkeyed rows place nothing."""
    return frozenset(key for key in (register_key(row=row) for row in rows) if key is not None)


def _head_registry_keys(*, cwd: Path) -> frozenset[tuple[str, str, str]] | None:
    """Every coverage key `HEAD`'s registry carries; `None` when it is incomparable.

    EVERY key, not only the `TODO` ones: the ratified clause requires the
    coverage key to be absent from `HEAD`'s registry outright, which is what
    refuses a real-test-to-`TODO` regression. A key that already had a row is
    not a new heading's key whatever that row said.
    """
    committed = head_rows(cwd=cwd, path=COVERAGE_PATH)
    return (
        None
        if isinstance(committed, IOFailure)
        else _keys(rows=unsafe_perform_io(committed.unwrap()))
    )


def _text(*, value: object) -> str | None:
    """`value` when it is a NONEMPTY string, else `None` — one spelling of "declared".

    A field holding `""`, whitespace, or a non-string declares nothing, and the
    three must answer identically: a rule that accepted a blank `work_item`
    while rejecting a missing one would turn the ownership condition into a
    typing exercise.
    """
    if isinstance(value, str) and value.strip():
        return value
    return None


def _owners(*, rows: list[dict[str, object]]) -> dict[tuple[str, str, str], str]:
    """Key → the nonempty `work_item` `rows` declare; rows declaring none place nothing.

    Shared by both sides of the ownership comparison — live `TODO` rows and
    register entries — because the comparison is only meaningful if the two
    sides are read the same way. An absent key here is "this side names no
    owner", which is a refusal rather than a wildcard.
    """
    owners: dict[tuple[str, str, str], str] = {}
    for row in rows:
        key = register_key(row=row)
        owner = _text(value=row.get("work_item"))
        if key is not None and owner is not None:
            owners[key] = owner
    return owners


def _reason_defects(
    *, rows: list[dict[str, object]]
) -> dict[tuple[str, str, str], tuple[str, str] | None]:
    """Key → the `(defect, evidence)` its `reason` draws; `None` when it acknowledges.

    A key is ABSENT when its row declares no reason at all, and that third state
    is the point of returning a mapping rather than a set: declared-and-refused
    is a condition this direction decides and reports, while
    not-declared-at-all is the growth direction's own finding and must not be
    reported twice under two names.

    The judgement itself is `reason_defect`'s — the ratified predicate
    `heading_coverage`'s reason guard reads for the identical row. Nothing about
    the wording is decided here, which is what keeps the two surfaces from
    disagreeing about one rule.
    """
    defects: dict[tuple[str, str, str], tuple[str, str] | None] = {}
    for row in rows:
        key = register_key(row=row)
        reason = _text(value=row.get("reason"))
        if key is not None and reason is not None:
            defects[key] = reason_defect(reason=reason)
    return defects


@dataclass(frozen=True, kw_only=True)
class _Declared:
    """What the two rows files declare about every key, read once for the run.

    Bundled rather than threaded as three parameters so `_admits` keeps one
    argument per EVIDENCE SOURCE — the repository at two revisions, and the
    rows the change authors — instead of one per field.
    """

    todo_owners: dict[tuple[str, str, str], str]
    register_owners: dict[tuple[str, str, str], str]
    reason_defects: dict[tuple[str, str, str], tuple[str, str] | None]


@dataclass(frozen=True, kw_only=True)
class SpecFirstFinding:
    """One grown key the exception refused with something to say about WHY.

    `evidence` names what failed — the comparison that could not be made, or the
    wording the acknowledgment predicate refused — which is the whole value of
    the finding over the bare refusal the caller emits anyway: it tells an author
    which read or which field to go and fix, instead of sending them to re-check
    conditions they satisfied.

    `defect` carries the acknowledgment predicate's own discriminator under the
    same field name `heading_coverage`'s reason guard prints, so the two surfaces
    name one defect identically. It is `None` for an evidence failure, which has
    no wording to classify, and is emitted either way: a conditional field would
    make an absent `reason_defect` ambiguous between "not that kind of finding"
    and "that key was omitted".
    """

    code: str
    key: tuple[str, str, str]
    evidence: str
    defect: str | None = None


@dataclass(frozen=True, kw_only=True)
class SpecFirstDecision:
    """The exception's two answers for one run, deliberately not collapsed into one.

    `admitted` is subtracted from the caller's growth findings; `reported`
    carries the keys the exception has something to SAY about — eligibility it
    could not establish, or an acknowledgment it decided against. A key is in
    neither set when the exception simply did not apply to it, which is an
    ordinary decided refusal the caller's `register_grew` finding reports whole.
    """

    admitted: frozenset[tuple[str, str, str]]
    reported: list[SpecFirstFinding]


def _eligible(
    *,
    key: tuple[str, str, str],
    live: frozenset[str],
    before: frozenset[str],
    head_registry_keys: frozenset[tuple[str, str, str]],
    declared: _Declared,
) -> bool:
    """Whether every admission condition EXCEPT the acknowledgment holds for `key`.

    ONE conjunction, deliberately, because this half of the ratified clause IS
    one: every condition must hold, and a key that fails any of them is the
    growth the shrink-only direction already named. Every argument is already
    KNOWN here — the caller establishes the three evidence reads answered before
    asking, so this function decides and never reports an unavailability.

    The acknowledgment is the one condition deliberately LEFT OUT, because it is
    the only one whose failure earns a finding of its own: separating it is what
    lets the caller say "this would have been admitted but for the reason"
    rather than reporting the acknowledgment as deciding a key some earlier
    condition had already settled.

    `declared.todo_owners.get(key)` doubles as the ORPHAN test: a register entry
    with no live `TODO` row places no owner, so a dangling key fails here rather
    than needing a condition of its own — and it must, because without the row
    there is no owner and no `reason` for the acknowledgment to read.
    """
    heading = key[2]
    owner = declared.todo_owners.get(key)
    return (
        key not in head_registry_keys
        and heading in live
        and heading not in before
        and not before - live
        and owner is not None
        and declared.register_owners.get(key) == owner
    )


def _unavailable(
    *,
    before: frozenset[str] | None,
    head_registry_keys: frozenset[tuple[str, str, str]] | None,
) -> str:
    """Which comparison could not be made; the caller has established one could not.

    Ordered by how little the run could do about it: a missing `HEAD` registry
    defeats every key at once, a missing `HEAD` copy of one specification file
    defeats that file's keys, and an unreadable working-tree copy is the local
    condition an author can fix on the spot. Reporting one name rather than a
    set keeps the remedy single — the next run re-reads all three anyway.

    The live read is the RESIDUAL and so takes no parameter: the caller calls
    this only when one of the three failed, so with both `HEAD` reads answered
    the working-tree copy is the one that did not. Taking `live` to re-test it
    would add a branch no fixture can reach, which is a worse record of the
    reasoning than this sentence.
    """
    if head_registry_keys is None:
        return "head-coverage-registry-incomparable"
    if before is None:
        return "head-specification-copy-absent"
    return "live-specification-unreadable"


def spec_first_admitted(
    *,
    cwd: Path,
    grown: list[tuple[str, str, str]],
    registry_rows: list[dict[str, object]],
    register_rows: list[dict[str, object]],
) -> SpecFirstDecision:
    """What the bounded v067 spec-first exception says about each key in `grown`.

    `grown` is the shrink-only direction's own finding set, passed in rather than
    recomputed, so the exception can only ever REMOVE a key the caller already
    convicted — it cannot invent an admission for a key no direction named. The
    two rows lists are the caller's already-validated copies for the same
    reason: re-reading either file here could admit a key against bytes no other
    direction judged.

    The evidence reads are skipped entirely when nothing grew, and that is
    load-bearing rather than an optimisation: the overwhelming majority of runs
    carry no growth at all, and a repository at zero debt must not be asked to
    open a spec file to confirm it — nor to report an evidence failure about a
    key no direction named.
    """
    if not grown:
        return SpecFirstDecision(admitted=frozenset(), reported=[])
    live_todo = todo_rows(rows=registry_rows)
    declared = _Declared(
        todo_owners=_owners(rows=live_todo),
        register_owners=_owners(rows=register_rows),
        reason_defects=_reason_defects(rows=live_todo),
    )
    head_registry_keys = _head_registry_keys(cwd=cwd)
    admitted: set[tuple[str, str, str]] = set()
    reported: list[SpecFirstFinding] = []
    for key in grown:
        spec_root, spec_file, _ = key
        live = _live_headings(cwd=cwd, spec_root=spec_root, spec_file=spec_file)
        before = _head_headings(cwd=cwd, spec_root=spec_root, spec_file=spec_file)
        if head_registry_keys is None or before is None or live is None:
            reported.append(
                SpecFirstFinding(
                    code="spec_first_evidence_unavailable",
                    key=key,
                    evidence=_unavailable(before=before, head_registry_keys=head_registry_keys),
                )
            )
            continue
        if not _eligible(
            key=key,
            live=live,
            before=before,
            head_registry_keys=head_registry_keys,
            declared=declared,
        ):
            continue
        if key not in declared.reason_defects:
            # No `reason` declared: nothing to judge, so growth reports it whole.
            continue
        defect = declared.reason_defects[key]
        if defect is None:
            admitted.add(key)
            continue
        reported.append(
            SpecFirstFinding(
                code="spec_first_acknowledgment_refused",
                key=key,
                evidence=defect[1],
                defect=defect[0],
            )
        )
    return SpecFirstDecision(admitted=frozenset(admitted), reported=reported)


def report_spec_first_violations(*, findings: list[SpecFirstFinding]) -> None:
    """Report every refusal this module owns at error level — the caller owns the exit code."""
    log = structlog.get_logger("heading_coverage_debt_register")
    for finding in findings:
        log.error(
            _MESSAGES[finding.code],
            spec_root=finding.key[0],
            spec_file=finding.key[1],
            heading=finding.key[2],
            finding=finding.code,
            reason_defect=finding.defect,
            evidence=finding.evidence,
            failing=True,
        )
