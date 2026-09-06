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

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

import structlog  # noqa: E402

from livespec_dev_tooling.checks._ci_job_names import (  # noqa: E402
    parse_ci_matrix,
    parse_top_level_jobs,
)

__all__: list[str] = []


_CI_YML_PATH = Path(".github/workflows/ci.yml")
# Match the two canonical github.com remote URL forms emitted by `git remote
# get-url origin`: `https://github.com/<owner>/<repo>(.git)` and
# `git@github.com:<owner>/<repo>(.git)`. The library is consumed across
# every livespec-governed sibling repo, so the consumer's owner/repo
# identifier MUST come from the local git remote rather than a hardcoded
# constant (which would have pinned the check to a single repo).
_REMOTE_URL_PATTERN = re.compile(
    r"^(?:https?://github\.com/|git@github\.com:)([^/]+)/([^/]+?)(?:\.git)?/?$"
)
# GitHub's branch-protection endpoints return this EXACT 404 message
# body only when an admin-scoped token reads a genuinely unprotected
# branch. A token that lacks the admin scope needed to READ protection
# (the default Actions GITHUB_TOKEN) gets a generic "Not Found" /
# "Resource not accessible by integration" instead, so the presence of
# this literal phrase is the definitive "absent" disambiguator.
_NOT_PROTECTED_MARKER = "Branch not protected"
# `git symbolic-ref refs/remotes/origin/HEAD` answers with a ref of this
# shape when the clone recorded origin's default branch; the branch name
# is the remainder after the prefix.
_ORIGIN_HEAD_PREFIX = "refs/remotes/origin/"
# Last-resort default branch when neither the local symref nor the repo
# object resolves one. Matches the fleet-side resolver's fallback
# (`FleetContext.canonical_ref`): an unresolvable lookup then behaves
# exactly as the pre-17o hardcoded path did.
_FALLBACK_BRANCH = "master"


@dataclass(frozen=True, kw_only=True)
class _ProtectionAbsent:
    """The API definitively reported the default branch is unprotected.

    Distinct from the graceful-skip case (represented by `None`): an
    admin-scoped token read the default branch's protection and GitHub
    answered with the canonical "Branch not protected" 404. This is a
    fail-trigger, not a can't-read skip.
    """


@dataclass(frozen=True, kw_only=True)
class _RequiredContexts:
    """The API succeeded; carries the default branch's required_status_checks.

    `contexts` is the required-checks list; `strict` is the
    require-branches-up-to-date flag, which MUST be OFF per livespec
    NFR section "CI as a merge gate (branch protection)".
    """

    contexts: frozenset[str]
    strict: bool


def _resolve_owner_repo(*, log: structlog.stdlib.BoundLogger) -> str | None:
    """Resolve the GitHub owner/repo identifier from `git remote get-url origin`.

    Returns None and logs a warning when git is unavailable, the
    remote is not set, or the URL does not match the canonical
    github.com pattern — so the calling check exits 0 cleanly
    rather than failing in unusual local configurations (no remote,
    fork remote, gitlab, etc.).
    """
    completed = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        log.warning(
            "git remote get-url origin failed; skipping branch-protection alignment check",
            stderr=completed.stderr.strip()[:200],
            hint="run inside a checked-out clone with an `origin` remote configured",
        )
        return None
    url = completed.stdout.strip()
    match = _REMOTE_URL_PATTERN.match(url)
    if match is None:
        log.warning(
            "origin URL did not match github.com pattern; skipping branch-protection alignment",
            url=url[:200],
            hint="branch-protection alignment is github.com-specific",
        )
        return None
    return f"{match.group(1)}/{match.group(2)}"


