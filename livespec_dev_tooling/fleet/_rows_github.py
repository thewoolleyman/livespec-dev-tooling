"""GitHub-side state obligation rows for the fleet-membership contract.

The obligation type "GitHub-side state" of livespec v108 section "Fleet
membership contract": Actions secret NAMES present (APP_ID +
APP_PRIVATE_KEY — names only, never values), the GitHub App
installation, branch protection present AND aligned (per livespec
section "CI as a merge gate (branch protection)"), and the `livespec-sibling`
topic. Reads that need scopes a given token lacks (secrets list,
branch protection under the App token; installation listing under a
user PAT) yield skips, never false reds — the operator-local run and
the App-token workflow runs jointly cover every row.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import cast

_VENDOR_DIR = Path(__file__).resolve().parent.parent / "_vendor"
if str(_VENDOR_DIR) not in sys.path:
    sys.path.insert(0, str(_VENDOR_DIR))

from returns.io import IOFailure, IOResult  # noqa: E402  — vendor-path-aware import.
from returns.unsafe import unsafe_perform_io  # noqa: E402  — vendor-path-aware import.

from livespec_dev_tooling.checks._ci_job_names import (  # noqa: E402
    parse_ci_matrix,
    parse_top_level_jobs,
)
from livespec_dev_tooling.fleet._ci_workflow_source import (  # noqa: E402
    CiWorkflowUnread,
    ci_workflow_text,
)
from livespec_dev_tooling.fleet._context import (  # noqa: E402
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
    gh_answer,
)
from livespec_dev_tooling.fleet._invocation_failure import (  # noqa: E402
    InvocationNotPerformed,
)

__all__: list[str] = [
    "REQUIRED_MERGE_SETTINGS",
    "REQUIRED_SECRET_NAMES",
    "SIBLING_TOPIC",
    "assert_app_installation",
    "assert_branch_protection",
    "assert_delete_branch_on_merge",
    "assert_merge_settings",
    "assert_secret_names",
    "assert_topic",
    "member_ci_check_names",
    "member_matrix_targets",
    # A RE-EXPORT, not a definition: `parse_ci_matrix` is owned by
    # `checks/_ci_job_names.py` and shared with the repo-local
    # `branch_protection_alignment` check. Naming it here keeps the fleet
    # surface stable for this module's existing importers.
    "parse_ci_matrix",
]


REQUIRED_SECRET_NAMES = ("APP_ID", "APP_PRIVATE_KEY")
SIBLING_TOPIC = "livespec-sibling"

# Repo-level merge-strategy settings the fleet mandates per livespec
# NFR section "Commit and merge discipline": `master` accepts only
# rebase-merge, so merge-commit and squash-merge are forbidden at the
# GitHub repo-settings level. `allow_auto_merge` is enabled so
# `gh pr merge --auto` (the fleet merge driver, per section "CI as a merge
# gate (branch protection)") is available. A freshly-scaffolded repo
# defaults to GitHub's `allow_merge_commit: true`, so this is a real
# obligation, not a no-op.
REQUIRED_MERGE_SETTINGS: dict[str, bool] = {
    "allow_merge_commit": False,
    "allow_squash_merge": False,
    "allow_rebase_merge": True,
    "allow_auto_merge": True,
}

# GitHub's branch-protection endpoints return this exact message only
# when an admin-scoped token reads a genuinely unprotected branch; a
# token without the admin read scope gets a generic "Not Found", which
# stays a skip. Mirrors the sibling `branch_protection_alignment` check.
_NOT_PROTECTED_MARKER = "Branch not protected"


def member_matrix_targets(
    *, ctx: FleetContext, member: FleetMember
) -> IOResult[set[str], CiWorkflowUnread]:
    """The member's ci.yml `matrix.target` legs — EMPTY when it declares none.

    An empty set is an ANSWER: the file was obtained (or definitively does
    not exist) and declares no matrix legs. It used to be spelled `None`,
    the same value an unreadable ci.yml produced, so a caller could not
    tell "this member has no matrix" from "this run never read it".
    """
    return ci_workflow_text(ctx=ctx, member=member).map(
        lambda text: set() if text is None else parse_ci_matrix(source=text)
    )


def member_ci_check_names(
    *, ctx: FleetContext, member: FleetMember
) -> IOResult[set[str], CiWorkflowUnread]:
    """Every ci.yml name a required status check may legitimately match.

    The union of the member's `matrix.target` legs and its top-level job
    ids / literal `name:` values, from ONE read of ci.yml. Both halves are
    load-bearing: per livespec NFR section "CI as a merge gate (branch
    protection)" the required-check set is exactly the single top-level
    all-green gate job, which is NOT a matrix leg — so a matrix-only view
    reports the mandated configuration as a phantom check.

    🔴 THIS FUNCTION IS NOT IN THE RAILWAY CHECK'S COUNT, and was converted
    anyway. Its only consumer lives in this same module, so it crosses no
    boundary the consumption graph can see and `_find_offenders` never
    convicted it — while its TWIN `member_matrix_targets`, identical in
    shape, is convicted because `_reconcile` imports it. The count is a
    conviction tally, not a defect tally, and this one carried the worse
    defect of the pair.
    """
    return ci_workflow_text(ctx=ctx, member=member).map(
        lambda text: set()
        if text is None
        else parse_ci_matrix(source=text) | parse_top_level_jobs(source=text)
    )


def assert_secret_names(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """APP_ID + APP_PRIVATE_KEY exist as Actions secret NAMES on the member."""
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{member.repo}/actions/secrets")
    if not isinstance(payload, dict):
        return RowSkip(reason=f"{member.repo}: secrets list unreadable (needs admin scope)")
    secrets = cast("dict[str, object]", payload).get("secrets")
    if not isinstance(secrets, list):
        return RowSkip(reason=f"{member.repo}: secrets payload shape unexpected")
    names = {
        cast("str", cast("dict[str, object]", entry).get("name"))
        for entry in cast("list[object]", secrets)
        if isinstance(entry, dict) and isinstance(cast("dict[str, object]", entry).get("name"), str)
    }
    missing = [name for name in REQUIRED_SECRET_NAMES if name not in names]
    if missing:
        return RowFinding(
            message=f"{member.repo}: missing Actions secret name(s): {', '.join(missing)}"
        )
    return RowPass()


def assert_app_installation(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The fleet GitHub App's installation covers the member repo."""
    installed = ctx.installed_repos()
    if installed is None:
        return RowSkip(
            reason=(
                f"{member.repo}: installation repositories unreadable "
                "(needs an App installation token)"
            )
        )
    if member.repo in installed:
        return RowPass()
    return RowFinding(message=f"{member.repo}: GitHub App installation does not cover this repo")


