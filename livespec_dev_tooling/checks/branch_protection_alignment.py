"""branch_protection_alignment — the default branch is protected AND ci.yml matches it.

Guard Layer 1 mechanical check with two responsibilities, both run
against the repo's resolved default branch (local `origin/HEAD` symref,
then the repo object's `default_branch`, then a `master` fallback — a
main-default governed repo is checked on `main`, never on a
nonexistent `master`; livespec-dev-tooling-17o):

1. PROTECTION-PRESENT gate. When `gh api` can definitively determine
   that the default branch has NO branch protection at all (GitHub
   returns the canonical "Branch not protected" 404), the check FAILS.
   A repo whose default branch is wide open lets PRs auto-merge before
   CI finishes and lets a red PR land; the merge-gate invariant
   requires required-check branch protection to be enabled. See
   `livespec/SPECIFICATION/non-functional-requirements.md` section "CI as a
   merge gate (branch protection)".

2. ALIGNMENT gate (only when protection exists). A `strict`-off
   assertion plus a two-direction comparison between the
   required-checks list and ci.yml (its matrix legs AND its top-level
   jobs), preventing the v039-D1-style drift where a CI job is added or
   removed without updating the default branch's required-checks list
   (or vice versa):

   - `required_status_checks.strict` is enabled → ERROR (strict MUST
     be OFF: strict makes GitHub keep a behind PR current by merging
     the default branch into its branch, injecting a merge commit that
     violates required_linear_history and buries the Red-Green-Replay
     TDD trailers; since the default branch accepts only rebase-merges,
     strict adds no correctness guarantee).
   - Required check matching NEITHER a ci.yml matrix leg NOR a
     top-level job (its id or literal `name:`) → ERROR (the v039 /
     `check-tests` failure: GitHub blocks merges because the required
     check never reports). A required top-level GATE job — the
     single-gate model's `ci-green` aggregate — is a valid target and
     does NOT error here even though it is not a matrix leg.
   - ci.yml matrix leg that is NOT in the required list → WARNING
     ONLY WHEN a required aggregate gate exists, otherwise ERROR. The
     "some jobs are intentionally not required" leniency is sound only
     under the SINGLE-GATE model, where the required aggregate fails in
     the unrequired leg's place; under the many-contexts model with the
     aggregate unrequired, a red leg blocks nothing — the leg is not
     required and neither is the aggregate that would have caught it.
     That condition is now EVALUATED rather than assumed
     (livespec-dev-tooling-e2wv). Top-level jobs (setup,
     export-telemetry, ci-green) are still never flagged as
     should-be-required.

External state: the script shells out to `gh api` to fetch the
required-checks list. The three outcomes are distinguished by the
GitHub API response:

- API succeeds with a contexts list → run the alignment gate.
- API returns the canonical "Branch not protected" 404 → the answer
  is DEFINITIVELY absent → FAIL (exit 4). GitHub only returns this
  exact message for an admin-scoped token reading a genuinely
  unprotected branch.
- `gh` is unavailable / unauthenticated, OR the API errors for any
  OTHER reason (notably a permission/visibility 404 — the default
  Actions `GITHUB_TOKEN` lacks the admin scope needed to READ branch
  protection and gets an ambiguous "Not Found" / "Resource not
  accessible by integration" rather than "Branch not protected") →
  the check CANNOT distinguish "absent" from "can't-read", so it
  exits 0 with a structured warning. Local pre-commit runs are not
  blocked, and CI does not false-fail under the Actions token.

CI-token caveat: because the default Actions `GITHUB_TOKEN` cannot
read branch protection (admin scope), this check hits its graceful-
skip path in a stock GitHub Actions job and does NOT enforce there.
It is wired into the `just check` aggregate / pre-push, where a
maintainer's admin-scoped `gh` token CAN read protection and the
fail-on-absent branch actually fires. It is intentionally NOT a
required CI matrix entry, which would always-skip and be pointless.

Exit codes:

- `0` — protection present and aligned, OR graceful skip (gh
  unavailable / unauthenticated / permission-error / non-github
  remote / no ci.yml).
- `1` — precondition failure: ci.yml present but its matrix.target is
  empty or unparseable (legacy code; the project state needed for the
  alignment gate is not met).
- `4` — check failed with structured stderr findings: default-branch
  protection is definitively absent (`failure_mode`
  `protection_absent`), or `required_status_checks.strict` is enabled
  (`failure_mode` `strict_enabled`; strict MUST be OFF), or a required
  check has no matching ci.yml job (`failure_mode`
  `required_check_missing_from_ci`), or a ci.yml matrix leg is not
  required while NO required aggregate gate covers it (`failure_mode`
  `unrequired_leg_without_aggregate_gate`).

Output discipline matches sibling checks: structlog JSON to stderr;
no `print`, no `sys.stderr.write`.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402

from livespec_dev_tooling.checks._branch_protection_api import (  # noqa: E402
    _fetch_required_contexts,
    _ProtectionAbsent,
)
from livespec_dev_tooling.checks._ci_job_names import (  # noqa: E402
    parse_ci_matrix,
    parse_top_level_jobs,
)
from livespec_dev_tooling.checks._gate_context import (  # noqa: E402
    credential_skip_is_failure,
)

__all__: list[str] = []


_CI_YML_PATH = Path(".github/workflows/ci.yml")


def _run_alignment_gate(
    *,
    log: structlog.stdlib.BoundLogger,
    required: frozenset[str],
    matrix_targets: set[str],
    job_names: set[str],
) -> int:
    """Two-direction comparison between required checks and ci.yml.

    A required check is satisfied when it matches EITHER a matrix leg
    (`matrix_targets`) OR a top-level job's id or literal `name:`
    (`job_names`) — the latter covers the single-gate model, where branch
    protection requires only an aggregate gate job (e.g. `ci-green`) that
    is a top-level job rather than a matrix leg.

    Returns `4` when one or more required checks match neither a matrix
    leg nor a top-level job (the drift the gate prevents), OR when a
    matrix leg is not required and no required aggregate gate covers it
    (below); `0` otherwise. `not_required` is deliberately computed
    against `matrix_targets` ONLY — top-level jobs (setup,
    export-telemetry, ci-green) are NOT flagged as "should be required".

    The "extra matrix legs are warnings only (optional jobs allowed)"
    leniency is CONDITIONAL, and this function EVALUATES the condition
    rather than assuming it (livespec-dev-tooling-e2wv). An unrequired
    leg is benign only under the SINGLE-GATE model, where a required
    top-level aggregate (`ci-green`) fans the matrix in and goes red in
    the leg's place. Under the many-contexts model with the aggregate
    unrequired, nothing catches the leg: it is not required, and neither
    is the aggregate. `required_aggregate_gates` is the condition, read
    from the required-checks list the caller already fetched (no extra
    API call): a required context that matches a top-level job and is
    NOT itself a matrix leg is the aggregate gate the leniency depends
    on. Recognition deliberately reuses the SAME `job_names` grammar
    `missing_from_ci` uses to accept a required top-level gate as a
    valid target, so the two rules cannot drift apart about what counts
    as a gate. An EMPTY required list is the limit case — no required
    context at all, hence no gate — and every leg is then reported.
    """
    missing_from_ci = required - (matrix_targets | job_names)
    not_required = matrix_targets - required
    required_aggregate_gates = (required & job_names) - matrix_targets
    legs_uncovered = not required_aggregate_gates
    for name in sorted(missing_from_ci):
        log.error(
            "required check has no matching ci.yml job",
            check=name,
            failure_mode="required_check_missing_from_ci",
            hint="add to ci.yml matrix or remove from branch protection",
        )
    for name in sorted(not_required):
        if legs_uncovered:
            log.error(
                "ci.yml matrix leg is not required and no required aggregate "
                "gate covers it; a red leg would not block a merge",
                check=name,
                failure_mode="unrequired_leg_without_aggregate_gate",
                hint=(
                    "the optional-leg leniency assumes the single-gate model; "
                    "no required context is a top-level aggregate gate here, so "
                    "add this leg to the required list or require the aggregate "
                    "gate job (e.g. ci-green) that fans the matrix in"
                ),
            )
            continue
        log.warning(
            "ci.yml job is not in branch-protection required list",
            check=name,
            hint="optional jobs are allowed; a required aggregate gate covers this leg",
        )
    if missing_from_ci or (not_required and legs_uncovered):
        return 4
    return 0


def _unreadable_protection_exit_code(
    *,
    log: structlog.stdlib.BoundLogger,
    env: Mapping[str, str],
) -> int:
    """The exit code owed when this run could not READ the protection state.

    Every cause of an unreadable state arrives here as one case — `gh`
    unavailable, unauthenticated, permission-denied, or a non-github remote —
    because for this decision they are one case: the run did not see.

    Outside a delegated gate that is exit 0. "Can't read" is indistinguishable
    from "absent" without admin read access, and failing every contributor who
    holds no forge token would cost far more than it caught.

    Inside a delegated gate it is exit 1. There the skip would authorise a push
    having never read branch protection, and a gate that cannot see must not
    report a pass — the same anti-vacuous-green ruling
    `fleet/_credential_preflight.py` already states for the conformance lane
    (R4.S6, livespec-dev-tooling-ul61).
    """
    if credential_skip_is_failure(env=env):
        log.error(
            "cannot read branch protection inside a delegated gate; "
            "refusing to report a pass this run did not verify",
            hint=(
                "provision the gate executor with a credential able to read "
                "branch protection, and a clone from which this check can "
                "resolve the gated repository, or remove this target from the "
                "gate recipe"
            ),
        )
        return 1
    return 0


def main() -> int:
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
    )
    log = structlog.get_logger("check_branch_protection_alignment")
    cwd = Path.cwd()
    ci_yml = cwd / _CI_YML_PATH
    if not ci_yml.is_file():
        # Graceful absence-handling (epic li-univck Phase 1.1, li-chkabs):
        # consumers that have not configured GitHub Actions CI have no
        # ci.yml; the branch-protection alignment invariant is vacuously
        # satisfied. Exit 0 so the check is safe to wire universally.
        return 0
    ci_source = ci_yml.read_text(encoding="utf-8")
    matrix_targets = parse_ci_matrix(source=ci_source)
    if not matrix_targets:
        log.error("ci.yml matrix.target is empty or unparseable", path=str(_CI_YML_PATH))
        return 1
    job_names = parse_top_level_jobs(source=ci_source)
    fetched = _fetch_required_contexts(log=log)
    if fetched is None:
        return _unreadable_protection_exit_code(log=log, env=os.environ)
    if isinstance(fetched, _ProtectionAbsent):
        log.error(
            "default branch has no branch protection; " "required-check protection MUST be enabled",
            failure_mode="protection_absent",
            hint=(
                "enable required-check branch protection on the default branch "
                "per livespec/SPECIFICATION/non-functional-requirements.md "
                '§"CI as a merge gate (branch protection)"; an unprotected '
                "default branch lets PRs auto-merge before CI finishes and "
                "lets a red PR land"
            ),
        )
        return 4
    if fetched.strict:
        log.error(
            "required_status_checks.strict is enabled; strict MUST be OFF",
            failure_mode="strict_enabled",
            hint=(
                "disable strict (require-branches-up-to-date) on the default "
                "branch's protection per livespec/SPECIFICATION/"
                'non-functional-requirements.md §"CI as a merge gate '
                '(branch protection)"; strict makes GitHub keep a behind PR '
                "current by merging the default branch into it, injecting a "
                "merge commit that violates required_linear_history and "
                "buries the per-commit Red-Green-Replay TDD trailers"
            ),
        )
        return 4
    return _run_alignment_gate(
        log=log,
        required=fetched.contexts,
        matrix_targets=matrix_targets,
        job_names=job_names,
    )


if __name__ == "__main__":
    raise SystemExit(main())
