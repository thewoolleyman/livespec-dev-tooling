"""heading_coverage_debt_register — the heading-coverage debt ratchet, shrink-only.

Charter D3 of plan `fleet-heading-coverage-convergence` (epic
`livespec-dev-tooling-0bse`), ratified into this repository's
`SPECIFICATION/non-functional-requirements.md` at v064. A per-commit BAN on
`test: "TODO"` was considered and rejected — it would break the spec-first
workflow (a coverage row exists at ratification time, before an impl item can
land the test) and recreate `livespec-dev-tooling-3ztbdq`, where arming over
a whole registry made `tests/heading-coverage.json` unwritable. A RATCHET
breaks neither: today's debt is frozen as a baseline, and the only permitted
movement is downward.

Three directions, all read from the repository's own committed files:

- `unregistered_todo` — a `test: "TODO"` row whose
  `(spec_root, spec_file, heading)` key is absent from
  `tests/heading-coverage-debt.json`. This is the NEW COP-OUT direction: the
  only way to add a `TODO` is to resolve one first.
- `stale_register_entry` — a register entry with no matching live `TODO` row.
  Fires when a row is resolved to a real test (or deleted) and its register
  entry is left behind, which would silently bank a shrink that never
  happened and leave room for a future `TODO` to slip in unchallenged.
- `register_grew` — a register key absent from `HEAD`'s register. The
  shrink-only rule itself.

A fourth, `register_row_incomplete`, guards the ratified SCHEMA: a register
row must carry the key three plus `work_item` and `first_seen`. Debt with no
owner and no clock is debt the liveness gate and the release-tier age bound
(charter D4/D5) cannot judge.

A fifth, the AGE BOUND (charter D5), is the one direction that is
RELEASE-TIER-ONLY: a `TODO` whose register `first_seen` is older than the
repository's configured bound (default 30 days) fails when
`LIVESPEC_FAIL_IF_HEADING_COVERAGE_TODOS_EXIST` is set, and only warns
otherwise. Age depends on the CLOCK rather than on anything a commit
authors, so a per-commit verdict on it could turn master red with no landed
change. It lives whole in the private sibling `_heading_coverage_age_bound`
— the same cohesion split as `heading_coverage`'s reason guard — which owns
the bound's configuration, the date arithmetic, the tier decision and both
of its diagnostics.

NON-BREAKING BY CONSTRUCTION. The register is generated from the live
registry (`livespec_dev_tooling.heading_coverage_debt`), so at adoption the
baseline IS today's set and every direction is satisfied on an untouched
tree. The check reddens a repository only once someone tries to grow the
debt.

AN INCOMPARABLE `HEAD` REGISTER DOES NOT CONVICT. When git cannot produce a
`HEAD` copy of the register — the adoption commit, where the file does not
exist at `HEAD`, or a clone with no history — growth is UNJUDGED and said so
(`baseline_unreadable`), because "the register may only shrink" is undefined
with nothing to shrink from. Fail-closed there would red the very commit
that adopts the ratchet in every consumer, which is the arm-ahead-of-adoption
trap this repository's `CLAUDE.md` records. The other three directions still
run, and they are the ones that hold on a tree with no history at all.

AN UNREADABLE FILE IS NOT AN EMPTY ONE, and telling them apart is what
`livespec-dev-tooling-qndn.15` bought here. `load_rows` used to answer `[]` for
a present file it could not turn into an array, so an unparseable registry
reached this check as "no `TODO` rows" — which fires `stale_register_entry`
for EVERY register key — and an unparseable register reached it as "no
entries", which fires `unregistered_todo` for every live `TODO`. Both are full
slates of confident findings that name the wrong file and the wrong cause. The
railway makes that state its own outcome: `main()` reports it once and exits
non-zero without deciding a single direction. An ABSENT file is untouched by
this and still rides the success track as `[]`, which is what keeps adoption
— no register yet — passing.

STAGED-DIFF SCOPE (`LIVESPEC_SCOPE_HEADING_COVERAGE_DEBT_TO_HEAD_DIFF` set to
a non-empty value) narrows the VERDICT to the keys a commit is AUTHORING:
those whose registry row or register entry differs from `HEAD`. This is the
same lever, and the same reasoning, as `no_todo_registry`'s — a commit is
judged on what it authors, never on debt it inherited (charter D2b). The
authoring-time arming in `scripts/just/check-pre-commit-doc-only.sh` sets it;
the aggregate does not, so the pre-push and CI verdicts stay whole-tree.

Two properties keep the narrowing honest, both inherited deliberately from
`no_todo_registry`:

- IT NARROWS THE VERDICT, NEVER THE REPORT. An out-of-scope finding is still
  emitted at warning level carrying `out_of_staged_scope`, so an inherited
  offender never becomes indistinguishable from a clean register.
- AN UNCOMPUTABLE SCOPE FAILS CLOSED. When `HEAD`'s registry copy is not
  comparable the scope reverts to EVERY finding and says so — "I could not
  tell what changed" must never be spelled the same way as "nothing changed".

The `after` side of both comparisons is the WORKING-TREE copy, not the index,
so an unstaged edit counts as in scope too. That is the fail-closed direction
(the judged set is a SUPERSET of the staged diff) and it is why the lever is
named for `HEAD` rather than for the index.

Output discipline: per spec, `print` (T20) and `sys.stderr.write`
(`check-no-write-direct`) are banned in this tree. Diagnostics flow through
structlog (JSON to stderr); the vendored copy is added to `sys.path` at
module import time.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.
from returns.io import IOFailure  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._heading_coverage_age_bound import (  # noqa: E402
    judged_age_findings,
    report_age_violations,
)
from livespec_dev_tooling.heading_coverage_debt import (  # noqa: E402
    COVERAGE_PATH,
    REGISTER_PATH,
    head_rows,
    load_rows,
    register_key,
    register_row_is_complete,
    todo_rows,
)

__all__: list[str] = []


_SCOPE_ENV_VAR = "LIVESPEC_SCOPE_HEADING_COVERAGE_DEBT_TO_HEAD_DIFF"

_MESSAGES = {
    "unregistered_todo": (
        'heading-coverage.json row has `test: "TODO"` but no entry in the shrink-only '
        "debt register — a new cop-out outside the frozen baseline. Resolve the heading "
        "to a real test, or remove the row"
    ),
    "stale_register_entry": (
        "heading-coverage-debt.json entry has no matching `TODO` row — the row was "
        "resolved or removed without removing its register entry. The register must "
        "shrink in lockstep with real resolutions"
    ),
    "register_grew": (
        "heading-coverage-debt.json entry is absent from HEAD's register — the register "
        "GREW. It may only shrink toward empty"
    ),
    "register_row_incomplete": (
        "heading-coverage-debt.json entry is missing a required field — every entry "
        "carries `spec_root`, `spec_file`, `heading`, `work_item` and `first_seen`"
    ),
}

# NOT a `_MESSAGES` entry, because it is not a finding: it says the ratchet
# could not read a file it ratchets, so it has no register key to name. An
# unreadable registry used to reach the directions below as "no rows" and an
# unreadable register as "no entries" — each producing a full slate of
# CONFIDENT findings about the other file, every one of them wrong about the
# cause. Saying so once, and exiting, is the honest response.
_UNREADABLE_MESSAGE = (
    "a heading-coverage file this ratchet reads is present and unreadable — no direction "
    "is decided for this run, because judging one file against an unreadable other would "
    "report a fabricated finding for every key in it"
)


@dataclass(frozen=True, kw_only=True)
class _Finding:
    """One ratchet violation, identified by the register key it concerns."""

    code: str
    key: tuple[str, str, str]


def _keyed(*, rows: list[dict[str, object]]) -> dict[tuple[str, str, str], dict[str, object]]:
    """Key → row for every KEYED row; unkeyed rows are dropped.

    An unkeyed row is `heading_coverage`'s business, not this check's: without
    a `(spec_root, spec_file, heading)` triple there is nothing to ratchet, and
    convicting it here would double-report a defect that gate already names.
    """
    keyed: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in rows:
        key = register_key(row=row)
        if key is not None:
            keyed[key] = row
    return keyed


def _state(
    *, registry_rows: list[dict[str, object]], register_rows: list[dict[str, object]]
) -> dict[tuple[str, str, str], str]:
    """Key → canonical rendering of the key's `(TODO row, register entry)` pair.

    Key-order-independent (`sort_keys`), so reformatting either file is not read
    as "every key changed" — only a changed VALUE puts a key back in scope.
    """
    todo = _keyed(rows=todo_rows(rows=registry_rows))
    register = _keyed(rows=register_rows)
    return {
        key: json.dumps([todo.get(key), register.get(key)], sort_keys=True)
        for key in set(todo) | set(register)
    }


def _changed_keys(
    *,
    cwd: Path,
    registry_rows: list[dict[str, object]],
    register_rows: list[dict[str, object]],
) -> frozenset[tuple[str, str, str]] | None:
    """The keys this tree AUTHORS relative to `HEAD`; `None` when uncomputable.

    A key changed when either its `TODO` row or its register entry differs from
    `HEAD` — added, modified, or removed. Removal has to count, or resolving a
    row while leaving its register entry behind would fall out of its own scope.

    `HEAD` carrying no register (the adoption commit) is NOT uncomputable: an
    absent register at `HEAD` is treated as empty, which puts every current
    entry in scope — the fail-closed direction. Only an incomparable REGISTRY
    copy defeats the computation, because without it nothing about the debt side
    can be placed.
    """
    head_registry = head_rows(cwd=cwd, path=COVERAGE_PATH)
    if isinstance(head_registry, IOFailure):
        return None
    # An incomparable HEAD REGISTER is the adoption commit, and treating it as
    # empty is what puts every current entry in scope — the fail-closed
    # direction this docstring names, kept verbatim across the conversion.
    head_register = head_rows(cwd=cwd, path=REGISTER_PATH)
    register_before: list[dict[str, object]] = []
    if not isinstance(head_register, IOFailure):
        register_before = unsafe_perform_io(head_register.unwrap())
    before = _state(
        registry_rows=unsafe_perform_io(head_registry.unwrap()), register_rows=register_before
    )
    after = _state(registry_rows=registry_rows, register_rows=register_rows)
    return frozenset(key for key in set(before) | set(after) if before.get(key) != after.get(key))


def _ratchet_findings(
    *, registry_rows: list[dict[str, object]], register_rows: list[dict[str, object]]
) -> list[_Finding]:
    """The three history-free directions: unregistered TODO, stale entry, bad schema."""
    todo = _keyed(rows=todo_rows(rows=registry_rows))
    register = _keyed(rows=register_rows)
    findings = [
        _Finding(code="unregistered_todo", key=key) for key in sorted(todo) if key not in register
    ]
    for key in sorted(register):
        if key not in todo:
            findings.append(_Finding(code="stale_register_entry", key=key))
        elif not register_row_is_complete(row=register[key]):
            findings.append(_Finding(code="register_row_incomplete", key=key))
    return findings


def _growth_findings(
    *, register_rows: list[dict[str, object]], baseline_rows: list[dict[str, object]]
) -> list[_Finding]:
    """Register keys `HEAD` does not carry — the shrink-only direction."""
    baseline = set(_keyed(rows=baseline_rows))
    return [
        _Finding(code="register_grew", key=key)
        for key in sorted(_keyed(rows=register_rows))
        if key not in baseline
    ]


def _emit(*, finding: _Finding, failing: bool) -> None:
    """Report one finding, as an error when judged and a warning when out of scope."""
    emit = structlog.get_logger("heading_coverage_debt_register")
    if failing:
        emit.error(
            _MESSAGES[finding.code],
            spec_root=finding.key[0],
            spec_file=finding.key[1],
            heading=finding.key[2],
            finding=finding.code,
            failing=True,
        )
        return
    emit.warning(
        _MESSAGES[finding.code],
        spec_root=finding.key[0],
        spec_file=finding.key[1],
        heading=finding.key[2],
        finding=finding.code,
        out_of_staged_scope=True,
        failing=False,
    )


def _judged(
    *,
    findings: list[_Finding],
    cwd: Path,
    registry_rows: list[dict[str, object]],
    register_rows: list[dict[str, object]],
) -> list[_Finding]:
    """`findings` narrowed to the keys this tree authors, reporting the rest as warnings."""
    emit = structlog.get_logger("heading_coverage_debt_register")
    changed = _changed_keys(cwd=cwd, registry_rows=registry_rows, register_rows=register_rows)
    if changed is None:
        emit.warning(
            "staged-diff scope requested but HEAD's heading-coverage registry is not "
            "comparable — the ratchet falls back to judging the WHOLE register",
            baseline_unreadable=True,
            failing=False,
        )
        return findings
    in_scope: list[_Finding] = []
    for finding in findings:
        if finding.key in changed:
            in_scope.append(finding)
            continue
        _emit(finding=finding, failing=False)
    return in_scope


def main() -> int:
    """Run the ratchet against the repository at cwd; non-zero on any judged finding."""
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    emit = structlog.get_logger("heading_coverage_debt_register")
    cwd = Path.cwd()
    registry_scan = load_rows(path=cwd / COVERAGE_PATH)
    register_scan = load_rows(path=cwd / REGISTER_PATH)
    for scan in (registry_scan, register_scan):
        if isinstance(scan, IOFailure):
            # The record's fields ARE the diagnostic fields, so they are spread
            # rather than restated: a field added to `RowsUnreadable` later
            # cannot then be silently missing from the one report that carries it.
            emit.error(
                _UNREADABLE_MESSAGE, **asdict(unsafe_perform_io(scan.failure())), failing=True
            )
            return 1
    # An ABSENT file stays on the success track as `[]`, so adoption — no
    # register yet — still reaches the directions below exactly as before.
    registry_rows = unsafe_perform_io(registry_scan.unwrap())
    register_rows = unsafe_perform_io(register_scan.unwrap())
    findings = _ratchet_findings(registry_rows=registry_rows, register_rows=register_rows)
    baseline_scan = head_rows(cwd=cwd, path=REGISTER_PATH)
    if isinstance(baseline_scan, IOFailure):
        emit.warning(
            "HEAD carries no comparable heading-coverage debt register — the shrink-only "
            "direction is UNJUDGED for this run (adoption, or a tree with no history)",
            **asdict(unsafe_perform_io(baseline_scan.failure())),
            baseline_unreadable=True,
            failing=False,
        )
    else:
        baseline_rows = unsafe_perform_io(baseline_scan.unwrap())
        findings += _growth_findings(register_rows=register_rows, baseline_rows=baseline_rows)
    if os.environ.get(_SCOPE_ENV_VAR):
        findings = _judged(
            findings=findings,
            cwd=cwd,
            registry_rows=registry_rows,
            register_rows=register_rows,
        )
    # The age direction is NOT narrowed by the staged-diff scope above, and
    # cannot be: it is armed by the release lever, which the authoring-time
    # subset never sets for this check, so there is no commit whose authorship
    # a narrowing could be measured against.
    aged = judged_age_findings(
        registry_rows=registry_rows, register_rows=register_rows, repo_root=cwd
    )
    for finding in findings:
        _emit(finding=finding, failing=True)
    report_age_violations(findings=aged)
    return 1 if findings or aged else 0


if __name__ == "__main__":
    raise SystemExit(main())
