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

Output discipline: `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned here. This module's `main()` WRITES THE
REGISTER FILE and emits nothing, so it needs no diagnostic stream at all.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

__all__: list[str] = [
    "COVERAGE_PATH",
    "REGISTER_PATH",
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


def load_rows(*, path: Path) -> list[dict[str, object]]:
    """The rows at `path`; an absent, unparseable, or non-array file yields none.

    Absence is deliberately NOT an error here: a consumer that has not yet
    adopted the register has no file, and the check that calls this owns the
    verdict about what an empty register means.
    """
    if not path.is_file():
        return []
    rows = _rows_from_text(text=path.read_text(encoding="utf-8"))
    if rows is None:
        return []
    return rows


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


def head_rows(*, cwd: Path, path: Path) -> list[dict[str, object]] | None:
    """The rows of `path` as of `HEAD`, or `None` when HEAD carries no comparable copy.

    `None` never means "it was empty at HEAD" — it means no comparison is
    possible (not a repository, no such blob, unparseable, not an array). The
    caller decides what an incomparable baseline costs; conflating the two would
    let "I could not tell what changed" pass as "nothing changed".
    """
    return _rows_from_text(text=_git_stdout(cwd=cwd, args=["show", f"HEAD:{path.as_posix()}"]))


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


def generate_register(*, cwd: Path, today: str) -> list[dict[str, object]]:
    """The register the live registry under `cwd` implies, sorted by key.

    One row per `TODO` row in `tests/heading-coverage.json`, carrying the key,
    the owning `work_item` verbatim, and the git-derived first-seen date
    (falling back to `today` for a key no committed blob carries yet). Sorting
    by key makes the output a pure function of the registry's CONTENT rather
    than of its file order, which is what lets a regeneration be compared
    byte-for-byte.
    """
    rows = todo_rows(rows=load_rows(path=cwd / COVERAGE_PATH))
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
    return [row for _key, row in sorted(generated, key=lambda pair: pair[0])]


def render_register(*, rows: list[dict[str, object]]) -> str:
    """The register's on-disk bytes for `rows` — stable, diffable, newline-terminated."""
    return json.dumps(rows, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    """Regenerate `tests/heading-coverage-debt.json` from the live registry at cwd."""
    cwd = Path.cwd()
    today = datetime.now(timezone.utc).date().isoformat()
    rows = generate_register(cwd=cwd, today=today)
    _ = (cwd / REGISTER_PATH).write_text(render_register(rows=rows), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