def _protection_problems(
    *, ctx: FleetContext, member: FleetMember, payload: dict[str, object]
) -> tuple[list[str], str | None]:
    """Misalignment messages, plus why the phantom-check comparison did not run.

    The second element is the whole point of this signature. The phantom
    comparison needs the member's ci.yml names; when this run could not
    obtain them the comparison DOES NOT HAPPEN, and returning problems
    alone made that indistinguishable from "the comparison ran and found
    nothing wrong". `assert_branch_protection` then returned `RowPass` —
    a member whose required checks can never report, and whose every merge
    would therefore deadlock, was certified ALIGNED because a read failed.
    A can't-read SKIPS; it does not pass (livespec-dev-tooling-6ge).
    """
    problems: list[str] = []
    enforce = payload.get("enforce_admins")
    if not (isinstance(enforce, dict) and cast("dict[str, object]", enforce).get("enabled")):
        problems.append("enforce_admins is not enabled")
    checks = payload.get("required_status_checks")
    if not isinstance(checks, dict):
        problems.append("required_status_checks is absent")
        return problems, None
    checks_map = cast("dict[str, object]", checks)
    if checks_map.get("strict"):
        problems.append(
            "required_status_checks.strict is enabled but must be OFF "
            "(per the strict-off merge-gate rule)"
        )
    contexts_raw = checks_map.get("contexts")
    contexts: set[str] = (
        {entry for entry in cast("list[object]", contexts_raw) if isinstance(entry, str)}
        if isinstance(contexts_raw, list)
        else set()
    )
    if not contexts:
        problems.append("required-check set is empty")
        return problems, None
    names = member_ci_check_names(ctx=ctx, member=member)
    if isinstance(names, IOFailure):
        return problems, unsafe_perform_io(names.failure()).detail
    # An EMPTY name set is now compared rather than skipped. A member whose
    # ci.yml names nothing while branch protection requires checks has a
    # phantom for every one of them — the definitive form of exactly what
    # this loop looks for, and previously the case that produced a pass.
    for name in sorted(contexts - unsafe_perform_io(names.unwrap())):
        problems.append(f"required check {name} matches no ci.yml matrix leg or top-level job")
    return problems, None


