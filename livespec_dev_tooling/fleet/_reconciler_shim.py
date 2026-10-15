"""The canonical master-health reconciler shim every fleet repository carries.

Child D of plan `red-master-self-healing` (epic `livespec-dev-tooling-zcp5vb`,
work-item `livespec-dev-tooling-dw7dzd`) — the DISTRIBUTION half of the
reconciler whose pure decision core child C1 shipped under
`livespec_dev_tooling/cross_repo/master_health_*.py` and whose decisions
`docs/master-health-reconciler.md` records.

THE SHIM IS DATA, NOT A FILE IN THIS TREE. It is the body `wire-fleet-member`
writes into a MEMBER repository at `MASTER_HEALTH_WORKFLOW`, so it lives here
as the one canonical rendering source: the install path and the conformance row
that convicts drift both read it, and a shim committed in a member repo that
differs from this body by one byte is a finding rather than a surprise. Charter
item 6 is what forbids the alternative — the shim is never configured by hand.

THE `uses:` REFERENCE AND THE WORKFLOW IT NAMES ARE ONE EDIT. The reusable
workflow's path is `REUSABLE_RECONCILER_WORKFLOW` and the shim interpolates it,
so renaming the central workflow cannot leave the fleet's shims pointing at a
path that no longer resolves.
"""

from __future__ import annotations

__all__: list[str] = [
    "MASTER_HEALTH_WORKFLOW",
    "RECONCILER_SHIM_TEMPLATE",
    "REUSABLE_RECONCILER_WORKFLOW",
    "reconciler_shim_content",
]


# The member-side shim's committed path, and the central reusable workflow it
# calls. Both are the `uses:` JOIN between a member repo and this one, so each
# is a semver-stable identifier per `SPECIFICATION/contracts.md` section
# "Reusable workflows wire contract": renaming either breaks every member that
# has already been wired, silently, at trigger time rather than at install time.
MASTER_HEALTH_WORKFLOW = ".github/workflows/master-health-reconcile.yml"
REUSABLE_RECONCILER_WORKFLOW = ".github/workflows/reusable-master-health-reconcile.yml"

# The canonical shim body, as authored. `{owner}` is the member's own owner
# (resolved from its git remote by `wire-fleet-member`), never a hardcoded
# `thewoolleyman`, so a fork of the fleet reaches its own copy of the reusable
# workflow. The `@master` ref is the bootstrap-discipline ref the sibling
# pin-and-bump shims use; the bump-pin automation rewrites it to a tag on the
# next release.
_RECONCILER_SHIM_SOURCE = """\
# master-health-reconcile.yml — the red-master self-healing reconciler shim.
#
# Installed by wire-fleet-member per livespec-dev-tooling
# SPECIFICATION/contracts.md §"Reusable workflows wire contract"; the mechanism
# is plan/red-master-self-healing (epic livespec-dev-tooling-zcp5vb), child D.
#
# ⛔ NEVER EDITED BY HAND IN A MEMBER REPOSITORY. wire-fleet-member writes this
# body and the fleet conformance row `workflow-master-health-reconcile` convicts
# any repository whose copy differs from it by one byte.
#
# THREE TRIGGER FAMILIES, each covering what the others cannot:
#
#   - workflow_run on the CI workflow's COMPLETION is the EDGE that puts the
#     reconciler on a red branch within one CI cycle rather than within one
#     tick. It selects the workflow by its `name:` value, which is `CI` across
#     this fleet. A member that renames its CI workflow loses only the edge —
#     the schedule below still reaches every episode, one tick later.
#
#   - the pull_request family carries BOTH revert-side facts the decision
#     reads: the revert pull request's own CI verdict, which arrives with its
#     lifecycle events, and the fix-forward CLAIM, which is a LABEL on that
#     pull request and so arrives only as labeled / unlabeled. Dropping the
#     label events would leave a claimed fix-forward invisible, and the
#     reconciler would release a revert the claim was holding.
#
#   - the five-minute schedule is the MISSED-EVENT COVER and the deadline
#     clock. An event that never fired, a run that crashed mid-step, and the
#     hard cap on a red episode all need a tick that arrives whatever else
#     happened. Five minutes is GitHub's finest schedule granularity, so it is
#     both the floor and the requirement.
#
# workflow_dispatch is here for the scheduled end-to-end revert drill, which
# must be able to run the whole path against a throwaway branch on demand.

name: Master health reconcile

on:
  workflow_run:
    workflows: [CI]
    types: [completed]
  pull_request:
    types: [opened, reopened, synchronize, labeled, unlabeled, closed]
  schedule:
    - cron: '*/5 * * * *'
  workflow_dispatch: {{}}

jobs:
  reconcile:
    uses: {owner}/livespec-dev-tooling/{workflow}@master
    secrets: inherit
"""


# The template `_reconcile_shims` PUTs and `reconciler_shim_content` renders —
# ONE string, so the install path and the drift-detecting conformance row can
# never disagree about what the canonical bytes are. The `{workflow}` slot is
# resolved HERE rather than left to each caller: the reusable workflow's path is
# a property of this repository, not of the member being wired, and only
# `{owner}` is.
RECONCILER_SHIM_TEMPLATE = _RECONCILER_SHIM_SOURCE.replace(
    "{workflow}", REUSABLE_RECONCILER_WORKFLOW
)


def reconciler_shim_content(*, owner: str) -> str:
    """The canonical reconciler shim body rendered against `owner`."""
    return RECONCILER_SHIM_TEMPLATE.format(owner=owner)
