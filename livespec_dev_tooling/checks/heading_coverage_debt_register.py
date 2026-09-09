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
from dataclasses import dataclass
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402  — vendor-path-aware import after sys.path insert.

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
    if head_registry is None:
        return None
    before = _state(
        registry_rows=head_registry, register_rows=head_rows(cwd=cwd, path=REGISTER_PATH) or []
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
    registry_rows = load_rows(path=cwd / COVERAGE_PATH)
    register_rows = load_rows(path=cwd / REGISTER_PATH)
    findings = _ratchet_findings(registry_rows=registry_rows, register_rows=register_rows)
    baseline_rows = head_rows(cwd=cwd, path=REGISTER_PATH)
    if baseline_rows is None:
        emit.warning(
            "HEAD carries no comparable heading-coverage debt register — the shrink-only "
            "direction is UNJUDGED for this run (adoption, or a tree with no history)",
            revision=f"HEAD:{REGISTER_PATH.as_posix()}",
            baseline_unreadable=True,
            failing=False,
        )
    else:
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
