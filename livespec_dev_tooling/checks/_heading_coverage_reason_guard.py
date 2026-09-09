"""_heading_coverage_reason_guard — which non-acknowledging TODO reasons are JUDGED.

Direction 5 of `heading_coverage`, charter D4 of plan
`fleet-heading-coverage-convergence` (epic `livespec-dev-tooling-0bse`),
ratified into this repository's `SPECIFICATION/non-functional-requirements.md`
at v064. The ratified PREDICATE — what makes a `reason` an acknowledgment
rather than a cop-out — lives in the sibling
`_heading_coverage_reason_predicate`; this module owns the TIER decision over
its findings and every structured diagnostic they produce.

THIS DIRECTION IS TWO-TIERED, and the split is what makes it landable ahead of
the burn-down it exists to force. At P1 landing every one of the fleet's 373
`TODO` rows fails the predicate (plan research `003`), so an unconditional
verdict would red 11 repositories on the commit that adopts it — the
arm-ahead-of-adoption trap this repository's `CLAUDE.md` records, and the
`livespec-dev-tooling-3ztbdq` shape that made `tests/heading-coverage.json`
unwritable when a gate judged a shared co-edit registry whole.

- PER-COMMIT tier (`LIVESPEC_SCOPE_HEADING_COVERAGE_REASONS_TO_HEAD_DIFF` unset
  or empty): every non-acknowledging reason is REPORTED at warning level naming
  the lever, and the direction contributes no exit code. This is the tier the
  plan's P2 burn-down runs under.
- ARMED tier (the lever set to a non-empty value; the authoring-time pre-commit
  subset sets it whenever the staged changeset touches the registry): the
  VERDICT is narrowed to the rows this tree AUTHORS — those whose row differs
  from `HEAD:tests/heading-coverage.json` — and a newly-authored cop-out exits
  non-zero.

Two properties keep the narrowing honest, both inherited deliberately from
`no_todo_registry`'s lever and the debt ratchet's:

- IT NARROWS THE VERDICT, NEVER THE REPORT. An out-of-scope finding is still
  emitted at warning level carrying `out_of_staged_scope`, so an inherited
  cop-out never becomes indistinguishable from an acknowledgment.
- AN UNCOMPUTABLE SCOPE FAILS CLOSED onto every finding and says so
  (`baseline_unreadable`) — "I could not tell what changed" must never be
  spelled the same way as "nothing changed". Where `HEAD` carries no registry
  copy at all, every live row IS newly authored, so fail-closed is also the
  correct answer there rather than merely the safe one.

The `after` side of the comparison is the WORKING-TREE copy the parent already
loaded, not the index, so an unstaged registry edit counts as in scope too.
That is the fail-closed direction (the judged set is a SUPERSET of the staged
diff) and it is why the lever is named for `HEAD` rather than for the index.

Charter D9 retires the lever once a repository's debt register reaches empty,
at which point a `TODO` row fails the per-commit tier outright.

## ON THE `IOResult` RAILWAY — `livespec-dev-tooling-qndn.15`

`judged_reason_findings` is convicted TRANSITIVELY: it reads `cwd` through
`baseline_fingerprints` → `heading_coverage_debt.head_rows`, whose whole
answer used to be a `None` sentinel. Both now ride the railway, and the shape
is the one `cross_member_consumption` took in `livespec-dev-tooling-qndn.14` —
the FAILURE carries the usable answer.

WHAT THE OLD `list[ReasonFinding]` COULD NOT SAY. Three different runs
returned that one spelling: nothing was judged because the guard is unarmed;
this exact set was judged because the tree AUTHORS it; and EVERYTHING is
judged because the scope could not be computed at all. The third is a
fail-closed fallback rather than a measurement, and it reached the caller
wearing a measurement's clothes — the caller's only cue was a warning it was
free not to read.

So an armed run over an incomparable `HEAD` returns
`IOFailure(UnnarrowedReasonJudgement)` CARRYING every finding. The verdict is
byte-unchanged (the caller still judges them all, which is correct where no
`HEAD` copy exists because every live row IS newly authored); what changed is
that the caller can no longer receive the fallback in a narrowed judgement's
spelling and forget the difference. A field can be left unread; a failure
track cannot.

`IOResult` and not `Result`: the scope is a statement about `HEAD`, read by
shelling out to git.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in this tree. Diagnostics flow through
structlog (JSON to stderr) under the PARENT's `heading_coverage` logger name,
because they are that check's findings; the vendored copy is added to
`sys.path` at module import time.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

# Carried rather than inherited from an importer: without it the vendored
# `structlog` resolves only because some module up the import chain happens to
# carry the preamble, which is a property of the caller rather than of this
# file.
_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure, IOResult, IOSuccess  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._heading_coverage_reason_predicate import (  # noqa: E402
    ReasonFinding,
    reason_findings,
)
from livespec_dev_tooling.heading_coverage_debt import (  # noqa: E402
    COVERAGE_PATH,
    HeadCopyIncomparable,
    head_rows,
)

# Names in `__all__` mark this private sibling's public surface to its sole
# importer, `heading_coverage.py`, so pyright's per-file analysis does not flag
# them unused across the package boundary. `ReasonFinding` is re-listed because
# the parent annotates its report signature with it.
__all__: list[str] = [
    "ReasonFinding",
    "UnnarrowedReasonJudgement",
    "baseline_fingerprints",
    "entry_fingerprint",
    "judged_reason_findings",
    "report_reason_violations",
]


_SCOPE_ENV_VAR = "LIVESPEC_SCOPE_HEADING_COVERAGE_REASONS_TO_HEAD_DIFF"
_MESSAGE = (
    'heading-coverage.json row has `test: "TODO"` whose `reason` does not acknowledge an '
    "owed test — per livespec-dev-tooling's SPECIFICATION/non-functional-requirements.md "
    '§"Scenario-tier coverage", the only legal justification for a `TODO` is that a real '
    "test at the required tier is owed and a live work-item owns landing it. There is no "
    "non-testable category: a heading with no behavior is a specification-structure defect"
)


@dataclass(frozen=True, kw_only=True)
class UnnarrowedReasonJudgement:
    """The armed tier could not narrow, so it judges EVERY finding — fail-closed.

    The failure track of `judged_reason_findings`, inhabited exactly when the
    lever is set and `HEAD` carries no comparable registry copy. `findings`
    holds every finding rather than none, because that IS the correct verdict
    there: with no `HEAD` copy, every live row is newly authored, so the
    fallback is right as well as safe, and discarding it would turn an
    unreadable baseline into a clean run.

    So the payload is deliberately identical to what the success track would
    have carried on the same input — the caller's obligation is what moves, not
    the data. `baseline_unreadable` says the same thing in the log, and a log
    line is a thing a caller may not read.
    """

    findings: list[ReasonFinding]


def entry_fingerprint(*, entry: dict[str, object]) -> str:
    """Canonical, key-order-independent rendering of one registry row.

    Two rows compare equal iff their VALUES agree, so reformatting the registry
    or reordering a row's keys is not read as "every row changed" — only a
    changed value puts a row back in scope.
    """
    return json.dumps(entry, sort_keys=True)


def baseline_fingerprints(*, cwd: Path) -> IOResult[frozenset[str], HeadCopyIncomparable]:
    """Fingerprints of the registry as of `HEAD`; a FAILURE when NOT COMPARABLE.

    A finding whose fingerprint is absent from this set is one the tree AUTHORS
    — added or modified since `HEAD`. Removal needs no representation here: a
    row that no longer exists carries no finding.

    The failure track never means "the registry was empty at HEAD". It is
    `head_rows`' verdict that no comparison is possible (not a repository, no
    such blob, unparseable, not an array), passed through unchanged so the one
    caller that turns it into a whole-registry fallback still names WHICH
    incomparability it hit.
    """
    return head_rows(cwd=cwd, path=COVERAGE_PATH).map(
        lambda rows: frozenset(entry_fingerprint(entry=row) for row in rows)
    )


def _fields(*, finding: ReasonFinding) -> dict[str, object]:
    """The diagnostic fields every spelling of this finding carries.

    Shared so a warn-only run and an armed one are read the same way by an
    operator, differing only in `failing` and in whether the lever or the scope
    explains the leniency.
    """
    return {
        "spec_root": finding.entry.get("spec_root"),
        "spec_file": finding.entry.get("spec_file"),
        "heading": finding.entry.get("heading"),
        "work_item": finding.entry.get("work_item"),
        "reason_defect": finding.defect,
        "evidence": finding.evidence,
    }


def _warn(*, finding: ReasonFinding, out_of_staged_scope: bool) -> None:
    """Report a finding this run does NOT judge, naming what spared it."""
    log = structlog.get_logger("heading_coverage")
    log.warning(
        _MESSAGE,
        **_fields(finding=finding),
        arm_env_var=_SCOPE_ENV_VAR,
        out_of_staged_scope=out_of_staged_scope,
        failing=False,
    )


def report_reason_violations(*, findings: list[ReasonFinding]) -> None:
    """Report every JUDGED finding at error level — the caller owns the exit code."""
    log = structlog.get_logger("heading_coverage")
    for finding in findings:
        log.error(_MESSAGE, **_fields(finding=finding), failing=True)


def judged_reason_findings(
    *, entries: list[dict[str, object]], cwd: Path
) -> IOResult[list[ReasonFinding], UnnarrowedReasonJudgement]:
    """The direction-5 findings this run JUDGES; the rest are reported as warnings.

    Unarmed, NOTHING is judged: every finding is reported at warning level
    naming the lever that arms it, and that empty list is an ANSWER, so it
    stays on the success track. That is the per-commit tier the P2 burn-down
    runs under, and it is why landing this direction reddens no repository on
    the commit that adopts it.

    ⛔ AN `IOSuccess` NOW MEANS "the scope question was SETTLED, and this is
    what it admits" — the lever is off so nothing is judged, or the lever is on
    and the narrowing was computed. It never means "I judged everything because
    I could not tell what changed": that is the failure track, carrying every
    finding; see `UnnarrowedReasonJudgement` for why the payload is the same
    either way.
    """
    log = structlog.get_logger("heading_coverage")
    findings = reason_findings(entries=entries)
    if not os.environ.get(_SCOPE_ENV_VAR):
        for finding in findings:
            _warn(finding=finding, out_of_staged_scope=False)
        return IOSuccess([])
    baseline = baseline_fingerprints(cwd=cwd)
    if isinstance(baseline, IOFailure):
        incomparable = unsafe_perform_io(baseline.failure())
        log.warning(
            "staged-diff scope requested but HEAD's heading-coverage registry is not "
            "comparable — the reason guard falls back to judging EVERY TODO reason",
            revision=incomparable.revision,
            head_copy=incomparable.reason,
            baseline_unreadable=True,
            failing=False,
        )
        return IOFailure(UnnarrowedReasonJudgement(findings=findings))
    fingerprints = unsafe_perform_io(baseline.unwrap())
    judged: list[ReasonFinding] = []
    for finding in findings:
        if entry_fingerprint(entry=finding.entry) in fingerprints:
            _warn(finding=finding, out_of_staged_scope=True)
            continue
        judged.append(finding)
    return IOSuccess(judged)
