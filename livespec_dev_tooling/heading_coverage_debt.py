"""heading_coverage_debt — the shrink-only heading-coverage debt register.

Charter D3 of plan `fleet-heading-coverage-convergence` (epic
`livespec-dev-tooling-0bse`), ratified into this repository's
`SPECIFICATION/non-functional-requirements.md` at v064:

> Every `TODO` row MUST appear in the repository's shrink-only
> heading-coverage debt register (`tests/heading-coverage-debt.json`, keyed
> by `(spec_root, spec_file, heading)` with the owning `work_item` and the
> row's first-seen date). [...] The register is generated mechanically from
> the live file at adoption, never authored by hand.

This module owns the register's SOURCES — its paths, how a working-tree copy
and a `HEAD` copy are read, and what git history says about a row's first-seen
date — plus the MECHANICAL GENERATOR that writes it. A row's own IDENTITY and
SCHEMA (its key, including how a scenario-shaped registry row derives one, and
the fields a register entry must carry) live in the private sibling
`_heading_coverage_debt_keys`, which this module re-imports so the vocabulary
every check reads keeps its single import site here. That split is by cohesion:
nothing in the sibling opens the registry, the register or git, and nothing
here decides what a row means. The verdict lives next door in
`livespec_dev_tooling.checks.heading_coverage_debt_register`; the two are
split because generation walks git history — a slow, write-side operation an
author runs once per resolution — while the check is a fast, read-only gate
that runs in every aggregate.

WHY THE REGISTER IS GENERATED AND NOT AUTHORED. A hand-authored baseline is
a list of exemptions: an author who wants a new `TODO` accepted adds a line,
and the ratchet becomes a formality. Generated from the live registry, the
register can only ever restate what is already there — so the ONLY way to
change it is to change the registry, which is exactly what the check
compares it against.

FIRST-SEEN IS READ FROM GIT, NOT DECLARED. `first_seen` is the UTC calendar
date (`YYYY-MM-DD`) of the committer timestamp of the earliest commit whose
`tests/heading-coverage.json` blob already carried the row as a `TODO`. It
is evidence rather than an assertion, which is what lets the release-tier
age bound (charter D5, a sibling work-item) rest on it. A key git history
cannot place — a row added in the working tree, or a registry with no
history yet — falls back to the caller-supplied `today`, so generation never
invents a date that looks measured.

...AND THE BASIS IS UTC, NOT THE COMMIT'S OWN TIMEZONE. The recorded date and
the committer-timestamp evidence the check next door judges it against are
both UTC calendar dates, because the committed tier judges a tree the forge may
have re-stamped. `%cs` renders the committer date in the COMMIT'S OWN timezone,
so one instant carried two calendar dates and a rebase-merge — which rewrites
exactly that field — could flip a verdict with no change to the tree; it did,
in livespec-orchestrator-beads-fabro on 2026-10-14. `first_seen_dates` now
reads `%cI` and normalizes, and `_utc_calendar_date` carries the measurement.

...AND ONCE RECORDED IT IS PRESERVED, NEVER RE-DERIVED. v067 of this
repository's `SPECIFICATION/non-functional-requirements.md` adds the other
half of that sentence:

> Once recorded, `first_seen` MUST NOT move later [...] generator
> regeneration MUST preserve existing dates, add only genuinely new rows,
> and keep ownership synchronized with the live coverage row.

So the register's OWN rows are an input to its regeneration, and the two
fields are read from opposite sides: `first_seen` from the recorded register
(falling back to git, then to `today`, for a genuinely new key) and
`work_item` from the live coverage row every run. The asymmetry is the whole
rule. A date re-derived each run moves LATER for the ordinary case — a row
authored in a working tree is dated `today` and committed a day or more
after, so its recorded date legitimately PRECEDES the git evidence — and
moving it forward resets the age bound's clock on debt that is already
running. An owner, by contrast, is a live fact about who owes the test, so
re-reading it is what keeps a reassignment mechanical instead of a hand edit.
Preserving a date EARLIER than the git evidence is therefore correct and
deliberate; only moving one later is forbidden, and the check next door
enforces that direction on both the authored and the committed tier.

That enforcement is why `as_calendar_date` and `live_todo_keys` are SHARED
rather than private to the direction that first needed them; the measurement
that paragraph records now lives with them, in
`_heading_coverage_debt_keys`.

## ON THE `IOResult` RAILWAY — `livespec-dev-tooling-qndn.15`

Both reads this module owns collapsed a NON-ANSWER into an answer's spelling,
and `_rows_from_text` below is the proof the distinction was already
understood: its `None` is reserved for "this is NOT a registry", and its own
docstring warns that an empty array "must never be spelled the same way as 'I
could not read it'". `load_rows` then spelled it exactly that way, mapping
that `None` straight onto `[]`.

WHAT EACH TRACK NOW CARRIES:

- `load_rows` — ABSENCE STAYS AN ANSWER (`IOSuccess([])`), deliberately, for
  the reason its own docstring already gave: a consumer that has not adopted
  the register has no file, and the check that calls this owns the verdict
  about an empty register. A file that EXISTS and cannot be turned into a
  comparable array is a `RowsUnreadable` failure — which is what an
  unparseable `tests/heading-coverage.json` used to spend as "there are no
  `TODO` rows", a vacuous pass for the ratchet that reads it and, through
  `generate_register`, an EMPTY baseline written over the real one.
- `head_rows` — every arm of the old `None` is a failure, because `None` there
  ALREADY meant "no comparison is possible" and never "it was empty at HEAD".
  No verdict moves; what moves is the caller's obligation to notice, off a
  sentinel it may forget to test and onto a track it cannot.

`IOResult` rather than `Result`, and that is the honest half: one read touches
the filesystem and the other shells out to git, so the effect is real and
claiming otherwise would blur the distinction the sibling conversions in this
tree sharpened.

Output discipline: `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned here. This module's `main()` WRITES THE
REGISTER FILE and, on the ONE path where it refuses to, says why through
structlog (JSON to stderr); the vendored copy is added to `sys.path` at module
import time. A generator that declines to overwrite the ratchet's baseline
must not do it silently.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

# Carried rather than inherited from an importer: without it the vendored
# `returns` / `structlog` resolve only because some module up the import chain
# happens to carry the preamble, which is a property of the caller rather than
# of this file. The module that broke the fleet's release fan-out for seven
# hours on 2026-07-30 was in exactly that state until it became an entry point.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling._heading_coverage_debt_keys import (  # noqa: E402
    as_calendar_date,
    configured_spec_root,
    live_todo_keys,
    register_key,
    register_row_is_complete,
    todo_rows,
)

__all__: list[str] = [
    "COVERAGE_PATH",
    "REGISTER_PATH",
    "HeadCopyIncomparable",
    "RowsUnreadable",
    "as_calendar_date",
    "configured_spec_root",
    "first_seen_dates",
    "generate_register",
    "head_rows",
    "head_text",
    "live_todo_keys",
    "load_rows",
    "main",
    "register_key",
    "register_row_is_complete",
    "render_register",
    "todo_rows",
]


COVERAGE_PATH = Path("tests") / "heading-coverage.json"
REGISTER_PATH = Path("tests") / "heading-coverage-debt.json"


@dataclass(frozen=True, kw_only=True)
class RowsUnreadable:
    """A rows file that EXISTS and could not be turned into a comparable array.

    ABSENCE IS DELIBERATELY NOT HERE, and that omission is the whole shape of
    the split: a missing file is a real answer this register's adoption story
    depends on, so it rides the success track as `[]`.

    `reason` separates the two ways a PRESENT file defeats the read, because
    they want different responses. `rows-file-unreadable` is a broken checkout
    (a directory where the file belongs, a permission or I/O error);
    `rows-file-not-an-array` is a file whose CONTENT is not a registry —
    unparseable, or JSON that is not an array, which `_rows_from_text` already
    treats as one meaning.
    """

    reason: Literal["rows-file-unreadable", "rows-file-not-an-array"]
    path: str
    detail: str


@dataclass(frozen=True, kw_only=True)
class HeadCopyIncomparable:
    """`HEAD` carries no copy of a rows file this run can compare against.

    Every arm of `head_rows`' old `None`, which never meant "it was empty at
    HEAD": not a repository, no such blob, an unrunnable git, unparseable text,
    or JSON that is not an array.

    `reason` splits the two an operator acts on differently. `head-copy-absent`
    is git producing nothing at all — the adoption commit, or a tree with no
    history, both of which are ordinary and expected. `head-copy-not-an-array`
    is a committed blob that IS there and is not a registry, which is a defect
    in what was committed.
    """

    reason: Literal["head-copy-absent", "head-copy-not-an-array"]
    revision: str


def _rows_from_text(*, text: str) -> list[dict[str, object]] | None:
    """The JSON-array rows in `text`, or `None` when it is NOT a comparable array.

    `None` is reserved for "this is not a registry" — unparseable text, or JSON
    that is not an array. An array that happens to be empty is a real answer and
    comes back as `[]`, because "the register is empty" is this mechanism's
    terminal state and must never be spelled the same way as "I could not read
    it".
    """
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list):
        return None
    elements = cast("list[object]", parsed)
    return [cast("dict[str, object]", element) for element in elements if isinstance(element, dict)]


def load_rows(*, path: Path) -> IOResult[list[dict[str, object]], RowsUnreadable]:
    """The rows at `path`; an ABSENT file yields none, a present unreadable one FAILS.

    Absence is deliberately NOT an error here: a consumer that has not yet
    adopted the register has no file, and the check that calls this owns the
    verdict about what an empty register means. A file that is THERE and will
    not yield an array is the opposite — nothing about the debt can be placed
    from it, and answering `[]` let that reach the ratchet as "no rows".

    ONE `try` rather than `is_file()` then `read_text()`: the pre-check pair
    fused absent with unreadable (a DIRECTORY where the register belongs came
    back as `[]`) and left a TOCTOU second arm no test could reach. Splitting
    on `FileNotFoundError` separates them for free.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return IOSuccess([])
    except OSError as unreadable:
        return IOFailure(
            RowsUnreadable(
                reason="rows-file-unreadable", path=path.as_posix(), detail=str(unreadable)
            )
        )
    rows = _rows_from_text(text=text)
    if rows is None:
        return IOFailure(
            RowsUnreadable(
                reason="rows-file-not-an-array",
                path=path.as_posix(),
                detail="unparseable, or JSON that is not an array",
            )
        )
    return IOSuccess(rows)


