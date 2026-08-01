"""_reconcile_shims — provision the three pin-and-bump shim workflows.

Split out of `_reconcile` to keep that module under the 250-LLOC hard
ceiling, which the ci.yml railway conversion pushed it past (264). The
shim surface is the largest self-contained group there: it is the only
reconcile that WRITES repository content rather than repository settings,
and it owns the canonical shim bodies.

⛔ READ RATHER THAN RELOCATED, per this thread's standing rule, and the
result is a NEGATIVE one worth recording so it is not re-derived:
`reconcile_shim_workflows`' branch probe reads every non-zero `gh` exit as
"the shim branch does not exist" and goes on to CREATE it. The `404` case
is the real one; a `403` or `5xx` is not. That fusion does NOT fail open —
the subsequent `POST /git/refs` on an existing ref is refused by GitHub and
`_gh_failed` surfaces it — so it is loud rather than silent, and it is left
alone here. The `InvocationNotPerformed` arm, which WOULD have created a
branch off a probe that never ran, was already split out (row 30).
"""

from __future__ import annotations

import base64
import json
from typing import cast

from livespec_dev_tooling.fleet._context import (
    FleetContext,
    FleetMember,
    RowFinding,
    RowOutcome,
    RowPass,
    RowSkip,
    gh_answer,
)
from livespec_dev_tooling.fleet._invocation_failure import InvocationNotPerformed
from livespec_dev_tooling.fleet._reconcile import _gh_failed
from livespec_dev_tooling.fleet._rows_files import (
    BUMP_PIN_WORKFLOW,
    PIN_FRESHNESS_WORKFLOW,
    RELEASE_DISPATCH_WORKFLOW,
)

__all__: list[str] = [
    "SHIM_BRANCH",
    "reconcile_shim_workflows",
    "shim_content",
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


def _open_shim_pr(*, ctx: FleetContext, member: FleetMember, missing: list[str]) -> RowOutcome:
    """Create the shim branch off the member's default branch and open the PR.

    Both the branch-point sha lookup and the PR `base` resolve through
    `FleetContext.canonical_ref` (livespec-dev-tooling-17o): a PR based
    on a hardcoded `master` fails outright on a main-default repo, so
    shim provisioning could never complete there.
    """
    repo_path = f"repos/{ctx.owner}/{member.repo}"
    base_ref = ctx.canonical_ref(repo=member.repo)
    head_ref = ctx.api_object(path=f"{repo_path}/git/ref/heads/{base_ref}")
    sha_obj = (
        cast("dict[str, object]", head_ref).get("object") if isinstance(head_ref, dict) else None
    )
    sha = cast("dict[str, object]", sha_obj).get("sha") if isinstance(sha_obj, dict) else None
    if not isinstance(sha, str):
        return RowFinding(message=f"{member.repo}: cannot resolve {base_ref} sha for shim PR")
    ref_body = json.dumps({"ref": f"refs/heads/{SHIM_BRANCH}", "sha": sha})
    branch_failure = _gh_failed(
        outcome=ctx.api(path=f"{repo_path}/git/refs", method="POST", body=ref_body),
        note=f"{member.repo}: creating shim branch failed",
    )
    if branch_failure is not None:
        return branch_failure
    for path in missing:
        content = shim_content(path=path, ctx=ctx, member=member)
        put_body = json.dumps(
            {
                "message": f"chore(fleet): add {path} shim via wire-fleet-member",
                "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "branch": SHIM_BRANCH,
            }
        )
        put_failure = _gh_failed(
            outcome=ctx.api(path=f"{repo_path}/contents/{path}", method="PUT", body=put_body),
            note=f"{member.repo}: adding {path} to shim branch failed",
        )
        if put_failure is not None:
            return put_failure
    pr_body = json.dumps(
        {
            "title": "chore(fleet): add missing pin-and-bump shim workflows",
            "head": SHIM_BRANCH,
            "base": base_ref,
            "body": (
                "Opened by wire-fleet-member per livespec "
                'SPECIFICATION/non-functional-requirements.md §"Fleet membership '
                f'contract". Missing shims: {", ".join(missing)}.'
            ),
        }
    )
    created_failure = _gh_failed(
        outcome=ctx.api(path=f"{repo_path}/pulls", method="POST", body=pr_body),
        note=f"{member.repo}: opening shim PR failed",
    )
    if created_failure is not None:
        return created_failure
    return RowPass(note=f"opened shim PR for {', '.join(missing)} (pending merge)")


def reconcile_shim_workflows(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Open ONE PR adding every missing shim workflow (idempotent).

    Shared by all three shim rows; the per-run once-marker and the
    pre-existing-branch check keep repeat invocations from opening
    duplicate PRs.
    """
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(
            reason=f"{member.repo}: default-branch tree unreadable; cannot reconcile shims"
        )
    missing = [path for path in _SHIM_WORKFLOWS if path not in tree.paths]
    if not missing:
        return RowPass(note="all shim workflows present")
    if not ctx.once(key=f"shim-pr:{member.repo}"):
        return RowPass(note="shim PR already handled in this run")
    branch_probe = gh_answer(
        outcome=ctx.api(path=f"repos/{ctx.owner}/{member.repo}/git/ref/heads/{SHIM_BRANCH}")
    )
    if isinstance(branch_probe, InvocationNotPerformed):
        # NOT a missing branch. Reading it as one would send this run on
        # to CREATE a shim branch whose existence it never established.
        return RowSkip(reason=f"{member.repo}: {branch_probe.reason}")
    if branch_probe.returncode == 0:
        return RowPass(note=f"shim branch {SHIM_BRANCH} already exists (PR pending merge)")
    return _open_shim_pr(ctx=ctx, member=member, missing=missing)
