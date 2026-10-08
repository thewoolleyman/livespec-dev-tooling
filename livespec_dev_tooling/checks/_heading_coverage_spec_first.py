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
rows. The coverage row's own `reason` is read for PRESENCE only: whether an
acknowledgment says the right thing is `heading_coverage`'s ratified
judgement, and re-deciding it here would give a repository two places to
disagree about one rule.

⛔ THE H2 SET IS RESTATED HERE RATHER THAN SHARED WITH `heading_coverage`. That
check's `_extract_h2_headings` is module-private and serves a different walk —
every template-declared spec file at every spec-tree root, in the working tree
only — while this module reads ONE named file at TWO revisions. Importing a
private name across a module boundary is refused by `private_calls` and by
pyright's `reportPrivateUsage`, and promoting one shared scanner would couple
the debt ratchet to the coverage check it has no other relationship with. The
two MAY disagree only in the fail-closed direction: a heading this scanner
misses is a heading whose debt is REFUSED, never one silently admitted.

Output discipline: this module DECIDES and emits nothing — the caller owns
every diagnostic — so `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) have nothing to ban here.
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

from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

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
    "spec_first_admitted",
]


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


def _acknowledged(*, rows: list[dict[str, object]]) -> frozenset[tuple[str, str, str]]:
    """The keys whose row carries a `reason` at all — presence, never content.

    The ratified clause puts the CONTENT rule ("MUST acknowledge that a real
    test at the required tier is owed and MUST name nothing else") under
    `heading_coverage`, so this direction reads only whether the acknowledgment
    exists. Judging the wording twice would let the two checks disagree about
    one rule, and the one that ran first would win.
    """
    acknowledged: set[tuple[str, str, str]] = set()
    for row in rows:
        key = register_key(row=row)
        if key is not None and _text(value=row.get("reason")) is not None:
            acknowledged.add(key)
    return frozenset(acknowledged)


@dataclass(frozen=True, kw_only=True)
class _Declared:
    """What the two rows files declare about every key, read once for the run.

    Bundled rather than threaded as three parameters so `_admits` keeps one
    argument per EVIDENCE SOURCE — the repository at two revisions, and the
    rows the change authors — instead of one per field.
    """

    todo_owners: dict[tuple[str, str, str], str]
    register_owners: dict[tuple[str, str, str], str]
    acknowledged: frozenset[tuple[str, str, str]]


def _admits(
    *,
    cwd: Path,
    key: tuple[str, str, str],
    head_registry_keys: frozenset[tuple[str, str, str]] | None,
    declared: _Declared,
) -> bool:
    """Whether `key` is the bounded spec-first exception rather than plain growth.

    ONE conjunction, deliberately, because the ratified clause IS one: every
    condition must hold, and a key that fails any of them is the growth the
    shrink-only direction already named. Both spec revisions are read before the
    test rather than inside it, so an unreadable working tree and an
    incomparable `HEAD` are distinguishable answers rather than one short
    circuit.

    `declared.todo_owners.get(key)` doubles as the ORPHAN test: a register entry
    with no live `TODO` row places no owner, so a dangling key fails here rather
    than needing a condition of its own — and it must, because without the row
    there is no owner and no acknowledgment for the next two conditions to read.
    """
    spec_root, spec_file, heading = key
    live = _live_headings(cwd=cwd, spec_root=spec_root, spec_file=spec_file)
    before = _head_headings(cwd=cwd, spec_root=spec_root, spec_file=spec_file)
    owner = declared.todo_owners.get(key)
    return (
        head_registry_keys is not None
        and key not in head_registry_keys
        and live is not None
        and heading in live
        and before is not None
        and heading not in before
        and not before - live
        and owner is not None
        and declared.register_owners.get(key) == owner
        and key in declared.acknowledged
    )


def spec_first_admitted(
    *,
    cwd: Path,
    grown: list[tuple[str, str, str]],
    registry_rows: list[dict[str, object]],
    register_rows: list[dict[str, object]],
) -> frozenset[tuple[str, str, str]]:
    """The subset of `grown` the bounded v067 spec-first exception admits.

    `grown` is the shrink-only direction's own finding set, passed in rather than
    recomputed, so the exception can only ever REMOVE a key the caller already
    convicted — it cannot invent an admission for a key no direction named. The
    two rows lists are the caller's already-validated copies for the same
    reason: re-reading either file here could admit a key against bytes no other
    direction judged.

    The evidence reads are skipped entirely when nothing grew, and that is
    load-bearing rather than an optimisation: the overwhelming majority of runs
    carry no growth at all, and a repository at zero debt must not be asked to
    open a spec file to confirm it.
    """
    if not grown:
        return frozenset()
    live_todo = todo_rows(rows=registry_rows)
    declared = _Declared(
        todo_owners=_owners(rows=live_todo),
        register_owners=_owners(rows=register_rows),
        acknowledged=_acknowledged(rows=live_todo),
    )
    head_registry_keys = _head_registry_keys(cwd=cwd)
    return frozenset(
        key
        for key in grown
        if _admits(cwd=cwd, key=key, head_registry_keys=head_registry_keys, declared=declared)
    )