def _git_stdout(*, cwd: Path, args: list[str]) -> str:
    """`git <args>` stdout under `cwd`; the EMPTY string when git produced nothing.

    Every `GIT_*` variable is stripped from the child's environment. The callers
    that matter here run inside a git commit hook, and git exports `GIT_DIR` /
    `GIT_INDEX_FILE` / `GIT_WORK_TREE` to its hooks; those OVERRIDE `cwd`, so an
    inherited environment would silently read a different repository.

    Failure is not distinguished from an empty answer, and deliberately so: a
    non-zero exit, an unrunnable git, and a `cwd` that is not a repository all
    print nothing, and empty text already fails to parse as an array in every
    caller. One response, one arm — a second spelling would only multiply
    diagnostics for one operator action.
    """
    git_env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    try:
        # S603/S607: argv is a fixed list of literal git args; no shell input.
        completed = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            check=False,
            env=git_env,
        )
    except OSError:
        return ""
    return completed.stdout


def head_text(*, cwd: Path, path: Path) -> IOResult[str, HeadCopyIncomparable]:
    """The TEXT of `path` as of `HEAD`; a FAILURE when HEAD carries no copy of it.

    The unparsed half of `head_rows` below, factored out because the v067
    spec-first direction compares a GOVERNED SPEC FILE across the same two
    revisions and a markdown file has no rows. Both callers must agree, to the
    character, on what "HEAD does not carry this" means — the `GIT_*`-stripped
    invocation and the one failure reason that covers every way git can decline
    — and a second spelling of it would let a spec file read as absent where a
    registry read as present.
    """
    revision = f"HEAD:{path.as_posix()}"
    text = _git_stdout(cwd=cwd, args=["show", revision])
    if not text:
        return IOFailure(HeadCopyIncomparable(reason="head-copy-absent", revision=revision))
    return IOSuccess(text)


