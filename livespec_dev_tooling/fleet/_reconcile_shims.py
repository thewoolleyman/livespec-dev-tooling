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
from livespec_dev_tooling.fleet._reconciler_shim import (
    MASTER_HEALTH_WORKFLOW,
    RECONCILER_SHIM_TEMPLATE,
    reconciler_shim_content,
)
from livespec_dev_tooling.fleet._rows_files import (
    BUMP_PIN_WORKFLOW,
    PIN_FRESHNESS_WORKFLOW,
    RELEASE_DISPATCH_WORKFLOW,
)

__all__: list[str] = [
    "SHIM_BRANCH",
    "reconcile_master_health_shim",
    "reconcile_shim_workflows",
    "shim_content",
]


SHIM_BRANCH = "wire-fleet-member/shim-workflows"

# The master-health reconciler shim rides the SAME provisioning mechanism as
# the three pin-and-bump shims rather than growing a second one, and that reuse
# is what gives the Definition of Done's "a second run leaves the repository
# unchanged" for free: the all-present pass, the pending-shim-branch pass and
# the per-run once-marker below are already the three idempotence guards this
# shim needs. Its canonical body is homed in `_reconciler_shim` because the
# drift read in `reconcile_master_health_shim` must render the same bytes this
# install writes (work-item livespec-dev-tooling-dw7dzd, child D of plan
# red-master-self-healing).
_SHIM_WORKFLOWS = (
    BUMP_PIN_WORKFLOW,
    PIN_FRESHNESS_WORKFLOW,
    RELEASE_DISPATCH_WORKFLOW,
    MASTER_HEALTH_WORKFLOW,
)

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
    MASTER_HEALTH_WORKFLOW: RECONCILER_SHIM_TEMPLATE,
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


def reconcile_master_health_shim(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Discover the member's reconciler shim; install it where it is ABSENT.

    ⛔ WIRE-FLEET-MEMBER'S OWN STEP, DELIBERATELY NOT AN OBLIGATION ROW, and the
    reason is arming ORDER rather than taste. A fleet conformance row convicting
    a missing shim is correct only once every member carries one; registered
    before that it reds the central lane for the whole fleet — and the FIRST
    repository it reds is livespec-dev-tooling itself, whose own
    `fleet_conformance --member-ci` leg reads its own rows (measured on
    livespec-dev-tooling draft pull request #2477, where `own_failing_rows` was
    exactly that row against ten members). Enforcement is a separate child of
    plan `red-master-self-healing`; this is provisioning, and it needs no row to
    find its own work. `plan/rop-railway-enforcement/` records what the fleet
    already paid for arming ahead of adoption: `46c5dab` reddened five repos and
    was reverted in `f4247110`.

    Three outcomes, and the split between the last two is load-bearing:

    - ABSENT is repaired, through the shared `reconcile_shim_workflows` install
      that the three pin-and-bump shims already use — ONE pull request carrying
      every shim the member lacks, and a no-op on a second run.
    - DRIFTED is REPORTED with its remedy. A hand-edited shim keeps its path, so
      presence alone takes it for conforming while its triggers, its `uses:`
      target or its `secrets: inherit` may all have been changed — and a
      reconciler that is never invoked goes quiet exactly when a master is red.
      Overwriting a file a repository has committed is a wider decision than
      this slice takes; the remedy named here reaches the same end through the
      install path above.
    - UNREADABLE is neither. Treating bytes this run could not read as bytes
      that DIFFER would accuse every member a scoped token cannot see into, for
      a fact about the token rather than about the repository (the
      `livespec-dev-tooling-6ge` discipline: can't-read is never reported as
      different).
    """
    tree = ctx.tree(repo=member.repo)
    if not tree.readable:
        return RowSkip(
            reason=(
                f"{member.repo}: default-branch tree unreadable; "
                "cannot reconcile the master-health reconciler shim"
            )
        )
    if MASTER_HEALTH_WORKFLOW not in tree.paths:
        return reconcile_shim_workflows(ctx=ctx, member=member)
    committed = ctx.file_text(repo=member.repo, path=MASTER_HEALTH_WORKFLOW)
    if committed is None:
        return RowSkip(
            reason=f"{member.repo}: {MASTER_HEALTH_WORKFLOW} unreadable; drift not established"
        )
    if committed != reconciler_shim_content(owner=ctx.owner):
        return RowFinding(
            message=(
                f"{member.repo}: {MASTER_HEALTH_WORKFLOW} has DRIFTED from the canonical "
                "master-health reconciler shim — restore it by deleting the file in a "
                "repo-local commit and re-running wire-fleet-member, which writes the "
                "canonical body (livespec-dev-tooling "
                "plan/red-master-self-healing, child D)"
            )
        )
    return RowPass(note=f"{MASTER_HEALTH_WORKFLOW} is the canonical reconciler shim")


def reconcile_shim_workflows(*, ctx: FleetContext, member: FleetMember) -> RowOutcome:
    """Open ONE PR adding every missing shim workflow (idempotent).

    Shared by all three shim rows AND by `reconcile_master_health_shim` above;
    the per-run once-marker and the pre-existing-branch check keep repeat
    invocations from opening duplicate PRs.
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
