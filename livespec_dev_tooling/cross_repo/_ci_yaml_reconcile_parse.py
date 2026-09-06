"""_ci_yaml_reconcile_parse — pure ci.yml transforms for ci_yaml_canonical_reconcile.

Private sibling of `ci_yaml_canonical_reconcile.py`, following the same pure/IO
plus LLOC-reduction split as `_ci_matrix_parse` / `ci_matrix_completeness` and
`_canonical_reconcile_parse` / `justfile_canonical_reconcile`: every function
here is PURE and the parent owns the file reads, writes, and annotations. The
module is private-NAMED with public-NAMED functions, the convention its siblings
already use.

## Two anchors, because consumers mirror the aggregate in two shapes

`check_ci_matrix_completeness` counts a canonical slug as run by CI when a job
lists it in a `strategy.matrix.target:` list OR invokes it from a `run:` line as
`just <slug>`. Both are first-class; the gate's own coverage union accepts
either.

The reconciler, however, could only ever WRITE the first. Its matrix-anchor
finder carried the claim that such a list "is guaranteed to exist wherever this
reconcile can matter" — and that claim was false. Five fleet consumers run the
aggregate exclusively in the batched form

    just check-aggregate-completeness || failed="$failed check-aggregate-completeness"

so the reconcile found no anchor and hard-failed the bump job. That failure is
not cosmetic: it aborts the whole bump, no pull request is opened, and the pin
never moves. Those five sat two releases behind, each carrying a red bump run
that nothing aggregated to fleet level, until a maintainer re-derived the
fan-out membership by hand.

`batch_anchor` closes that asymmetry: the writer now understands every shape the
reader already accepted. A consumer carrying neither shape is genuinely
unreconcilable and still escalates.

The batch line is built by SUBSTITUTION into the consumer's own aggregate line
rather than from a format string of our own, so a repo whose batched lines are
spelled differently keeps its spelling. The gate parses these with
`_ci_matrix_parse._parse_run_slugs`, which scans for `just <slug>` anywhere in a
run line, so any faithful substitution is recognized.

## The anchor is the aggregate's OWN block, not every run line in the file

`batch_anchor` used to collect EVERY `just check-<slug>` line in the file, and
`batch_insert_index` anchors on the first canonical entry that sorts after the
new slug — so a slug sorting before `check-per-file-coverage` landed in THAT
job's bare single-target step, which sits well above the metadata batch.
v1.43.0 did precisely that with `check-ci-gate-parity` in seven consumers. A
bare step line declares no `$failed` accumulator, so the inserted `||
failed="$failed <slug>"` fed a variable nothing reads: the check RAN and its
non-zero exit was DISCARDED, leaving the job green whatever the check found.
Unlike the missing-anchor failure above, this one is SILENT — it survived until
every carrier PR of the `pr-gate-master-parity` plan moved the line by hand.

Two rules close it. An ENTRY must be accumulator-SHAPED — a `just check-<slug>`
invocation carrying a `||` tail that captures its exit status — so a bare
single-target step line is never an insertion anchor. And the entries are SCOPED
to the contiguous, equally-indented run of such lines that contains the
aggregate, so a sibling step's own accumulator (the `.py`-gated batch that
precedes the metadata batch in the common fleet shape) is never part of this
one. A consumer that invokes the aggregate with no tail to capture it therefore
carries no batch at all and takes the loud `::error::` path — the honest answer,
since there is no accumulator there for an inserted line to feed.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

__all__: list[str] = [
    "AGGREGATE_SLUG",
    "Anchor",
    "BatchAnchor",
    "above_leading_comments",
    "batch_anchor",
    "batch_insert_index",
    "batch_line_for",
    "collect_entries",
    "insert_index",
    "matrix_anchor",
    "rewrite_renamed_bullets",
]

AGGREGATE_SLUG = "check-aggregate-completeness"

# `strategy.matrix.target:` anchors. The bullet regex mirrors
# `_ci_matrix_parse._MATRIX_TARGET_LINE` so this module recognizes exactly the
# entries the gate counts, and captures the bullet's own indent so an inserted
# entry lands at the list's existing depth.
_MATRIX_KEY = re.compile(r"^\s*matrix:\s*$")
_TARGET_KEY = re.compile(r"^\s*target:\s*$")
_BULLET = re.compile(r"^(\s*)-\s*([\w-]+)\s*$")

# One line of a batched ACCUMULATOR block: `just <check-slug>` followed by a
# `||` tail that captures the invocation's exit status (`|| failed="$failed
# <slug>"` in every fleet consumer). The tail is matched only by its `||` and is
# otherwise the consumer's own, preserved by substitution rather than
# re-synthesised, so a repo that spells its tail differently keeps its spelling.
#
# The `||` is load-bearing, not decoration. A BARE `just check-<slug>` line is a
# single-target step whose own exit status IS the step's verdict; it declares no
# accumulator, so a line inserted beside it feeds a `$failed` nothing reads.
_BATCH_RUN = re.compile(r"^(\s*)just\s+(check-[\w-]+)\b[^\n]*\|\|")


@dataclass(frozen=True, kw_only=True)
class Anchor:
    """The consumer's `matrix.target:` list that already carries the aggregate slug.

    `head` is the line index of the list's first entry line (where a slug with no
    canonical predecessor is inserted), `entries` pairs each bullet's line index
    with its token, and `indent` is the bullets' own leading whitespace.
    """

    head: int
    entries: tuple[tuple[int, str], ...]
    indent: str


def collect_entries(*, lines: list[str], head: int) -> tuple[tuple[int, str], ...]:
    """Collect the (line index, token) bullets of the target list starting at `head`.

    Blank and `#`-comment lines inside the list are stepped over (a consumer
    matrix routinely annotates its entries); the first line that is neither a
    bullet nor a blank/comment ends the list.
    """
    entries: list[tuple[int, str]] = []
    for index in range(head, len(lines)):
        stripped = lines[index].strip()
        if not stripped or stripped.startswith("#"):
            continue
        bullet = _BULLET.match(lines[index])
        if bullet is None:
            break
        entries.append((index, bullet.group(2)))
    return tuple(entries)


def matrix_anchor(*, lines: list[str]) -> Anchor | None:
    """Return the `matrix.target:` list carrying the aggregate slug, or None.

    That list is guaranteed to exist wherever this reconcile can matter: a
    consumer whose CI does not run `check-aggregate-completeness` cannot be
    failed by `check-ci-matrix-completeness` for a slug the aggregate wires.
    """
    in_matrix = False
    for index, raw in enumerate(lines):
        if _MATRIX_KEY.match(raw) is not None:
            in_matrix = True
            continue
        if not in_matrix or _TARGET_KEY.match(raw) is None:
            continue
        entries = collect_entries(lines=lines, head=index + 1)
        if AGGREGATE_SLUG not in [token for _, token in entries]:
            continue
        first_line = lines[entries[0][0]]
        return Anchor(
            head=entries[0][0],
            entries=entries,
            indent=first_line[: len(first_line) - len(first_line.lstrip())],
        )
    return None


def above_leading_comments(*, lines: list[str], entry: int, head: int) -> int:
    """Return the first line of the `#` comment block directly above `entry`.

    A comment block immediately above a matrix entry annotates THAT entry (the
    fleet's ci.yml matrices are heavily annotated), so a new entry sorting before
    it must land ABOVE the block, not between the block and the entry it
    describes — a bump PR merges the insertion into the consumer's master
    permanently, making a misattributed comment a durable defect rather than a
    transient diff artifact. A blank line breaks the association, and the walk
    never passes the list head.
    """
    point = entry
    while point > head and lines[point - 1].strip().startswith("#"):
        point -= 1
    return point


def insert_index(*, lines: list[str], anchor: Anchor, canonical_set: set[str], slug: str) -> int:
    """Return the line index `slug`'s bullet is inserted BEFORE.

    The slug lands before the first EXISTING canonical entry that sorts after it
    (keeping the canonical block alphabetical, and above any comment block that
    annotates that entry), or after the last canonical entry when it sorts last,
    or at the list head when the list holds no canonical entry. Non-canonical
    entries (a consumer's repo-private extras, conventionally parked at the tail)
    are never sort anchors, so the canonical block stays contiguous.
    """
    last_canonical: int | None = None
    for index, token in anchor.entries:
        if token not in canonical_set:
            continue
        if token > slug:
            return above_leading_comments(lines=lines, entry=index, head=anchor.head)
        last_canonical = index
    return anchor.head if last_canonical is None else last_canonical + 1


def rewrite_renamed_bullets(
    *, ci_yaml_text: str, renames: Sequence[tuple[str, str]], canonical_set: set[str]
) -> str:
    """Rewrite a CI matrix bullet naming a since-renamed slug to its NEW name.

    Mirrors the sibling `justfile_canonical_reconcile._rewrite_renamed_references`:
    a canonical check rename drops the OLD slug from the canonical set with no
    trace, so a consumer's ci.yml matrix bullet still naming it strands the bump
    on `just check-<old-slug>` once the sibling justfile reconcile has already
    rewritten that recipe away (livespec-dev-tooling-3gy1). For every rename
    whose `new` side is canonical, rewrites the OLD bullet in place to the NEW
    slug — or, when a NEW bullet is ALREADY present elsewhere in the matrix
    (a maintainer or an earlier pass already added it), drops the now-duplicate
    OLD bullet line entirely rather than leaving two.
    """
    lines = ci_yaml_text.splitlines(keepends=True)
    for old, new in renames:
        tokens = [m.group(2) if (m := _BULLET.match(ln)) else None for ln in lines]
        if new not in canonical_set or old not in tokens:
            continue
        i = tokens.index(old)
        new_line = f"{lines[i][: len(lines[i]) - len(lines[i].lstrip())]}- {new}\n"
        lines[i : i + 1] = [] if new in tokens else [new_line]
    return "".join(lines)


@dataclass(frozen=True, kw_only=True)
class BatchAnchor:
    """The consumer's batched aggregate section, when it carries no matrix list.

    `entries` pairs each batched `just <slug>` line index with its slug, in file
    order; `template` is the consumer's own aggregate line, reused verbatim as
    the shape for inserted lines.
    """

    entries: tuple[tuple[int, str], ...]
    template: str


@dataclass(frozen=True, kw_only=True)
class _BlockLine:
    """One accumulator-shaped run line: its file index, its indent, and its slug."""

    index: int
    indent: str
    slug: str


def _accumulator_lines(*, lines: list[str]) -> list[_BlockLine]:
    """Return every accumulator-shaped `just check-<slug>` line, in file order."""
    return [
        _BlockLine(index=index, indent=match.group(1), slug=match.group(2))
        for index, raw in enumerate(lines)
        if (match := _BATCH_RUN.match(raw)) is not None
    ]


def _same_block(*, lines: list[str], one: _BlockLine, other: _BlockLine) -> bool:
    """Return True when two accumulator lines belong to ONE contiguous block.

    Contiguity is what scopes the anchor to the step whose `$failed` an inserted
    line will actually feed: the two lines share an indent, and nothing but
    blank or `#`-comment lines separates them — the same tolerance
    `collect_entries` gives an interleaved comment inside a matrix target list,
    because these ci.yml files annotate individual entries. A `just
    check-<slug>` line in a DIFFERENT step is separated by that step's own YAML
    keys and by the block-closing `if [ -n "$failed" ]` test, so it can never
    join the block.
    """
    if one.indent != other.indent:
        return False
    first, second = sorted((one.index, other.index))
    between = [lines[index].strip() for index in range(first + 1, second)]
    return all(not text or text.startswith("#") for text in between)


def batch_anchor(*, lines: list[str]) -> BatchAnchor | None:
    """Return the accumulator block that invokes the aggregate slug, or None.

    A consumer qualifies when an accumulator-shaped run line invokes `just
    check-aggregate-completeness`. The anchor's entries are the lines of THAT
    block alone — walked outward from the aggregate for as long as `_same_block`
    holds — so insertion preserves canonical order against the slugs already
    present without ever leaving the block that fails the job on `$failed`.
    """
    found = _accumulator_lines(lines=lines)
    pivot = next((slot for slot, line in enumerate(found) if line.slug == AGGREGATE_SLUG), None)
    if pivot is None:
        return None
    block = [found[pivot]]
    for step in (-1, 1):
        for slot in range(pivot + step, -1 if step < 0 else len(found), step):
            if not _same_block(lines=lines, one=found[slot - step], other=found[slot]):
                break
            block.append(found[slot])
    ordered = sorted(block, key=lambda line: line.index)
    return BatchAnchor(
        entries=tuple((line.index, line.slug) for line in ordered),
        template=lines[found[pivot].index],
    )


def batch_line_for(*, anchor: BatchAnchor, slug: str) -> str:
    """Return the batched run line for `slug`, in the consumer's own spelling.

    Built by substituting `slug` for the aggregate slug throughout the
    consumer's aggregate line, so the surrounding shape — indent, the
    `|| failed="$failed <slug>"` tail, any repo-specific wording — is carried
    over rather than re-invented. A repo that spells its batched lines
    differently keeps its spelling, and the gate still recognizes the result
    because it scans for `just <slug>` anywhere in the line.
    """
    return anchor.template.replace(AGGREGATE_SLUG, slug)


def batch_insert_index(*, anchor: BatchAnchor, canonical_set: set[str], slug: str) -> int:
    """Return the line index at which `slug`'s batched line belongs.

    Mirrors `insert_index`: before the first EXISTING canonical slug that sorts
    after it, after the last canonical slug when it sorts last. Non-canonical
    entries are never sort anchors, so the canonical block stays contiguous.
    """
    last_canonical: int | None = None
    for index, token in anchor.entries:
        if token not in canonical_set:
            continue
        last_canonical = index
        if token > slug:
            return index
    if last_canonical is None:
        return anchor.entries[0][0] if anchor.entries else 0
    return last_canonical + 1