def head_rows(*, cwd: Path, path: Path) -> IOResult[list[dict[str, object]], HeadCopyIncomparable]:
    """The rows of `path` as of `HEAD`; a FAILURE when HEAD carries no comparable copy.

    The failure track never means "it was empty at HEAD" — it means no
    comparison is possible (not a repository, no such blob, unparseable, not an
    array). The caller decides what an incomparable baseline costs, and every
    one of them fails closed; conflating the two would let "I could not tell
    what changed" pass as "nothing changed", which is precisely what a sentinel
    a caller may forget to test invites.
    """
    committed = head_text(cwd=cwd, path=path)
    if isinstance(committed, IOFailure):
        return committed
    rows = _rows_from_text(text=unsafe_perform_io(committed.unwrap()))
    if rows is None:
        return IOFailure(
            HeadCopyIncomparable(
                reason="head-copy-not-an-array", revision=f"HEAD:{path.as_posix()}"
            )
        )
    return IOSuccess(rows)


def _utc_calendar_date(*, committed_at: str) -> str:
    """A strict-ISO committer timestamp read as the UTC calendar date of its instant.

    ONE TIMEZONE BASIS, AND IT IS NOT THE COMMIT'S OWN. `%cs` renders the
    committer date in the commit's own timezone, so one instant yields two
    different calendar dates depending on the offset the committer's clock was
    set to — and a rebase-merge rewrites exactly that field. Measured 2026-10-14
    in livespec-orchestrator-beads-fabro: a PR whose commits carried
    2026-10-14T00:44:17Z passed with a register row dated 2026-10-14, the forge's
    rebase-merge re-stamped the UNCHANGED TREE under the web-flow committer's
    Pacific offset, the read turned that instant into 2026-10-13, and the
    committed tier convicted the date the PR had just certified. Every dispatch
    in that repository was refused by the green-master gate until a fix-forward
    landed, and any spec PR merging between 00:00Z and 07:00Z reaches it in any
    rebase-merge repository of the fleet.

    Normalizing to UTC makes the verdict a property of the TREE and the INSTANT
    rather than of whoever's clock recorded it. A timestamp that will not parse
    is a BUG in this invocation rather than an expected error, so it raises
    rather than riding a Result rail: `git log --format=%cI` emits a strict ISO
    8601 offset on every line it prints, and a caller that reached here with
    anything else has already read something that is not a git log.

    ...AND `%cI` SPELLS A UTC OFFSET TWO WAYS, DEPENDING ON THE HOST'S GIT.
    `Z` and `+00:00` are both strict ISO 8601, which is why the paragraph above
    was true and this read still crashed: git 2.51 renders a `+00:00` committer
    offset as a trailing `Z` (measured 2026-10-14 on hp-xubuntu, git 2.51.0 —
    `%cI` gave `2026-01-02T00:00:00Z` while `%ci` still gave `+0000`), and
    `datetime.fromisoformat` accepts that suffix only from Python 3.11 while
    this repository pins 3.10.16. Every read on such a host raised `ValueError`
    instead of dating the instant: `first_seen_dates` and both generator entry
    points crashed, 14 suite tests failed with them, and the committed and
    release tiers next door could neither convict an inflated date nor acquit
    one — a crashed gate rather than a verdict. CI never saw it, because the
    runner image carries an older git that still prints `+00:00`.

    So the suffix is normalized before parsing rather than left to the
    interpreter. The point is not merely to accept `Z`: it is that the date a
    verdict rests on must not depend on which git version printed the offset,
    any more than it may depend on which timezone the committer's clock was set
    to. Both are facts about the OBSERVER, and this function exists to keep
    them out of the answer.
    """
    # `fromisoformat` is left to parse the offset itself in every other case;
    # only the one spelling it cannot read on 3.10 is rewritten, and into the
    # exact offset `Z` abbreviates.
    instant = f"{committed_at[:-1]}+00:00" if committed_at.endswith("Z") else committed_at
    return datetime.fromisoformat(instant).astimezone(timezone.utc).date().isoformat()


