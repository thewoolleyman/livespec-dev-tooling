"""_heading_coverage_age_bound — the RELEASE-TIER age bound on heading-coverage debt.

Charter D5 of plan `fleet-heading-coverage-convergence` (epic
`livespec-dev-tooling-0bse`), ratified into this repository's
`SPECIFICATION/non-functional-requirements.md` at v064:

> A `TODO` older than the repository's configured age bound (default 30 days
> from first-seen) MUST fail the release tier. Liveness and age are evaluated
> ONLY at the release tier, so no per-commit verdict depends on mutable
> external state.

This is the fifth direction of `heading_coverage_debt_register`, and it lives
in a private sibling for the same reason the reason guard does: it is
self-contained — a config read, a date subtraction, a tier decision and two
diagnostics — and folding it into the parent would push that file into the
LLOC soft band for no cohesion gain.

AGE IS MEASURED FROM THE REGISTER, NOT FROM A DECLARATION. `first_seen` is the
committer date the ratchet's generator read out of git (charter D3): the
earliest commit whose `tests/heading-coverage.json` blob already carried the
row as a `TODO`. That is evidence rather than an assertion, which is the
property that lets a bound rest on it at all — an author cannot restart the
clock without rewriting history, and a hand-edited register is the one thing
the ratchet already refuses.

WHY RELEASE-TIER-ONLY, AND WHY THE LEVER IS THE ONE THAT ALREADY EXISTS. Age
depends on the CLOCK, which no commit controls: judged per commit it could
turn master red with no landed change, which livespec core's
`.ai/ci-gate-discipline.md` treats as a real broken state rather than a
notification. So the direction is armed by
`LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST` — `no_todo_registry`'s
existing release lever, deliberately NOT a second knob. The ratified clause
pairs the two in one sentence ("Liveness and age are evaluated ONLY at the
release tier"), and one spelling of "this is the release context" is what
keeps them from drifting apart; a lever of its own would be the severity knob
this repository's `CLAUDE.md` forbids.

Unarmed, every overdue row is REPORTED at warning level naming that lever and
the direction contributes no exit code. That is also what makes it landable:
this repository's own register carries rows first seen 2026-05-27, so an
unconditional verdict would red the tree on the very commit that adds the
check — the arm-ahead-of-adoption trap `CLAUDE.md` records.

AN UNMEASURABLE `first_seen` IS CONVICTED, NOT SKIPPED. A register entry whose
`first_seen` is not an ISO calendar date has no age at all, and "I cannot tell
how old this is" must never be spelled the same way as "it is young". It fires
its own diagnostic at the same tier.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in this tree. Diagnostics flow through
structlog (JSON to stderr) under the PARENT's `heading_coverage_debt_register`
logger name, because they are that check's findings; the vendored copy is
added to `sys.path` at module import time.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

# Carried rather than inherited from an importer: without it the vendored
# `structlog` resolves only because some module up the import chain happens to
# carry the preamble, which is a property of the caller rather than of this
# file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

from livespec_dev_tooling.config import (  # noqa: E402
    load_heading_coverage_todo_age_bound_days,
)
from livespec_dev_tooling.heading_coverage_debt import (  # noqa: E402
    register_key,
    todo_rows,
)

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `heading_coverage_debt_register.py`, so pyright's per-file analysis
# does not flag them unused across the package boundary.
__all__: list[str] = [
    "DEFAULT_AGE_BOUND_DAYS",
    "AgeFinding",
    "age_bound_days",
    "age_findings",
    "judged_age_findings",
    "report_age_violations",
]


DEFAULT_AGE_BOUND_DAYS = 30
_FAIL_ENV_VAR = "LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST"

_MESSAGES = {
    "todo_past_age_bound": (
        'heading-coverage.json row has `test: "TODO"` whose debt-register `first_seen` is '
        "older than this repository's configured age bound — per livespec-dev-tooling's "
        'SPECIFICATION/non-functional-requirements.md §"Scenario-tier coverage" a `TODO` is '
        "a TRANSITION, and this one has outlived it. Resolve the heading to a real test at "
        "the required tier, or remove the row"
    ),
    "todo_first_seen_unmeasurable": (
        "heading-coverage-debt.json entry carries a `first_seen` that is not an ISO "
        "calendar date, so the row has no measurable age — regenerate the register from "
        "the live registry (`livespec_dev_tooling.heading_coverage_debt`) rather than "
        "editing it by hand"
    ),
}


@dataclass(frozen=True, kw_only=True)
class AgeFinding:
    """One register entry the release tier judges on its age.

    `age_days` is `None` exactly when `code` is `todo_first_seen_unmeasurable`:
    there is no number to report, which is the whole of that finding.
    """

    code: str
    key: tuple[str, str, str]
    first_seen: str
    bound_days: int
    age_days: int | None


def age_bound_days(*, repo_root: Path) -> int:
    """The repository's configured bound in days; the ratified default when undeclared.

    The default lives HERE rather than in the loader so an absent key and a
    declared `30` reach the check as the same number by the same path.
    """
    declared = load_heading_coverage_todo_age_bound_days(repo_root=repo_root)
    if declared is None:
        return DEFAULT_AGE_BOUND_DAYS
    return declared


def _as_calendar_date(*, value: object) -> date | None:
    """`value` read as an ISO calendar date; `None` when it is not one.

    `None` is the UNMEASURABLE answer, and its caller convicts on it. It is
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