def _protection_payload(*, stdout: str) -> dict[str, object] | None:
    """The protection payload as an object map, or None when it is neither.

    Extracted to keep `assert_branch_protection` under the six-return cap the
    conversion's new failure arm pushed it past. The two unusable shapes —
    unparseable bytes and a parsed non-object — collapse to one answer because
    the row responds to both identically: it skips, since neither is evidence
    about the member's protection.
    """
    try:
        payload = cast("object", json.loads(stdout))
    except json.JSONDecodeError:
        return None
    return cast("dict[str, object]", payload) if isinstance(payload, dict) else None


def assert_branch_protection(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Canonical-ref branch protection present AND aligned.

    The ref is resolved per member rather than assumed to be `master`,
    matching the contents and tree reads: addressing a hardcoded branch
    makes a member whose default branch is not `master` read as
    unprotected-or-unreadable whatever its real configuration.

    Aligned means: `enforce_admins`, `strict` OFF, a non-empty
    required-check set, and every required check matched by a ci.yml
    matrix leg OR a top-level ci.yml job (the direction that blocks
    merges when violated), per livespec section "CI as a merge gate (branch
    protection)". A required check matching NEITHER is a phantom that can
    never report and would deadlock every merge; a required TOP-LEVEL
    all-green gate job (the `ci-green` single-gate model the contract
    mandates) matches and is NOT flagged, even though it is not a matrix
    leg, because requiring it gates the whole matrix through its `needs:`.
    """
    ref = ctx.canonical_ref(repo=member.repo)
    result = gh_answer(
        outcome=ctx.api(path=f"repos/{ctx.owner}/{member.repo}/branches/{ref}/protection")
    )
    if isinstance(result, InvocationNotPerformed):
        # Not "needs admin scope": that diagnostic guesses at the TOKEN,
        # and no token was ever presented.
        return RowSkip(reason=f"{member.repo}: {result.reason}")
    if result.returncode != 0:
        if _NOT_PROTECTED_MARKER in f"{result.stdout}\n{result.stderr}":
            return RowFinding(message=f"{member.repo}: {ref} has no branch protection")
        return RowSkip(reason=f"{member.repo}: branch protection unreadable (needs admin scope)")
    payload = _protection_payload(stdout=result.stdout)
    if payload is None:
        return RowSkip(reason=f"{member.repo}: branch protection payload unparseable or unexpected")
    problems, unverified = _protection_problems(ctx=ctx, member=member, payload=payload)
    return _protection_verdict(member=member, problems=problems, unverified=unverified)


def _protection_verdict(
    *, member: FleetMember, problems: list[str], unverified: str | None
) -> RowOutcome:
    """Turn the two halves of the alignment reading into one outcome.

    Extracted to keep `assert_branch_protection` under the six-return cap
    the new skip arm pushed it past — never by routing around the cap.

    ORDER IS LOAD-BEARING. Definitive problems are reported whatever else
    could not be checked: withholding a real misalignment because a SECOND
    read failed would trade one silence for another. Only when there is
    nothing definitive to say does the unverified comparison decide, and
    then it SKIPS rather than passing.
    """
    if problems:
        return RowFinding(message=f"{member.repo}: {'; '.join(problems)}")
    if unverified is not None:
        return RowSkip(reason=f"{member.repo}: required-check alignment unverified ({unverified})")
    return RowPass()


def assert_merge_settings(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Repo-level merge settings are rebase-only (+ auto-merge enabled).

    Per livespec NFR section "Commit and merge discipline": `master` accepts
    only rebase-merge (`allow_merge_commit` / `allow_squash_merge` OFF,
    `allow_rebase_merge` ON), with `allow_auto_merge` ON so the fleet's
    `gh pr merge --auto` driver works. A freshly-scaffolded repo
    defaults to GitHub's `allow_merge_commit: true`, so a manifest
    member that has never been reconciled fails this row.

    A READABLE repo object that simply OMITS these keys is a can't-read,
    not a misconfiguration: GitHub returns the merge-strategy fields only
    to a token with admin access to the repo, so a token lacking it sees
    a well-formed payload with the keys absent. Reading absence as `None`
    and comparing it to the required value reported every setting as
    violated on a repo whose settings were already correct, which is why
    absence is separated from present-but-wrong here.
    """
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{member.repo}")
    if not isinstance(payload, dict):
        return RowSkip(reason=f"{member.repo}: repo settings unreadable (needs admin scope)")
    settings = cast("dict[str, object]", payload)
    absent = [key for key in REQUIRED_MERGE_SETTINGS if key not in settings]
    if absent:
        return RowSkip(
            reason=(
                f"{member.repo}: merge settings unreadable (needs admin scope): "
                f"{', '.join(absent)} absent from the repo object"
            )
        )
    problems = [
        f"{key} is {settings.get(key)!r}, must be {want!r}"
        for key, want in REQUIRED_MERGE_SETTINGS.items()
        if settings.get(key) != want
    ]
    if problems:
        return RowFinding(
            message=f"{member.repo}: merge settings not rebase-only: {'; '.join(problems)}"
        )
    return RowPass()