def _default_branch_from_git() -> str | None:
    """The default branch per the clone's `refs/remotes/origin/HEAD`, or None.

    `git symbolic-ref refs/remotes/origin/HEAD` answers from local state
    (no network); a normal clone records the symref at clone time. None
    when the symref is unset (e.g. a single-ref CI fetch) or the output
    is not a `refs/remotes/origin/<branch>` ref.
    """
    completed = subprocess.run(
        ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    ref = completed.stdout.strip()
    branch = ref.removeprefix(_ORIGIN_HEAD_PREFIX)
    if branch == ref or not branch:
        return None
    return branch


def _default_branch_from_api(*, owner_repo: str) -> str | None:
    """The default branch per the GitHub repo object, or None on any failure.

    `GET repos/{owner_repo}` needs only basic repository read access
    (the default Actions GITHUB_TOKEN has it), so this fallback still
    resolves correctly where the symref is unset.
    """
    completed = subprocess.run(
        ["gh", "api", f"repos/{owner_repo}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        return None
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        return None
    branch = cast("dict[str, object]", parsed).get("default_branch")
    if not isinstance(branch, str) or not branch:
        return None
    return branch


def _resolve_default_branch(*, log: structlog.stdlib.BoundLogger, owner_repo: str) -> str:
    """Resolve the repo's default branch: local symref, then the API, then `master`.

    The check historically hardcoded `master`, so on a main-default
    governed repo it read the protection of a nonexistent branch and
    misreported (livespec-dev-tooling-17o). Default-branch resolution is
    mechanical extraction, not a spec-rule parser, so per the
    livespec-dev-tooling-6cf convention it is implemented locally here
    rather than shared with the fleet modules' `FleetContext.canonical_ref`
    (`checks/` never imports from `fleet/`).
    """
    branch = _default_branch_from_git()
    if branch is not None:
        return branch
    branch = _default_branch_from_api(owner_repo=owner_repo)
    if branch is not None:
        return branch
    log.warning(
        "could not resolve the default branch; falling back to 'master'",
        hint=(
            "record origin's default branch locally (git remote set-head "
            "origin -a) or check gh auth status"
        ),
    )
    return _FALLBACK_BRANCH


def _fetch_required_contexts(
    *, log: structlog.stdlib.BoundLogger
) -> _RequiredContexts | _ProtectionAbsent | None:
    """Fetch the default branch protection's required_status_checks object.

    Three-way result:

    - `_RequiredContexts` — the API succeeded; carries the default
      branch's required-checks list (possibly empty) AND the `strict`
      flag.
    - `_ProtectionAbsent` — the API definitively reported NO protection
      (the canonical "Branch not protected" 404). Fail-trigger.
    - `None` — graceful skip: `gh` is unavailable, the call failed for
      a reason OTHER than definitive-absence (e.g. a permission/
      visibility 404 under a token without admin scope), the remote is
      not github.com, or the success payload had an unexpected shape.
      The caller exits 0 so local pre-commit and Actions-token CI runs
      are not blocked, since "can't read" is indistinguishable from
      "absent" without admin read access.
    """
    if shutil.which("gh") is None:
        log.warning(
            "gh CLI not on PATH; skipping branch-protection alignment check",
            hint="install gh CLI or run in CI with GH_TOKEN set",
        )
        return None
    owner_repo = _resolve_owner_repo(log=log)
    if owner_repo is None:
        return None
    branch = _resolve_default_branch(log=log, owner_repo=owner_repo)
    # Read the full required_status_checks OBJECT (not the bare
    # /contexts sub-endpoint) so the response carries both `strict` and
    # `contexts`: the strict-off assertion needs the `strict` flag, which
    # the /contexts list endpoint does not return.
    api_path = f"repos/{owner_repo}/branches/{branch}/protection/required_status_checks"
    completed = subprocess.run(
        ["gh", "api", api_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        combined = f"{completed.stdout}\n{completed.stderr}"
        if _NOT_PROTECTED_MARKER in combined:
            # Definitive "absent": an admin-scoped token read the default
            # branch and GitHub answered with the canonical "Branch not
            # protected" 404. This is the fail-trigger, NOT a can't-read
            # skip.
            return _ProtectionAbsent()
        log.warning(
            "gh api call failed for a non-definitive reason; "
            "cannot distinguish absent protection from missing read access; "
            "skipping branch-protection alignment check",
            stderr=completed.stderr.strip()[:200],
            hint=(
                "check gh auth status; the default Actions GITHUB_TOKEN "
                "lacks the admin scope needed to read branch protection"
            ),
        )
        return None
    parsed = json.loads(completed.stdout)
    if not isinstance(parsed, dict):
        log.error("unexpected gh api response shape", payload_type=type(parsed).__name__)
        return None
    # The `cast` is the single typed parse boundary: `json.loads` yields
    # `Any`, the `isinstance` guard narrows to `dict`, and the cast gives the
    # object's members a typed `object` shape so the per-element
    # `isinstance(entry, str)` filter and the `bool(...)` strict coercion stay
    # load-bearing runtime guards against a malformed `gh api` payload.
    payload = cast("dict[str, object]", parsed)
    contexts_raw = payload.get("contexts")
    contexts: set[str] = set()
    if isinstance(contexts_raw, list):
        for entry in cast("list[object]", contexts_raw):
            if isinstance(entry, str):
                contexts.add(entry)
    strict = bool(payload.get("strict"))
    return _RequiredContexts(contexts=frozenset(contexts), strict=strict)


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
        # Graceful skip: gh unavailable / unauthenticated /
        # permission-error / non-github remote. "Can't read" is
        # indistinguishable from "absent" without admin read access,
        # so do NOT fail.
        return 0
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