def first_seen_dates(*, cwd: Path, spec_root: str | None = None) -> dict[tuple[str, str, str], str]:
    """Key → UTC calendar date of the earliest commit whose registry carried it as `TODO`.

    Walks `git log --reverse` over the live registry path only — the file has a
    short history (21 commits when this landed), so the per-commit blob read is
    cheap and exact. A key absent from the result was never a `TODO` in any
    committed blob; the caller supplies the fallback date rather than this
    function inventing one.

    The committer timestamp is read as `%cI` and normalized to UTC rather than
    taken as `%cs`, so the date this returns survives a rebase-merge — see
    `_utc_calendar_date` for the defect that bought the distinction.
    """
    configured_root = spec_root if spec_root is not None else configured_spec_root(cwd=cwd)
    log = _git_stdout(
        cwd=cwd,
        args=["log", "--reverse", "--format=%H %cI", "--", COVERAGE_PATH.as_posix()],
    )
    dates: dict[tuple[str, str, str], str] = {}
    for line in log.splitlines():
        revision, _, committed_at = line.partition(" ")
        committed_on = _utc_calendar_date(committed_at=committed_at)
        blob = _git_stdout(cwd=cwd, args=["show", f"{revision}:{COVERAGE_PATH.as_posix()}"])
        for row in todo_rows(rows=_rows_from_text(text=blob) or []):
            key = register_key(row=row, spec_root=configured_root)
            if key is not None and key not in dates:
                dates[key] = committed_on
    return dates