def _live_todo_keys(*, registry_rows: list[dict[str, object]]) -> set[tuple[str, str, str]]:
    """The keys of every live `TODO` row — the rows an age verdict may concern."""
    keys: set[tuple[str, str, str]] = set()
    for row in todo_rows(rows=registry_rows):
        key = register_key(row=row)
        if key is not None:
            keys.add(key)
    return keys


def age_findings(
    *,
    registry_rows: list[dict[str, object]],
    register_rows: list[dict[str, object]],
    repo_root: Path,
    today: date,
) -> list[AgeFinding]:
    """Every register entry whose live `TODO` row has outlived the bound.

    Scoped to keys the registry still carries as `TODO`, because a register
    entry with no live row is a `stale_register_entry` the parent already
    convicts, and a second conviction would report one defect as two. An
    unkeyed entry is likewise not this direction's business: without a key it
    has no row to be the age OF.

    The comparison is strictly `>`, so a row first seen exactly `bound_days`
    ago still passes — the bound is the age a `TODO` may REACH, and reading it
    as `>=` would shorten every repository's stated window by a day.
    """
    bound = age_bound_days(repo_root=repo_root)
    live = _live_todo_keys(registry_rows=registry_rows)
    findings: list[AgeFinding] = []
    for row in register_rows:
        key = register_key(row=row)
        if key is None or key not in live:
            continue
        declared = row.get("first_seen")
        first_seen = _as_calendar_date(value=declared)
        if first_seen is None:
            findings.append(
                AgeFinding(
                    code="todo_first_seen_unmeasurable",
                    key=key,
                    first_seen=str(declared),
                    bound_days=bound,
                    age_days=None,
                )
            )
            continue
        age = (today - first_seen).days
        if age > bound:
            findings.append(
                AgeFinding(
                    code="todo_past_age_bound",
                    key=key,
                    first_seen=first_seen.isoformat(),
                    bound_days=bound,
                    age_days=age,
                )
            )
    return sorted(findings, key=lambda finding: finding.key)


def _fields(*, finding: AgeFinding) -> dict[str, object]:
    """The diagnostic fields every spelling of this finding carries.

    Shared so a warn-only run and an armed one are read the same way by an
    operator, differing only in `failing` and in whether the lever explains the
    leniency.
    """
    return {
        "spec_root": finding.key[0],
        "spec_file": finding.key[1],
        "heading": finding.key[2],
        "finding": finding.code,
        "first_seen": finding.first_seen,
        "age_days": finding.age_days,
        "age_bound_days": finding.bound_days,
    }


def report_age_violations(*, findings: list[AgeFinding]) -> None:
    """Report every JUDGED finding at error level — the caller owns the exit code."""
    log = structlog.get_logger("heading_coverage_debt_register")
    for finding in findings:
        log.error(_MESSAGES[finding.code], **_fields(finding=finding), failing=True)


def judged_age_findings(
    *,
    registry_rows: list[dict[str, object]],
    register_rows: list[dict[str, object]],
    repo_root: Path,
) -> list[AgeFinding]:
    """The age findings this run JUDGES; outside the release tier, none of them.

    Unarmed, every finding is reported at warning level naming the lever that
    arms it, and the direction contributes no exit code. That is the per-commit
    tier, and it is why landing this direction reddens no repository on the
    commit that adopts it.
    """
    log = structlog.get_logger("heading_coverage_debt_register")
    findings = age_findings(
        registry_rows=registry_rows,
        register_rows=register_rows,
        repo_root=repo_root,
        today=datetime.now(timezone.utc).date(),
    )
    if os.environ.get(_FAIL_ENV_VAR):
        return findings
    for finding in findings:
        log.warning(
            _MESSAGES[finding.code],
            **_fields(finding=finding),
            fail_env_var=_FAIL_ENV_VAR,
            failing=False,
        )
    return []
