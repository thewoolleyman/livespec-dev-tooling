"""branch_protection_alignment — master is protected AND ci.yml matches it.

Guard Layer 1 mechanical check with two responsibilities:

1. PROTECTION-PRESENT gate. When `gh api` can definitively determine
   that master has NO branch protection at all (GitHub returns the
   canonical "Branch not protected" 404), the check FAILS. A repo
   whose master is wide open lets PRs auto-merge before CI finishes
   and lets a red PR land on master; the merge-gate invariant requires
   required-check branch protection to be enabled. See
   `livespec/SPECIFICATION/non-functional-requirements.md` §"CI as a
   merge gate (branch protection)".

2. ALIGNMENT gate (only when protection exists). A `strict`-off
   assertion plus a two-direction comparison between the
   required-checks list and ci.yml's matrix, preventing the
   v039-D1-style drift where a CI job is added or removed without
   updating the master-branch required-checks list (or vice versa):

   - `required_status_checks.strict` is enabled → ERROR (strict MUST
     be OFF: strict makes GitHub keep a behind PR current by merging
     master into its branch, injecting a merge commit that violates
     required_linear_history and buries the Red-Green-Replay TDD
     trailers; since master accepts only rebase-merges, strict adds
     no correctness guarantee).
   - Required check missing from ci.yml's matrix → ERROR (the
     v039 / `check-tests` failure: GitHub blocks merges because
     the required check never reports).
   - ci.yml job that is NOT in the required list → WARNING (some
     jobs are intentionally not required, e.g., experimental
     workflows; emit a diagnostic but exit 0).

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
- `4` — check failed with structured stderr findings: master
  protection is definitively absent (`failure_mode`
  `protection_absent`), or `required_status_checks.strict` is enabled
  (`failure_mode` `strict_enabled`; strict MUST be OFF), or a required
  check has no matching ci.yml job (`failure_mode`
  `required_check_missing_from_ci`).

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

__all__: list[str] = []


_CI_YML_PATH = Path(".github/workflows/ci.yml")
_MATRIX_TARGET_LINE = re.compile(r"^\s*-\s*([\w-]+)\s*$")
_MATRIX_HEADER = re.compile(r"^\s*matrix:\s*$")
_MATRIX_TARGET_KEY = re.compile(r"^\s*target:\s*$")
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


@dataclass(frozen=True, kw_only=True)
class _ProtectionAbsent:
    """The API definitively reported master has no branch protection.

    Distinct from the graceful-skip case (represented by `None`): an
    admin-scoped token read master's protection and GitHub answered
    with the canonical "Branch not protected" 404. This is a
    fail-trigger, not a can't-read skip.
    """


@dataclass(frozen=True, kw_only=True)
class _RequiredContexts:
    """The API succeeded; carries master's required_status_checks object.

    `contexts` is the required-checks list; `strict` is the
    require-branches-up-to-date flag, which MUST be OFF per livespec
    NFR §"CI as a merge gate (branch protection)".
    """

    contexts: frozenset[str]
    strict: bool


def _parse_ci_matrix(*, source: str) -> set[str]:
    """Extract the matrix.target job names from ci.yml.

    Walks the file line-by-line looking for the `matrix:` table,
    then the `target:` key, then bullet entries that look like
    job slugs (`- check-foo`). Stops collecting once a non-bullet
    non-comment line outside the bullet block is hit.
    """
    targets: set[str] = set()
    in_matrix = False
    in_target_list = False
    for raw in source.splitlines():
        if _MATRIX_HEADER.match(raw):
            in_matrix = True
            in_target_list = False
            continue
        if not in_matrix:
            continue
        if _MATRIX_TARGET_KEY.match(raw):
            in_target_list = True
            continue
        if in_target_list:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            match = _MATRIX_TARGET_LINE.match(raw)
            if match is None:
                # End of bullet list (next YAML key or section).
                in_target_list = False
                continue
            targets.add(match.group(1))
    return targets


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


def _fetch_required_contexts(
    *, log: structlog.stdlib.BoundLogger
) -> _RequiredContexts | _ProtectionAbsent | None:
    """Fetch master branch protection's required_status_checks object.

    Three-way result:

    - `_RequiredContexts` — the API succeeded; carries master's
      required-checks list (possibly empty) AND the `strict` flag.
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
    # Read the full required_status_checks OBJECT (not the bare
    # /contexts sub-endpoint) so the response carries both `strict` and
    # `contexts`: the strict-off assertion needs the `strict` flag, which
    # the /contexts list endpoint does not return.
    api_path = f"repos/{owner_repo}/branches/master/protection/required_status_checks"
    completed = subprocess.run(
        ["gh", "api", api_path],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        combined = f"{completed.stdout}\n{completed.stderr}"
        if _NOT_PROTECTED_MARKER in combined:
            # Definitive "absent": an admin-scoped token read master and
            # GitHub answered with the canonical "Branch not protected"
            # 404. This is the fail-trigger, NOT a can't-read skip.
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
) -> int:
    """Two-direction comparison between required checks and ci.yml matrix.

    Returns `4` when one or more required checks have no matching ci.yml
    job (the drift the gate prevents); `0` otherwise. Extra ci.yml jobs
    not in the required list are warnings only (optional jobs allowed).
    """
    missing_from_ci = required - matrix_targets
    not_required = matrix_targets - required
    for name in sorted(missing_from_ci):
        log.error(
            "required check has no matching ci.yml job",
            check=name,
            failure_mode="required_check_missing_from_ci",
            hint="add to ci.yml matrix or remove from branch protection",
        )
    for name in sorted(not_required):
        log.warning(
            "ci.yml job is not in branch-protection required list",
            check=name,
            hint="optional jobs are allowed; informational only",
        )
    if missing_from_ci:
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
    matrix_targets = _parse_ci_matrix(source=ci_yml.read_text(encoding="utf-8"))
    if not matrix_targets:
        log.error("ci.yml matrix.target is empty or unparseable", path=str(_CI_YML_PATH))
        return 1
    fetched = _fetch_required_contexts(log=log)
    if fetched is None:
        # Graceful skip: gh unavailable / unauthenticated /
        # permission-error / non-github remote. "Can't read" is
        # indistinguishable from "absent" without admin read access,
        # so do NOT fail.
        return 0
    if isinstance(fetched, _ProtectionAbsent):
        log.error(
            "master has no branch protection; required-check protection MUST be enabled",
            failure_mode="protection_absent",
            hint=(
                "enable required-check branch protection on master "
                "per livespec/SPECIFICATION/non-functional-requirements.md "
                '§"CI as a merge gate (branch protection)"; an unprotected '
                "master lets PRs auto-merge before CI finishes and lets a "
                "red PR land on master"
            ),
        )
        return 4
    if fetched.strict:
        log.error(
            "required_status_checks.strict is enabled; strict MUST be OFF",
            failure_mode="strict_enabled",
            hint=(
                "disable strict (require-branches-up-to-date) on master's "
                "branch protection per livespec/SPECIFICATION/"
                'non-functional-requirements.md §"CI as a merge gate '
                '(branch protection)"; strict makes GitHub keep a behind PR '
                "current by merging master into its branch, injecting a "
                "merge commit that violates required_linear_history and "
                "buries the per-commit Red-Green-Replay TDD trailers"
            ),
        )
        return 4
    return _run_alignment_gate(log=log, required=fetched.contexts, matrix_targets=matrix_targets)


if __name__ == "__main__":
    raise SystemExit(main())