def _recorded_first_seen(*, rows: list[dict[str, object]]) -> dict[tuple[str, str, str], str]:
    """Key → the `first_seen` date ALREADY RECORDED for it in `rows`.

    Only a KEYED row carrying a non-empty string places anything. An unkeyed
    row has no identity to preserve a date for, and a `first_seen` that is not
    a non-empty string is not a date: carrying either forward would hand the
    release-tier age bound a value it cannot measure and call it preserved, so
    both defer to the git-derived answer — the same answer the generator gave
    before any date was recorded.
    """
    recorded: dict[tuple[str, str, str], str] = {}
    for row in rows:
        key = register_key(row=row)
        value = row.get("first_seen")
        if key is not None and isinstance(value, str) and value.strip():
            recorded[key] = value
    return recorded


def generate_register(
    *, cwd: Path, today: str
) -> IOResult[list[dict[str, object]], RowsUnreadable]:
    """The register the live registry under `cwd` implies, sorted by key.

    One row per `TODO` row in `tests/heading-coverage.json`, carrying the key,
    the owning `work_item` verbatim from the LIVE row, and the first-seen date
    ALREADY RECORDED for that key — falling back to the git-derived date, and
    then to `today`, only for a key the register does not yet carry. Sorting by
    key makes the output a pure function of the registry's CONTENT rather than
    of its file order, which is what lets a regeneration be compared
    byte-for-byte.

    THE RECORDED DATE WINS OVER GIT, per the module docstring's second half: a
    re-derived date moves LATER for the ordinary working-tree-authored row and
    resets the age bound's clock, so regeneration preserves rather than
    recomputes. The owner is deliberately NOT preserved — it is resynchronized
    from the live row on every run.

    The failure track is `load_rows`' verbatim, PROPAGATED rather than
    absorbed, and that is the point of converting it: a registry that will not
    parse used to generate an EMPTY register, which `main()` then wrote over
    the real one. A generator whose output IS the ratchet's baseline must
    refuse rather than bank a shrink nobody made. The REGISTER is now read on
    the same track and for the mirror reason: read as "nothing is recorded", an
    unparseable register would re-date every existing row from git in one
    silent overwrite.
    """
    loaded = load_rows(path=cwd / COVERAGE_PATH)
    if isinstance(loaded, IOFailure):
        return loaded
    previous = load_rows(path=cwd / REGISTER_PATH)
    if isinstance(previous, IOFailure):
        return previous
    recorded = _recorded_first_seen(rows=unsafe_perform_io(previous.unwrap()))
    rows = todo_rows(rows=unsafe_perform_io(loaded.unwrap()))
    spec_root = configured_spec_root(cwd=cwd)
    dates = first_seen_dates(cwd=cwd, spec_root=spec_root)
    generated: list[tuple[tuple[str, str, str], dict[str, object]]] = []
    for row in rows:
        key = register_key(row=row, spec_root=spec_root)
        if key is None:
            continue
        work_item = row.get("work_item")
        generated.append(
            (
                key,
                {
                    "spec_root": key[0],
                    "spec_file": key[1],
                    "heading": key[2],
                    "work_item": work_item if isinstance(work_item, str) else "",
                    "first_seen": recorded.get(key, dates.get(key, today)),
                },
            )
        )
    return IOSuccess([row for _key, row in sorted(generated, key=lambda pair: pair[0])])


def render_register(*, rows: list[dict[str, object]]) -> str:
    """The register's on-disk bytes for `rows` — stable, diffable, newline-terminated."""
    return json.dumps(rows, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    """Regenerate `tests/heading-coverage-debt.json` from the live registry at cwd.

    A registry the generator could not read takes the ONE non-zero exit, and
    the register file is left UNTOUCHED. Writing what an unreadable registry
    implies would render `[]` — an empty baseline over the real one, which is
    the whole debt banked as resolved in a single silent overwrite.
    """
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    cwd = Path.cwd()
    today = datetime.now(timezone.utc).date().isoformat()
    generated = generate_register(cwd=cwd, today=today)
    if isinstance(generated, IOFailure):
        unreadable = unsafe_perform_io(generated.failure())
        structlog.get_logger("heading_coverage_debt").error(
            "the live heading-coverage registry is not readable — the debt register was "
            "NOT regenerated, because generating it from an unreadable registry would "
            "write an empty baseline over the real one",
            path=unreadable.path,
            reason=unreadable.reason,
            detail=unreadable.detail,
            failing=True,
        )
        return 1
    rows = unsafe_perform_io(generated.unwrap())
    _ = (cwd / REGISTER_PATH).write_text(render_register(rows=rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
