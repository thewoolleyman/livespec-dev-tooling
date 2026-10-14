"""_reusable_reconciler — the canonical reusable master-health workflow body.

Child D of plan `red-master-self-healing` (epic `livespec-dev-tooling-zcp5vb`,
work-item `livespec-dev-tooling-dw7dzd`). The sibling `_reconciler_shim` holds
the THIN per-repo caller that `wire-fleet-member` installs; this module holds
the bytes that caller's `uses:` resolves to.

⛔ WHY THE BYTES LIVE HERE RATHER THAN AT
`.github/workflows/reusable-master-health-reconcile.yml`. A factory branch
cannot create or update any file under `.github/workflows/`: the factory
dispatch credential carries no `workflows` grant (livespec
`.ai/ci-gate-discipline.md`, the workflows-boundary rule). So the run that
authors this workflow reports it as a dropped unified diff for maintainer-side
landing instead of committing it. Holding the canonical bytes in the package
is what keeps their two gradeable properties — hosted capacity and the fleet
App token — assertable on a branch where the workflow file itself is absent.

ONCE THE FILE LANDS, THESE BYTES ARE THE SOURCE IT WAS COPIED FROM. There is
deliberately no byte-identity check between the two yet: such a check can only
be armed after the file exists, and arming a check ahead of the adoption it
judges is the failure this repository already paid for in `46c5dab`. Landing
the file is what makes that check safe to add, and it is the natural companion
to the landing.
"""

from __future__ import annotations

__all__: list[str] = [
    "reusable_reconciler_workflow",
]


# The canonical reusable workflow. No templating: nothing in the body is
# owner- or member-specific, because the reconciler reads the repository it
# acts on from the workflow context. That is also why the body can carry
# `${{ … }}` expressions verbatim rather than through `str.format`'s doubled
# braces, which is the shape the sibling shim bodies have to pay for.
_REUSABLE_RECONCILER = """\
# reusable-master-health-reconcile.yml — the red-master self-healing reconciler.
#
# Authority: livespec-dev-tooling
#   plan/red-master-self-healing/research/001-charter-red-master-self-healing.md
#   (epic livespec-dev-tooling-zcp5vb), design items 2 "A deterministic
#   MASTER-HEALTH RECONCILER", 3 "Triggers" and 6 "Distribution". Called by
#   each fleet member's `master-health-reconcile.yml` shim, which
#   wire-fleet-member installs and the `workflow-master-health-reconcile`
#   fleet-conformance obligation row holds to the canonical bytes.
#
# ⛔ GITHUB-HOSTED RUNNERS, NOT THE FLEET'S OWN k3s POOL. This is a
# CORRECTNESS requirement, not a cost preference. The reconciler's whole job is
# to heal a red master, and "the k3s runner pool is down" is one of the
# failures that reddens one. A healer queued against the broken pool cannot run
# at the exact moment it is most needed, and the episode then sits red with its
# own remedy stuck in the queue behind the outage that caused it.
#
# The runner-label token this rules out is therefore absent from this file
# ENTIRELY, prose included, so the guard over it can be a plain whole-source
# check rather than one that has to tell a label from a sentence about labels.
#
# ⛔ THE FLEET APP TOKEN, NOT `GITHUB_TOKEN`. A pull request created with the
# default `GITHUB_TOKEN` does not trigger workflow runs. The reconciler
# RELEASES a revert on the evidence of the revert's OWN CI being green, so
# under `GITHUB_TOKEN` that CI never starts, the evidence never arrives, and
# the self-healing path stalls on every episode — silently, because a revert
# waiting on a run that will never exist is indistinguishable from a revert
# waiting on a slow one.
#
# The `permissions:` block below governs `github.token`, which this workflow
# uses for READS only. Every write the reconciler performs — opening the
# revert, arming its auto-merge, re-running failed jobs, raising the
# needs-attention issue — rides the minted App token instead, so the two are
# deliberately asymmetric rather than accidentally so.
#
# ⛔ DO NOT LAND THIS FILE BEFORE ITS RECONCILE RUNNER EXISTS. The step below
# invokes a transport module that C1 did not ship and that this child does not
# ship either: C1 is the DECISION layer (the four pure `master_health_*`
# modules, whose no-network guarantee is enforced by an AST walk over that very
# name prefix), and this child is DISTRIBUTION. The forge-reading,
# forge-writing module between them is an unfiled gap in the plan's child list
# and is reported as such. Landing this workflow first would put a five-minute
# schedule in every fleet repository against a module that does not resolve.

name: reusable-master-health-reconcile

on:
  workflow_call:
    secrets:
      APP_ID:
        description: >-
          Fleet GitHub App client id, passed through from the caller's shim by
          `secrets: inherit`.
        required: true
      APP_PRIVATE_KEY:
        description: >-
          Fleet GitHub App private key, passed through from the caller's shim
          by `secrets: inherit`.
        required: true

# Reads only; see the asymmetry note in the header.
permissions:
  actions: read
  contents: read

# One reconcile at a time per repository. `cancel-in-progress: false` is
# deliberate: a run cancelled mid-step can leave a half-made revert behind,
# and the episode is long-lived relative to the cadence, so queueing the next
# tick costs nothing a cancellation would save.
concurrency:
  group: master-health-reconcile-${{ github.repository }}
  cancel-in-progress: false

jobs:
  reconcile:
    name: master-health-reconcile
    runs-on: ubuntu-latest
    steps:
      - name: Mint the fleet GitHub App token
        id: app-token
        uses: actions/create-github-app-token@v3
        with:
          client-id: ${{ secrets.APP_ID }}
          private-key: ${{ secrets.APP_PRIVATE_KEY }}

      - name: Checkout the caller repo
        uses: actions/checkout@v5

      - name: Checkout livespec-dev-tooling support modules
        uses: actions/checkout@v5
        with:
          repository: thewoolleyman/livespec-dev-tooling
          path: .livespec-dev-tooling
          fetch-depth: 1

      - name: Reconcile this repository's master health
        env:
          # The MINTED token, not `github.token` — see the header. Minting the
          # App token and then leaving this step on `github.token` is the live
          # failure mode: the workflow reads as authenticated and behaves as
          # though it is not.
          GH_TOKEN: ${{ steps.app-token.outputs.token }}
          TARGET_BRANCH: ${{ github.event.repository.default_branch }}
        run: |
          set -uo pipefail
          export PYTHONPATH=.livespec-dev-tooling
          # Reads the forge, hands the recorded state to the pure decision
          # modules, and performs the AT MOST ONE step they return. Exit codes
          # follow the sibling release-lane runners: 0 healthy, 1 a step was
          # taken or an episode needs attention, 2 the forge could not be read
          # or the write did not land. A watcher that cannot measure must never
          # read as one reporting healthy.
          python3 -m livespec_dev_tooling.cross_repo.red_master_reconcile_runner
"""


def reusable_reconciler_workflow() -> str:
    """The canonical body of `reusable-master-health-reconcile.yml`."""
    return _REUSABLE_RECONCILER
