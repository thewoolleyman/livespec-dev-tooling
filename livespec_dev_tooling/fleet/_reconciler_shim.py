"""The canonical master-health reconciler shim.

Child D of plan `red-master-self-healing`
(`plan/red-master-self-healing/research/001-charter-red-master-self-healing.md`,
work-item `livespec-dev-tooling-dw7dzd`). The decision layer this shim reaches
is the `master_health_*` family under `livespec_dev_tooling/cross_repo/`; the
charter's §6 "Distribution" is what this module implements: "thin shim in every
fleet repo installed and reconciled by `wire-fleet-member`; a conformance row
fails a repo whose shim is missing or drifted. Never configured by hand."

WHY `MASTER_HEALTH_WORKFLOW` IS HOMED HERE rather than beside the other
workflow path constants in `_rows_files`: `_reconcile_shims` already imports
those constants FROM `_rows_files`, so an obligation assert placed in
`_rows_files` that needed the canonical body would have to import
`_reconcile_shims` back and close a cycle. Homing the path with its bytes
leaves the dependency pointing one way — `_reconcile_shims` imports this
module, and nothing here imports either of them.

THE SHIM IS DATA, NOT A COMMITTED WORKFLOW FILE IN THIS REPOSITORY. A canonical
shim stored under `.github/workflows/` could not be written by a factory run at
all: the dispatch credential carries no `workflows` grant (livespec
`.ai/ci-gate-discipline.md` section "workflows boundary"). Data is also what the
installer needs — it PUTs these bytes into a member through the contents API —
so this is the shape the mechanism wanted anyway.
"""

from __future__ import annotations

__all__: list[str] = [
    "MASTER_HEALTH_WORKFLOW",
    "RECONCILER_SHIM_BODY",
    "REUSABLE_WORKFLOW_FILE",
    "reconciler_shim_content",
]


MASTER_HEALTH_WORKFLOW = ".github/workflows/master-health-reconcile.yml"

# The reusable workflow this shim delegates to, named separately because the
# shim body and the reusable workflow's own canonical body must agree on ONE
# file name. A shim pointing at a name the reusable workflow does not publish
# fails at dispatch time, in the member, where nothing in this repository is
# watching.
REUSABLE_WORKFLOW_FILE = "reusable-master-health-reconcile.yml"

# The canonical shim body. Only `{owner}` varies — unlike the sibling
# release-dispatch shim there is no per-member value, because every decision
# the reconciler takes is computed from forge state and the reusable workflow's
# own inputs. That uniformity is what lets a drift read be a BYTE comparison
# rather than a structural one.
#
# The trigger set is the charter's §3 "Triggers", and each leg answers a
# distinct failure of the others:
#
# - `workflow_run` on the gating CI workflow, `completed` rather than filtered
#   to failures: a run that came back GREEN is what ends an episode and closes
#   a superseded revert, and subscribing only to failures would leave that step
#   waiting for the schedule.
# - `pull_request` carries the revert's and the fix-forward's own lifecycle;
#   `labeled`/`unlabeled` are the claim mechanism, `synchronize` is a fix
#   pushing a commit, `closed` is a revert landing or a fix merging.
# - `issue_comment` carries the comment half of the same claim, which
#   `pull_request` does not deliver at all.
# - `schedule` at five minutes is deadline enforcement AND missed-event cover:
#   events are best-effort, and the hard cap is a deadline no event announces.
#
# The `@master` ref is the bootstrap-discipline ref the sibling shims use; the
# bump-pin automation rewrites it to a tag on the next release.
RECONCILER_SHIM_BODY = """\
# master-health-reconcile.yml — red-master self-healing reconciler shim.
#
# Installed by wire-fleet-member per livespec
# SPECIFICATION/non-functional-requirements.md §"Fleet membership contract".

name: Master health reconcile

on:
  workflow_run:
    workflows: [CI]
    types: [completed]
  pull_request:
    types: [opened, reopened, synchronize, labeled, unlabeled, closed]
  issue_comment:
    types: [created, edited]
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch: {{}}

jobs:
  reconcile:
    uses: {owner}/livespec-dev-tooling/.github/workflows/{reusable}@master
    secrets: inherit
"""


def reconciler_shim_content(*, owner: str, repo: str) -> str:
    """The canonical reconciler shim body rendered for one member.

    `repo` is threaded into the render rather than dropped so this renderer
    takes the SAME arguments the installer's shared `shim_content` passes every
    shim body: a renderer with a narrower signature would have to be special-
    cased there, and a special case is how the reconciler shim would come to be
    installed by a different path than its siblings.
    """
    return RECONCILER_SHIM_BODY.format(owner=owner, repo=repo, reusable=REUSABLE_WORKFLOW_FILE)