def _delete_branch_on_merge_severity() -> str:
    """Severity lever: token-bearing runs fail; tokenless local runs warn."""
    if os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return "error"
    return "warning"


def assert_delete_branch_on_merge(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Merged PR head branches are deleted automatically for every fleet repo.

    The repo setting is read from the same repo-object payload as merge
    settings. It needs a GitHub token in real runs; tokenless local
    runs still report the offender at warning severity rather than
    silently skipping, while token-bearing contexts fail on any
    non-true value.

    "Non-true value" means a value that was actually READ. The setting is
    admin-only, so a token without admin access gets a well-formed repo
    object with the key missing; collapsing that onto `None` reported a
    violation against a repo whose setting was already `true`. Absence is
    therefore a skip at BOTH severities — an unreadable field is not a
    finding the severity lever should grade — while an explicit `False`
    still reports exactly as before. The membership test is what keeps
    absent distinguishable from a genuine `False`.
    """
    severity = _delete_branch_on_merge_severity()
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{member.repo}")
    if not isinstance(payload, dict):
        return RowSkip(reason=f"{member.repo}: repo settings unreadable (needs admin scope)")
    settings = cast("dict[str, object]", payload)
    if "delete_branch_on_merge" not in settings:
        return RowSkip(
            reason=(
                f"{member.repo}: delete_branch_on_merge unreadable (needs admin scope): "
                "absent from the repo object"
            )
        )
    setting = settings["delete_branch_on_merge"]
    if setting is True:
        return RowPass()
    return RowFinding(
        message=f"{member.repo}: delete_branch_on_merge is {setting!r}, must be True",
        severity=severity,
    )


def assert_topic(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """The member carries the `livespec-sibling` topic (discovery safety net)."""
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{member.repo}/topics")
    if not isinstance(payload, dict):
        return RowSkip(reason=f"{member.repo}: topics unreadable")
    names = cast("dict[str, object]", payload).get("names")
    if not isinstance(names, list):
        return RowSkip(reason=f"{member.repo}: topics payload shape unexpected")
    if SIBLING_TOPIC in cast("list[object]", names):
        return RowPass()
    return RowFinding(message=f"{member.repo}: missing the {SIBLING_TOPIC} topic")
