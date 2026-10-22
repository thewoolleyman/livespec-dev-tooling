"""The IDENTITY and SCHEMA of a heading-coverage debt row.

Split out of `heading_coverage_debt` by cohesion: everything here answers a
question about a SINGLE ROW held in memory — what key identifies it, whether it
carries the fields the ratified register schema requires, whether it is debt at
all, and whether its recorded date is measurable. Nothing here reads the
registry, the register, or git history; the one file this module opens is the
consuming repository's `.livespec.jsonc`, and it opens it for exactly one
reason, below. Its sibling owns the row SOURCES (the working tree and `HEAD`)
and the mechanical generator that writes the register.

THE KEY IS THE RATIFIED TRIPLE, WHATEVER SHAPE THE REGISTRY ROW TAKES. This
repository's `SPECIFICATION/non-functional-requirements.md`, where it ratifies
scenario-tier coverage, keys the register by `(spec_root, spec_file, heading)`,
and that is not negotiable: the register is the thing every direction of the
ratchet compares against, so a second key schema would be a second register.
What IS negotiable is how a REGISTRY row is read into that triple, because the
specification does not fix the registry row's own field names and the fleet's
repositories do not spell them the same way:

- A row carrying `spec_root`, `spec_file` and `heading` is keyed on those three
  verbatim — the shape this repository and most consumers author.
- A SCENARIO-SHAPED row carries `scenario` and `scenario_file` instead, because
  its repository's own coverage checker requires those names (console's
  `crates/console-spec-check` `parse_entry` is the measured case). Its triple is
  DERIVED: `spec_file` from `scenario_file`, `heading` from `scenario` prefixed
  by `## `, and `spec_root` from the consuming repository's configured
  `spec_root` — the one field a scenario row deliberately does not carry,
  because it is a property of the repository rather than of the row.

That derivation is why this module reads `.livespec.jsonc` at all, and it is
read rather than assumed: a repository that declares no root, or whose
configuration cannot be parsed, leaves its scenario rows UNKEYED, which the
ratchet already ignores. Inventing a root would key a row against a
specification tree that may not exist, and the resulting register entry would
be indistinguishable from a real one.

WHY `as_calendar_date` AND `live_todo_keys` ARE SHARED RATHER THAN PRIVATE to
the direction that first needed them — the paragraph this module inherits from
its sibling, because it is the design record for two of the functions moved
here. Both now have two readers — the release-tier age bound and the
committed-tier date comparison — and the two MUST agree, to the character, on
which `first_seen` values are measurable and which registry rows a verdict may
concern. Two copies of that judgement would let a row be unmeasurable to one
reader and measurable to the other, which is an escape hatch rather than a
disagreement: the row would be convicted by neither.

Output discipline: `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned here. This module emits no diagnostics at
all — every function returns its non-answer (`None`, `False`) to a caller that
owns the verdict.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import cast

# Carried rather than inherited from an importer: without it the vendored
# `jsoncomment` resolves only because some module up the import chain happens
# to carry the preamble, which is a property of the caller rather than of this
# file.
_VENDOR_DIR = Path(__file__).resolve().parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import jsoncomment  # noqa: E402  — vendor-path-aware import after sys.path insert.

__all__: list[str] = [
    "as_calendar_date",
    "configured_spec_root",
    "live_todo_keys",
    "register_key",
    "register_row_is_complete",
    "todo_rows",
]


_LIVESPEC_CONFIG_PATH = Path(".livespec.jsonc")

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


def configured_spec_root(*, cwd: Path) -> str | None:
    """The consuming repository's configured `spec_root`, when it is readable.

    Scenario-shaped registry rows deliberately carry no `spec_root`: their
    coverage key belongs under the consuming repository's configured root.
    Existing triple-shaped rows do not depend on this read, so an unavailable
    or malformed livespec configuration leaves only those scenario rows
    unkeyed for the ratchet to ignore alongside other unkeyed entries.
    """
    try:
        source = (cwd / _LIVESPEC_CONFIG_PATH).read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = jsoncomment.loads(source)
    except (TypeError, ValueError):
        return None
    # A document that PARSES but is not an object declares no keys at all — an
    # answer, not a parse failure.
    if not isinstance(parsed, dict):
        return None
    # The `cast` is the single typed parse boundary, the same one
    # `cross_repo/_pin_single_file_formats.walk_livespec_jsonc` draws: the
    # parsed document is `Any`, so casting to `dict[str, object]` AFTER the
    # `isinstance` guard types `.get` and leaves the value to narrow from
    # `object` through the `isinstance(..., str)` guard below.
    spec_root = cast("dict[str, object]", parsed).get("spec_root")
    return spec_root if isinstance(spec_root, str) else None


def register_key(
    *, row: dict[str, object], spec_root: str | None = None
) -> tuple[str, str, str] | None:
    """The ratified triple for an explicit or scenario-shaped registry row.

    A row missing any of the three, or carrying a non-string in one of them, has
    no identity the ratchet can track on either side of the comparison, so it is
    reported as unkeyed rather than silently keyed on a coerced value. A
    scenario-shaped `TODO` instead derives that same triple from its
    `scenario_file`, its `scenario` prefixed by `## `, and the consuming
    repository's configured `spec_root`.

    `spec_root` is the caller's already-resolved root. It defaults to resolving
    it from the repository at the process cwd, which is where every caller that
    omits it reads its own tree from: each check's `main()` opens with
    `cwd = Path.cwd()`, so the omitted argument and the explicit one name the
    same repository rather than two.
    """
    row_spec_root = row.get("spec_root")
    spec_file = row.get("spec_file")
    heading = row.get("heading")
    if isinstance(row_spec_root, str) and isinstance(spec_file, str) and isinstance(heading, str):
        return (row_spec_root, spec_file, heading)
    configured_root = spec_root if spec_root is not None else configured_spec_root(cwd=Path.cwd())
    scenario = row.get("scenario")
    scenario_file = row.get("scenario_file")
    if not (
        isinstance(configured_root, str)
        and isinstance(scenario, str)
        and isinstance(scenario_file, str)
    ):
        return None
    return (configured_root, scenario_file, f"## {scenario}")


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


def as_calendar_date(*, value: object) -> date | None:
    """`value` read as an ISO calendar date; `None` when it is not one.

    `None` is the UNMEASURABLE answer, and its callers convict on it. It is
    never "assume today": a row whose date cannot be read would then be born
    young on every run, and the bound would silently stop applying to exactly
    the rows whose register entry is malformed.
    """
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None


def live_todo_keys(*, registry_rows: list[dict[str, object]]) -> set[tuple[str, str, str]]:
    """The keys of every live `TODO` row — the rows a date or age verdict may concern."""
    keys: set[tuple[str, str, str]] = set()
    for row in todo_rows(rows=registry_rows):
        key = register_key(row=row)
        if key is not None:
            keys.add(key)
    return keys
