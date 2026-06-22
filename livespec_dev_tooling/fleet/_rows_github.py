"""GitHub-side state obligation rows for the fleet-membership contract.

The obligation type "GitHub-side state" of livespec v108 §"Fleet
membership contract": Actions secret NAMES present (APP_ID +
APP_PRIVATE_KEY — names only, never values), the GitHub App
installation, branch protection present AND aligned (per livespec
§"CI as a merge gate (branch protection)"), and the `livespec-sibling`
topic. Reads that need scopes a given token lacks (secrets list,
branch protection under the App token; installation listing under a
user PAT) yield skips, never false reds — the operator-local run and
the App-token workflow runs jointly cover every row.
"""

from __future__ import annotations

import json
import re
from typing import cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_files import CI_WORKFLOW

__all__: list[str] = [
    "REQUIRED_MERGE_SETTINGS",
    "REQUIRED_SECRET_NAMES",
    "SIBLING_TOPIC",
    "assert_app_installation",
    "assert_branch_protection",
    "assert_merge_settings",
    "assert_secret_names",
    "assert_topic",
    "member_matrix_targets",
    "parse_ci_matrix",
]


REQUIRED_SECRET_NAMES = ("APP_ID", "APP_PRIVATE_KEY")
SIBLING_TOPIC = "livespec-sibling"

# Repo-level merge-strategy settings the family mandates per livespec
# NFR §"Commit and merge discipline": `master` accepts only
# rebase-merge, so merge-commit and squash-merge are forbidden at the
# GitHub repo-settings level. `allow_auto_merge` is enabled so
# `gh pr merge --auto` (the family merge driver, per §"CI as a merge
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

_MATRIX_TARGET_LINE = re.compile(r"^\s*-\s*([\w-]+)\s*$")
_MATRIX_HEADER = re.compile(r"^\s*matrix:\s*$")
_MATRIX_TARGET_KEY = re.compile(r"^\s*target:\s*$")


def parse_ci_matrix(*, source: str) -> set[str]:
    """Extract `matrix.target` job names from a ci.yml source text.

    Same line-walk shape as the per-repo `branch_protection_alignment`
    check's parser (that one is module-private, so the fleet surface
    carries its own): find `matrix:`, then `target:`, then collect
    bullet entries until a non-bullet non-comment line ends the list.
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
                in_target_list = False
                continue
            targets.add(match.group(1))
    return targets


def member_matrix_targets(*, ctx: FleetContext, member: FleetMember) -> set[str] | None:
    """The member's ci.yml `matrix.target` set, or None when unreadable/empty."""
    text = ctx.file_text(repo=member.repo, path=CI_WORKFLOW)
    if text is None:
        return None
    targets = parse_ci_matrix(source=text)
    return targets or None


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
    """The family GitHub App's installation covers the member repo."""
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
) -> list[str]:
    """Misalignment messages for an existing branch protection payload."""
    problems: list[str] = []
    enforce = payload.get("enforce_admins")
    if not (isinstance(enforce, dict) and cast("dict[str, object]", enforce).get("enabled")):
        problems.append("enforce_admins is not enabled")
    checks = payload.get("required_status_checks")
    if not isinstance(checks, dict):
        problems.append("required_status_checks is absent")
        return problems
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
        return problems
    matrix = member_matrix_targets(ctx=ctx, member=member)
    if matrix is not None:
        for name in sorted(contexts - matrix):
            problems.append(f"required check {name} has no ci.yml matrix job")
    return problems


def assert_branch_protection(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Master branch protection present AND aligned.

    Aligned means: `enforce_admins`, `strict` OFF, a non-empty
    required-check set, and every required check matched by a ci.yml
    matrix job (the direction that blocks merges when violated), per
    livespec §"CI as a merge gate (branch protection)".
    """
    result = ctx.api(path=f"repos/{ctx.owner}/{member.repo}/branches/master/protection")
    if result.returncode != 0:
        if _NOT_PROTECTED_MARKER in f"{result.stdout}\n{result.stderr}":
            return RowFinding(message=f"{member.repo}: master has no branch protection")
        return RowSkip(reason=f"{member.repo}: branch protection unreadable (needs admin scope)")
    try:
        payload = cast("object", json.loads(result.stdout))
    except json.JSONDecodeError:
        return RowSkip(reason=f"{member.repo}: branch protection payload unparseable")
    if not isinstance(payload, dict):
        return RowSkip(reason=f"{member.repo}: branch protection payload shape unexpected")
    problems = _protection_problems(
        ctx=ctx, member=member, payload=cast("dict[str, object]", payload)
    )
    if problems:
        return RowFinding(message=f"{member.repo}: {'; '.join(problems)}")
    return RowPass()


def assert_merge_settings(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Repo-level merge settings are rebase-only (+ auto-merge enabled).

    Per livespec NFR §"Commit and merge discipline": `master` accepts
    only rebase-merge (`allow_merge_commit` / `allow_squash_merge` OFF,
    `allow_rebase_merge` ON), with `allow_auto_merge` ON so the family's
    `gh pr merge --auto` driver works. A freshly-scaffolded repo
    defaults to GitHub's `allow_merge_commit: true`, so a manifest
    member that has never been reconciled fails this row.
    """
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{member.repo}")
    if not isinstance(payload, dict):
        return RowSkip(reason=f"{member.repo}: repo settings unreadable (needs admin scope)")
    settings = cast("dict[str, object]", payload)
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
