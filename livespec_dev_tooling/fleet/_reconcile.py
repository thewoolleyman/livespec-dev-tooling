"""Reconcile logic for the fleet-membership contract (`wire-fleet-member`).

The wiring side of the shared contract definition (livespec v108
§"Fleet membership contract", "assert mode is CI; reconcile mode is
wiring"): push the required secret NAMES from the operator's
1Password-wrapper-provided environment (values flow env→stdin, never
argv / logs / outcomes), set branch protection derived from the
member's own ci.yml matrix, apply the `livespec-sibling` topic, and
open one shim-workflow PR for any missing pin-and-bump shims. Every
operation is idempotent — re-running against an already-wired member
changes nothing. None of it depends on a dev-tooling release going
out (the no-circular-gating rule).
"""

from __future__ import annotations

import base64
import json
import os
from typing import cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
)
from livespec_dev_tooling.fleet._rows_files import (
    BUMP_PIN_WORKFLOW,
    PIN_FRESHNESS_WORKFLOW,
    RELEASE_DISPATCH_WORKFLOW,
)
from livespec_dev_tooling.fleet._rows_github import (
    REQUIRED_MERGE_SETTINGS,
    REQUIRED_SECRET_NAMES,
    SIBLING_TOPIC,
    member_matrix_targets,
)

__all__: list[str] = [
    "SHIM_BRANCH",
    "reconcile_branch_protection",
    "reconcile_merge_settings",
    "reconcile_secret_names",
    "reconcile_shim_workflows",
    "reconcile_topic",
]


SHIM_BRANCH = "wire-fleet-member/shim-workflows"

_SHIM_WORKFLOWS = (BUMP_PIN_WORKFLOW, PIN_FRESHNESS_WORKFLOW, RELEASE_DISPATCH_WORKFLOW)

# Canonical shim bodies, mirroring livespec-dev-tooling's own committed
# shims (the reusable workflows these `uses:` lines target live in this
# repo, so this repo is the canonical source for the shim shape). The
# `@master` ref is the bootstrap-discipline ref; the bump-pin
# automation rewrites it to a tag on the next release. Only
# release-dispatch.yml is member-specific (its `source_repo`).
_BUMP_PIN_SHIM = """\
# bump-pin-from-dispatch.yml — sibling-released handler shim.
#
# Installed by wire-fleet-member per livespec
# SPECIFICATION/non-functional-requirements.md §"Fleet membership contract".

name: Bump pin from sibling dispatch

on:
  repository_dispatch:
    types: [sibling-released]

jobs:
  bump:
    uses: {owner}/livespec-dev-tooling/.github/workflows/reusable-bump-pin-from-dispatch.yml@master
    secrets: inherit
    with:
      source_repo: ${{{{ github.event.client_payload.source_repo }}}}
      tag: ${{{{ github.event.client_payload.tag }}}}
      release_url: ${{{{ github.event.client_payload.release_url }}}}
"""

_PIN_FRESHNESS_SHIM = """\
# pin-freshness.yml — periodic pin-staleness safety-net shim.
#
# Installed by wire-fleet-member per livespec
# SPECIFICATION/non-functional-requirements.md §"Fleet membership contract".

name: Pin freshness sweep

on:
  schedule:
    - cron: '0 13 * * *'
  workflow_dispatch: {{}}

jobs:
  freshness:
    uses: {owner}/livespec-dev-tooling/.github/workflows/reusable-pin-freshness.yml@master
    secrets: inherit
"""

_RELEASE_DISPATCH_SHIM = """\
# release-dispatch.yml — fan-out shim for cross-repo coordination.
#
# Installed by wire-fleet-member per livespec
# SPECIFICATION/non-functional-requirements.md §"Fleet membership contract".

name: Release dispatch (fan-out to siblings)

on:
  release:
    types: [published]

jobs:
  dispatch:
    uses: {owner}/livespec-dev-tooling/.github/workflows/reusable-release-dispatch.yml@master
    secrets: inherit
    with:
      source_repo: {repo}
      tag: ${{{{ github.event.release.tag_name }}}}
      release_url: ${{{{ github.event.release.html_url }}}}
"""

_SHIM_BODIES = {
    BUMP_PIN_WORKFLOW: _BUMP_PIN_SHIM,
    PIN_FRESHNESS_WORKFLOW: _PIN_FRESHNESS_SHIM,
    RELEASE_DISPATCH_WORKFLOW: _RELEASE_DISPATCH_SHIM,
}


def shim_content(*, path: str, ctx: FleetContext, member: FleetMember) -> str:
    """Render the canonical shim body for `path` against the member."""
    return _SHIM_BODIES[path].format(owner=ctx.owner, repo=member.repo)


