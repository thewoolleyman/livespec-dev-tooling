"""heading_coverage_debt — the shrink-only heading-coverage debt register.

Charter D3 of plan `fleet-heading-coverage-convergence` (epic
`livespec-dev-tooling-0bse`), ratified into this repository's
`SPECIFICATION/non-functional-requirements.md` at v064:

> Every `TODO` row MUST appear in the repository's shrink-only
> heading-coverage debt register (`tests/heading-coverage-debt.json`, keyed
> by `(spec_root, spec_file, heading)` with the owning `work_item` and the
> row's first-seen date). [...] The register is generated mechanically from
> the live file at adoption, never authored by hand.

This module is the register's shared VOCABULARY (its path, its key, its
row schema, and how a `HEAD` copy is read) plus the MECHANICAL GENERATOR
that produces it. The verdict lives next door in
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

FIRST-SEEN IS READ FROM GIT, NOT DECLARED. `first_seen` is the committer
date (`%cs`, `YYYY-MM-DD`) of the earliest commit whose
`tests/heading-coverage.json` blob already carried the row as a `TODO`. It
is evidence rather than an assertion, which is what lets the release-tier
age bound (charter D5, a sibling work-item) rest on it. A key git history
cannot place — a row added in the working tree, or a registry with no
history yet — falls back to the caller-supplied `today`, so generation never
invents a date that looks measured.

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

__all__: list[str] = [
    "COVERAGE_PATH",
    "REGISTER_PATH",
    "HeadCopyIncomparable",
    "RowsUnreadable",
    "first_seen_dates",
    "generate_register",
    "head_rows",
    "load_rows",
    "main",
    "register_key",
    "register_row_is_complete",
    "render_register",
    "todo_rows",
]


COVERAGE_PATH = Path("tests") / "heading-coverage.json"
REGISTER_PATH = Path("tests") / "heading-coverage-debt.json"

_KEY_FIELDS = (
    "spec_root",
    "spec_file",
    "heading",
)
_REQUIRED_FIELDS = (
    "spec_root",
    "spec_file",
    "heading",
    "work_item",
    "first_seen",
)


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


def register_key(*, row: dict[str, object]) -> tuple[str, str, str] | None:
    """The `(spec_root, spec_file, heading)` key of `row`; `None` when unkeyed.

    A row missing any of the three, or carrying a non-string in one of them, has
    no identity the ratchet can track on either side of the comparison, so it is
    reported as unkeyed rather than silently keyed on a coerced value.
    """
    spec_root = row.get("spec_root")
    spec_file = row.get("spec_file")
    heading = row.get("heading")
    if not (isinstance(spec_root, str) and isinstance(spec_file, str) and isinstance(heading, str)):
        return None
    return (spec_root, spec_file, heading)


def register_row_is_complete(*, row: dict[str, object]) -> bool:
    """Whether `row` carries every field the ratified register schema requires.

    The key three plus `work_item` (who owes the test) and `first_seen` (when
    the debt started). A register row without those last two is a row the age
    bound and the liveness gate cannot judge — it would be debt with no owner
    and no clock.
    """
    for field in _REQUIRED_FIELDS:
        value = row.get(field)
        if not isinstance(value, str) or not value.strip():
            return False
    return True


def todo_rows(*, rows: list[dict[str, object]]) -> list[dict[str, object]]:
    """The `test: "TODO"` rows among `rows` — the debt the register tracks."""
    return [row for row in rows if row.get("test") == "TODO"]


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


def head_rows(*, cwd: Path, path: Path) -> IOResult[list[dict[str, object]], HeadCopyIncomparable]:
    """The rows of `path` as of `HEAD`; a FAILURE when HEAD carries no comparable copy.

    The failure track never means "it was empty at HEAD" — it means no
    comparison is possible (not a repository, no such blob, unparseable, not an
    array). The caller decides what an incomparable baseline costs, and every
    one of them fails closed; conflating the two would let "I could not tell
    what changed" pass as "nothing changed", which is precisely what a sentinel
    a caller may forget to test invites.
    """
    revision = f"HEAD:{path.as_posix()}"
    text = _git_stdout(cwd=cwd, args=["show", revision])
    if not text:
        return IOFailure(HeadCopyIncomparable(reason="head-copy-absent", revision=revision))
    rows = _rows_from_text(text=text)
    if rows is None:
        return IOFailure(HeadCopyIncomparable(reason="head-copy-not-an-array", revision=revision))
    return IOSuccess(rows)


def first_seen_dates(*, cwd: Path) -> dict[tuple[str, str, str], str]:
    """Key → committer date of the earliest commit whose registry carried it as `TODO`.

    Walks `git log --reverse` over the live registry path only — the file has a
    short history (21 commits when this landed), so the per-commit blob read is
    cheap and exact. A key absent from the result was never a `TODO` in any
    committed blob; the caller supplies the fallback date rather than this
    function inventing one.
    """
    log = _git_stdout(
        cwd=cwd,
        args=["log", "--reverse", "--format=%H %cs", "--", COVERAGE_PATH.as_posix()],
    )
    dates: dict[tuple[str, str, str], str] = {}
    for line in log.splitlines():
        revision, _, committed_at = line.partition(" ")
        blob = _git_stdout(cwd=cwd, args=["show", f"{revision}:{COVERAGE_PATH.as_posix()}"])
        for row in todo_rows(rows=_rows_from_text(text=blob) or []):
            key = register_key(row=row)
            if key is not None and key not in dates:
                dates[key] = committed_at
    return dates


def generate_register(
    *, cwd: Path, today: str
) -> IOResult[list[dict[str, object]], RowsUnreadable]:
    """The register the live registry under `cwd` implies, sorted by key.

    One row per `TODO` row in `tests/heading-coverage.json`, carrying the key,
    the owning `work_item` verbatim, and the git-derived first-seen date
    (falling back to `today` for a key no committed blob carries yet). Sorting
    by key makes the output a pure function of the registry's CONTENT rather
    than of its file order, which is what lets a regeneration be compared
    byte-for-byte.

    The failure track is `load_rows`' verbatim, PROPAGATED rather than
    absorbed, and that is the point of converting it: a registry that will not
    parse used to generate an EMPTY register, which `main()` then wrote over
    the real one. A generator whose output IS the ratchet's baseline must
    refuse rather than bank a shrink nobody made.
    """
    loaded = load_rows(path=cwd / COVERAGE_PATH)
    if isinstance(loaded, IOFailure):
        return loaded
    rows = todo_rows(rows=unsafe_perform_io(loaded.unwrap()))
    dates = first_seen_dates(cwd=cwd)
    generated: list[tuple[tuple[str, str, str], dict[str, object]]] = []
    for row in rows:
        key = register_key(row=row)
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
                    "first_seen": dates.get(key, today),
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
