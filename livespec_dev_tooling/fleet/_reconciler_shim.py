"""_reconciler_shim — how the master-health reconciler reaches a fleet repo.

Child D of plan `red-master-self-healing` (epic `livespec-dev-tooling-zcp5vb`,
work-item `livespec-dev-tooling-dw7dzd`). C1 shipped the reconciler's
DECISIONS as four pure `master_health_*` modules under
`livespec_dev_tooling/cross_repo/`; this module is the DISTRIBUTION half the
charter's design item 6 names — the canonical per-repo shim, the canonical
reusable workflow that shim calls, and the obligation row that fails a member
whose shim is missing or drifted. The shim lands in a fleet repository through
`wire-fleet-member` ONLY, never by hand (GitOps).

⛔ WHY THE REUSABLE WORKFLOW'S BODY LIVES HERE AS DATA RATHER THAN AT
`.github/workflows/reusable-master-health-reconcile.yml`. A factory branch
cannot create or update a file under `.github/workflows/` — the factory
dispatch credential carries no `workflows` grant (livespec
`.ai/ci-gate-discipline.md` §workflows boundary) — so the reusable workflow is
reported as a dropped unified diff for maintainer-side landing instead of
being committed by the run that authors it. Holding the canonical bytes HERE
is what keeps the property assertions on them gradeable in the meantime: a
test can read `reusable_reconciler_workflow()` even on a branch where the
workflow file itself is absent. Once the file lands, this constant is the
source those bytes were copied from; keep the two in lockstep.
"""

from __future__ import annotations

__all__: list[str] = [
    "RECONCILER_WORKFLOW",
    "REUSABLE_RECONCILER_WORKFLOW",
    "reconciler_shim_content",
]


# The shim's path inside each fleet member.
RECONCILER_WORKFLOW = ".github/workflows/master-health-reconcile.yml"
# The reusable workflow's path inside livespec-dev-tooling — the `uses:` target
# the shim names. This repository's `SPECIFICATION/contracts.md` records the
# reusable-workflow wire contract: the file name IS the semver-stable
# identifier a consumer references, so this path is an interface, not a detail.
REUSABLE_RECONCILER_WORKFLOW = ".github/workflows/reusable-master-health-reconcile.yml"

# The canonical shim body. Every rationale comment sits in the HEADER rather
# than interleaved inside the `on:` block, so each trigger's block holds only
# the trigger — a reader (and the parser the tests use) never has to tell a
# comment about one event from the declaration of the next.
#
# The `@master` ref is the bootstrap-discipline ref the sibling pin-and-bump
# shims use; the bump-pin automation rewrites it to a tag on the next release,
# which is why the drift comparison below normalises it away.
_RECONCILER_SHIM = """\
# master-health-reconcile.yml — red-master self-healing reconciler shim.
#
# Installed by wire-fleet-member per livespec
# SPECIFICATION/non-functional-requirements.md §"Fleet membership contract".
# Design: livespec-dev-tooling
# plan/red-master-self-healing/research/001-charter-red-master-self-healing.md.
#
# A THIN caller by design: every decision lives in the reusable workflow and
# the pure modules it drives, so a fleet-wide behaviour change ships as ONE
# release rather than as ten shim rewrites.
#
# THE TRIGGERS, AND WHY EACH IS LOAD-BEARING:
#
#   workflow_run — master CI completing is the episode's opening AND closing
#     edge: a failure opens it, a success is what ends it. The filter is on
#     `completed` rather than on a conclusion so ONE trigger serves the whole
#     lifecycle. It matches on the upstream workflow's `name:` (`CI`), not on
#     its file name.
#
#   pull_request — the revert and the fix-forward both reach the reconciler
#     here. There is deliberately NO `branches:` filter: a revert sits on
#     GitHub's generated `revert-<n>-<branch>` head, but a fix-forward rides
#     whatever head its author chose, so any filter narrow enough to name the
#     revert is blind to the claim that holds it. `labeled` is in the set
#     because the fix-forward claim is mechanical — a label on the revert pull
#     request — and a claim noticed only on the next tick loses the race
#     against the revert it exists to hold.
#
#   schedule — deadline enforcement and missed-event cover. GitHub drops
#     `workflow_run` and `pull_request` deliveries, and the hard cap is a
#     DEADLINE: it has to fire on a branch where nothing is happening, which
#     is precisely the state that generates no events at all. Five minutes is
#     the forge's own floor for `schedule:`, so this is as tight as the
#     cadence goes.

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
    uses: {owner}/livespec-dev-tooling/{reusable}@master
    secrets: inherit
"""


def reconciler_shim_content(*, owner: str) -> str:
    """Render the canonical reconciler shim body for `owner`.

    Templated on the OWNER alone, unlike the `release-dispatch.yml` shim: the
    reconciler reads the repository it runs in from the workflow context, so
    nothing in the body is member-specific and every fleet member receives
    byte-identical content.
    """
    return _RECONCILER_SHIM.format(owner=owner, reusable=REUSABLE_RECONCILER_WORKFLOW)
