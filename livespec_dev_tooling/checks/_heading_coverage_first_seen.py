"""_heading_coverage_first_seen — the first-seen DATE directions of the debt ratchet.

Ratified into this repository's `SPECIFICATION/non-functional-requirements.md`
at v067, among the requirements governing the repository's testing approach and
the transitional heading-coverage debt it tracks:

> Once recorded, `first_seen` MUST NOT move later, enforced in the authoring
> tier by comparison with `HEAD` [...] After commit, an admitted row's
> `first_seen` MUST NOT be later than the committer date of the earliest
> commit whose coverage registry carries that key as TODO; pre-push and CI
> MUST reject a later date using repository history, and unavailable evidence
> MUST refuse validation rather than establish eligibility.

WHY A DATE DIRECTION EXISTS AT ALL. Every other direction of
`heading_coverage_debt_register` judges the SET of registered keys, and a
moved date changes no key: the register neither grows nor shrinks, the schema
holds, every live `TODO` stays registered. What moves is the clock the
release-tier age bound measures from — so moving a date forward launders debt
that is already running into fresh debt, resolving nothing, and the four
set-shaped directions are all blind to it.

ONE TIER, ONE EVIDENCE, AND THE SPLIT IS NOT A CONVENIENCE. The two tiers rest
on different evidence because only one of them has evidence to rest on:

- AUTHORING (the `LIVESPEC_SCOPE_HEADING_COVERAGE_DEBT_TO_HEAD_DIFF` lever,
  set by the pre-commit subset) compares against the date `HEAD`'s own
  register records. The commit carrying this row's registry `TODO` does not
  exist yet, so there is no committer date to read; demanding one would refuse
  the very spec-first admission the ratified clause permits.
- COMMITTED (pre-push and CI, where the lever is unset) compares against the
  committer date of the earliest commit whose `tests/heading-coverage.json`
  blob already carried the key as a `TODO`. That is the same evidence the
  generator reads, and after the commit it is finally answerable.

Neither tier runs the other's comparison. An author is judged on what they can
answer for; a landed tree is judged on what the repository can prove.

ONLY LATER IS FORBIDDEN — EARLIER IS LEGITIMATE AND ORDINARY. A row authored
in a working tree is dated the day it was authored and committed a day or more
after, so a correct recorded date PRECEDES its committer-date evidence; that
is the shape the generator deliberately preserves. It is also what a SHALLOW
clone looks like, because truncating history moves the earliest VISIBLE
carrying commit forward. A direction that refused any mismatch would convict a
repository for how it was cloned, and would block the correction of a date that
was recorded too late — the inflation it exists to remove.

UNAVAILABLE EVIDENCE REFUSES, IT DOES NOT PASS. When no commit in the visible
history carries the key as a `TODO` there is no committer date to judge
against. "I could not establish the date" must never be spelled the same way
as "the date is fine": an unanswerable comparison that passed would make every
inflated date launderable by removing its evidence, which is the cheaper
attack than inflating the date in the first place.

AN UNMEASURABLE RECORDED DATE DRAWS NOTHING HERE. A `first_seen` that is not
an ISO calendar date has no position on a timeline, so neither comparison is
defined for it — and the release-tier age bound already convicts it by name
(`todo_first_seen_unmeasurable`). Reporting it twice would send an author
looking for a second problem that does not exist. An unkeyed entry is likewise
not this module's business: without a key it has no identity to compare across
the two sides.

WHY A SIBLING MODULE. The same cohesion split as `_heading_coverage_age_bound`
next door, and for the same two reasons: these directions are self-contained —
two evidence reads, two date comparisons, one diagnostic shape — and folding
them into the parent would push that file past the LLOC hard ceiling for no
cohesion gain.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in this tree. Diagnostics flow through
structlog (JSON to stderr) under the PARENT's `heading_coverage_debt_register`
logger name, because they are that check's findings; the vendored copy is
added to `sys.path` at module import time.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

# Carried rather than inherited from an importer: without it the vendored
# `returns` / `structlog` resolve only because some module up the import chain
# happens to carry the preamble, which is a property of the caller rather than
# of this file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.heading_coverage_debt import (  # noqa: E402
    REGISTER_PATH,
    as_calendar_date,
    first_seen_dates,
    head_rows,
    live_todo_keys,
    register_key,
)

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `heading_coverage_debt_register.py`, so pyright's per-file analysis
# does not flag them unused across the package boundary.
__all__: list[str] = [
    "FirstSeenFinding",
    "judged_first_seen_findings",
    "report_first_seen_violations",
]


_SPEC_CITATION = (
    'livespec-dev-tooling\'s SPECIFICATION/non-functional-requirements.md §"Testing approach"'
)

_MESSAGES = {
    "first_seen_moved_later": (
        "heading-coverage-debt.json entry moves a `first_seen` LATER than the date HEAD "
        f"records for the same key — per {_SPEC_CITATION} a recorded first-seen date may be "
        "corrected EARLIER but never moved forward, because moving it forward restarts the "
        "release-tier age bound's clock on debt that is already running. Regenerate the "
        "register from the live registry (`livespec_dev_tooling.heading_coverage_debt`) "
        "rather than editing the date by hand"
    ),
    "first_seen_after_earliest_todo_commit": (
        "heading-coverage-debt.json entry records a `first_seen` LATER than the committer "
        "date of the earliest commit whose heading-coverage registry already carried this "
        f"key as a `TODO` — per {_SPEC_CITATION} the recorded date is EVIDENCE, and this one "
        "claims age the repository's own history does not owe. The `evidence` field carries "
        "the committer date it was judged against"
    ),
    "first_seen_evidence_unavailable": (
        "heading-coverage-debt.json entry carries registered debt this run cannot validate: "
        "no commit in the visible history carries its key as a `TODO` in the heading-coverage "
        "registry, so there is no committer date to judge the recorded date against. Per "
        f"{_SPEC_CITATION} evidence that cannot be read REFUSES validation rather than "
        "establishing it — commit the registry, or restore the history that carries it"
    ),
}


@dataclass(frozen=True, kw_only=True)
class FirstSeenFinding:
    """One register entry whose recorded date fails its tier's evidence.

    `evidence` is the date the recorded value was judged AGAINST, and it is
    `None` exactly when `code` is `first_seen_evidence_unavailable`: there was
    no date to judge against, which is the whole of that finding.
    """

    code: str
    key: tuple[str, str, str]
    first_seen: str
    evidence: str | None


def _recorded_dates(*, rows: list[dict[str, object]]) -> dict[tuple[str, str, str], date]:
    """Key → recorded `first_seen` read as a calendar date, for every COMPARABLE row.

    A row is comparable only when it is keyed AND its date is readable. An
    unkeyed row has no identity to place on either side of a comparison, and a
    `first_seen` that is not an ISO calendar date has no position on a
    timeline; dropping both is what keeps this module from re-convicting
    defects the schema direction and the age bound already name.
    """
    dates: dict[tuple[str, str, str], date] = {}
    for row in rows:
        key = register_key(row=row)
        recorded = as_calendar_date(value=row.get("first_seen"))
        if key is not None and recorded is not None:
            dates[key] = recorded
    return dates


def _authored_findings(
    *, cwd: Path, register_rows: list[dict[str, object]]
) -> list[FirstSeenFinding]:
    """Register entries whose recorded date is LATER than the one `HEAD` records.

    Judged over the INTERSECTION of the two sides, which is the honest universe
    rather than a convenience: a date can only have MOVED if `HEAD` records one
    to move it from. A key `HEAD`'s register does not carry is a newly admitted
    row, whose date this tier has no prior value to compare and whose admission
    the sibling directions own.

    An incomparable `HEAD` register — the adoption commit, or a tree with no
    history — decides nothing, exactly as the shrink-only direction does not.
    The caller has already said so once (`baseline_unreadable`) off the same
    read, and a second voice for one operator action would only multiply the
    diagnostic.
    """
    baseline = head_rows(cwd=cwd, path=REGISTER_PATH)
    if isinstance(baseline, IOFailure):
        return []
    before = _recorded_dates(rows=unsafe_perform_io(baseline.unwrap()))
    now = _recorded_dates(rows=register_rows)
    findings: list[FirstSeenFinding] = []
    for key in sorted(set(now) & set(before)):
        if now[key] <= before[key]:
            continue
        findings.append(
            FirstSeenFinding(
                code="first_seen_moved_later",
                key=key,
                first_seen=now[key].isoformat(),
                evidence=before[key].isoformat(),
            )
        )
    return findings


def _committed_findings(
    *,
    cwd: Path,
    registry_rows: list[dict[str, object]],
    register_rows: list[dict[str, object]],
) -> list[FirstSeenFinding]:
    """Registered debt whose recorded date history refuses, or cannot speak to.

    Scoped to keys the registry still carries as a live `TODO`, because a
    register entry with no live row is a `stale_register_entry` the parent
    already convicts and a second conviction would report one defect as two.

    The history walk is skipped entirely when nothing is left to judge, and
    that is load-bearing rather than an optimisation: a repository that has
    reached zero debt — the ratchet's own success condition, and the state this
    repository is in — must not be asked for evidence it has no reason to hold.
    """
    live = live_todo_keys(registry_rows=registry_rows)
    judged = {
        key: recorded
        for key, recorded in _recorded_dates(rows=register_rows).items()
        if key in live
    }
    if not judged:
        return []
    carried = first_seen_dates(cwd=cwd)
    findings: list[FirstSeenFinding] = []
    for key, recorded in sorted(judged.items()):
        evidence = as_calendar_date(value=carried.get(key))
        if evidence is None:
            findings.append(
                FirstSeenFinding(
                    code="first_seen_evidence_unavailable",
                    key=key,
                    first_seen=recorded.isoformat(),
                    evidence=None,
                )
            )
            continue
        if recorded > evidence:
            findings.append(
                FirstSeenFinding(
                    code="first_seen_after_earliest_todo_commit",
                    key=key,
                    first_seen=recorded.isoformat(),
                    evidence=evidence.isoformat(),
                )
            )
    return findings


def judged_first_seen_findings(
    *,
    cwd: Path,
    registry_rows: list[dict[str, object]],
    register_rows: list[dict[str, object]],
    authoring: bool,
) -> list[FirstSeenFinding]:
    """The date findings this run judges — ONE tier's evidence, never both.

    `authoring` is the caller's reading of the staged-diff scope lever, passed
    in rather than re-read here so the repository has exactly one spelling of
    "this is the authoring context". The tiers are exclusive by design: the
    committed comparison is unanswerable before the commit, and the `HEAD`
    comparison is subsumed by it after.

    Both tiers FAIL rather than warn, and unlike the age bound next door they
    need no release lever to do it. Every input is repository DATA — a
    committed blob and a committer date — so no verdict here moves with the
    wall clock, and none can turn master red with no landed change.
    """
    if authoring:
        return _authored_findings(cwd=cwd, register_rows=register_rows)
    return _committed_findings(cwd=cwd, registry_rows=registry_rows, register_rows=register_rows)


def report_first_seen_violations(*, findings: list[FirstSeenFinding]) -> None:
    """Report every finding at error level — the caller owns the exit code."""
    log = structlog.get_logger("heading_coverage_debt_register")
    for finding in findings:
        log.error(
            _MESSAGES[finding.code],
            spec_root=finding.key[0],
            spec_file=finding.key[1],
            heading=finding.key[2],
            finding=finding.code,
            first_seen=finding.first_seen,
            evidence=finding.evidence,
            failing=True,
        )