def reconcile_secret_names(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Push APP_ID + APP_PRIVATE_KEY from env via `gh secret set` (stdin only).

    The operator invokes wire-fleet-member under the 1Password
    environment wrapper, so the canonical values are present as env
    vars; they flow to GitHub via stdin and are never echoed.
    """
    for name in REQUIRED_SECRET_NAMES:
        value = os.environ.get(name)
        if value is None:
            return RowFinding(
                message=(
                    f"{member.repo}: env var {name} absent — invoke under "
                    "with-livespec-env.sh so the 1Password projection provides it"
                )
            )
        result = ctx.run_gh(
            args=["secret", "set", name, "--repo", f"{ctx.owner}/{member.repo}"],
            stdin=value,
        )
        if result.returncode != 0:
            return RowFinding(message=f"{member.repo}: gh secret set {name} failed")
    return RowPass(note="secrets pushed from env (values via stdin, never logged)")


def reconcile_topic(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Apply the `livespec-sibling` topic, preserving existing topics."""
    payload = ctx.api_object(path=f"repos/{ctx.owner}/{member.repo}/topics")
    if not isinstance(payload, dict):
        return RowSkip(reason=f"{member.repo}: topics unreadable; cannot reconcile")
    names_raw = cast("dict[str, object]", payload).get("names")
    if not isinstance(names_raw, list):
        return RowSkip(reason=f"{member.repo}: topics payload shape unexpected")
    names = [entry for entry in cast("list[object]", names_raw) if isinstance(entry, str)]
    if SIBLING_TOPIC in names:
        return RowPass(note="topic already present")
    body = json.dumps({"names": [*names, SIBLING_TOPIC]})
    result = ctx.api(path=f"repos/{ctx.owner}/{member.repo}/topics", method="PUT", body=body)
    if result.returncode != 0:
        return RowFinding(message=f"{member.repo}: applying {SIBLING_TOPIC} topic failed")
    return RowPass(note=f"applied {SIBLING_TOPIC} topic")


def reconcile_branch_protection(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Set master branch protection from the member's own ci.yml matrix."""
    matrix = member_matrix_targets(ctx=ctx, member=member)
    if matrix is None:
        return RowFinding(
            message=(
                f"{member.repo}: cannot derive required checks (ci.yml unreadable or "
                "matrix empty); set branch protection manually"
            )
        )
    body = json.dumps(
        {
            "required_status_checks": {"strict": False, "contexts": sorted(matrix)},
            "enforce_admins": True,
            "required_pull_request_reviews": None,
            "restrictions": None,
        }
    )
    result = ctx.api(
        path=f"repos/{ctx.owner}/{member.repo}/branches/master/protection",
        method="PUT",
        body=body,
    )
    if result.returncode != 0:
        return RowFinding(message=f"{member.repo}: setting branch protection failed")
    return RowPass(note="branch protection set (strict=off + enforce_admins + ci matrix checks)")


def reconcile_merge_settings(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Set repo-level merge settings to rebase-only (+ auto-merge enabled).

    PATCHes the repo object with the family-mandated merge-strategy
    flags (livespec NFR §"Commit and merge discipline"): merge-commit
    and squash-merge OFF, rebase-merge ON, auto-merge ON. Idempotent —
    re-PATCHing an already-rebase-only repo changes nothing.
    """
    body = json.dumps(dict(REQUIRED_MERGE_SETTINGS))
    result = ctx.api(path=f"repos/{ctx.owner}/{member.repo}", method="PATCH", body=body)
    if result.returncode != 0:
        return RowFinding(message=f"{member.repo}: setting merge settings failed")
    return RowPass(note="merge settings set (rebase-only + auto-merge)")


def _open_shim_pr(*, ctx: FleetContext, member: FleetMember, missing: list[str]) -> RowOutcome:
    """Create the shim branch, add each missing shim file, open the PR."""
    repo_path = f"repos/{ctx.owner}/{member.repo}"
    master_ref = ctx.api_object(path=f"{repo_path}/git/ref/heads/master")
    sha_obj = (
        cast("dict[str, object]", master_ref).get("object")
        if isinstance(master_ref, dict)
        else None
    )
    sha = cast("dict[str, object]", sha_obj).get("sha") if isinstance(sha_obj, dict) else None
    if not isinstance(sha, str):
        return RowFinding(message=f"{member.repo}: cannot resolve master sha for shim PR")
    ref_body = json.dumps({"ref": f"refs/heads/{SHIM_BRANCH}", "sha": sha})
    if ctx.api(path=f"{repo_path}/git/refs", method="POST", body=ref_body).returncode != 0:
        return RowFinding(message=f"{member.repo}: creating shim branch failed")
    for path in missing:
        content = shim_content(path=path, ctx=ctx, member=member)
        put_body = json.dumps(
            {
                "message": f"chore(fleet): add {path} shim via wire-fleet-member",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": SHIM_BRANCH,
            }
        )
        put = ctx.api(path=f"{repo_path}/contents/{path}", method="PUT", body=put_body)
        if put.returncode != 0:
            return RowFinding(message=f"{member.repo}: adding {path} to shim branch failed")
    pr_body = json.dumps(
        {
            "title": "chore(fleet): add missing pin-and-bump shim workflows",
            "head": SHIM_BRANCH,
            "base": "master",
            "body": (
                "Opened by wire-fleet-member per livespec "
                'SPECIFICATION/non-functional-requirements.md §"Fleet membership '
                f'contract". Missing shims: {", ".join(missing)}.'
            ),
        }
    )
    created = ctx.api(path=f"{repo_path}/pulls", method="POST", body=pr_body)
    if created.returncode != 0:
        return RowFinding(message=f"{member.repo}: opening shim PR failed")
    return RowPass(note=f"opened shim PR for {', '.join(missing)} (pending merge)")


def reconcile_shim_workflows(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Open ONE PR adding every missing shim workflow (idempotent).

    Shared by all three shim rows; the per-run once-marker and the
    pre-existing-branch check keep repeat invocations from opening
    duplicate PRs.
    """
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(reason=f"{member.repo}: master tree unreadable; cannot reconcile shims")
    missing = [path for path in _SHIM_WORKFLOWS if path not in tree.paths]
    if not missing:
        return RowPass(note="all shim workflows present")
    if not ctx.once(key=f"shim-pr:{member.repo}"):
        return RowPass(note="shim PR already handled in this run")
    branch_probe = ctx.api(path=f"repos/{ctx.owner}/{member.repo}/git/ref/heads/{SHIM_BRANCH}")
    if branch_probe.returncode == 0:
        return RowPass(note=f"shim branch {SHIM_BRANCH} already exists (PR pending merge)")
    return _open_shim_pr(ctx=ctx, member=member, missing=missing)
