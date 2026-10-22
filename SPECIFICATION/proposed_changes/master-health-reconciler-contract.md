---
topic: master-health-reconciler-contract
author: claude:delegated-gate-fleet-rollout
created_at: 2026-10-22T14:07:22Z
---

## Proposal: Govern the master-health reconciler in this repository's contracts

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a `## Master-health reconciler` H2 to contracts.md stating the reconciler's decision contract: red-master detection, flake and infrastructure classification, culprit selection, the held revert, the obstruction refusal, the progress-bounded fix-forward claim and its claimant set, the hard cap, fail-closed configuration, the watch-the-watcher and drill signals, and the fleet conformance row for its shim. Add one `## Scenario:` per decision to scenarios.md. livespec-dev-tooling ships this module (livespec_dev_tooling/cross_repo/master_health_*.py), but today no heading in its own governed tree states what it must do.

### Motivation

The master-health reconciler's behaviour was ratified in livespec core v224 (non-functional-requirements.md, the H3 `### CI as a merge gate (branch protection)`). Its realization lives here: the reconciler module and its reusable workflow ship from livespec-dev-tooling. Yet nothing in this repository's SPECIFICATION/ states its decisions. Its module docstring and every child of plan red-master-self-healing (epic livespec-dev-tooling-zcp5vb) reference `Cross-repo coordination automation surface`, which governs the pin-and-bump workflows and says nothing about a red master. On 2026-10-22 the R316 launch-time Definition-of-Done preflight refused livespec-dev-tooling-joqff6 on two independent judges (claude and codex): that reference resolves but governs none of its seven assertions. Its pending siblings (bznobs, yilv6p, 4xrhck, reslr6) carry the same latent defect. They could not be dispatched with a governing reference until the contract exists in this tree. Per the authoring discipline, split (iii), the realization belongs in this repository's spec, while the repo-agnostic policy stays in core.

### Proposed Changes

Add the following H2 to SPECIFICATION/contracts.md immediately before `## Semver discipline`:

## Master-health reconciler

This library ships the fleet's master-health reconciler, the deterministic module that realizes livespec core's ratified red-master policy (livespec `SPECIFICATION/non-functional-requirements.md` §"CI as a merge gate (branch protection)", v224). Core owns the policy; this section is the realization contract that this library's reconciler module, its reusable workflow and its conformance row MUST satisfy.

**Statelessness and determinism.** Each reconcile run MUST read current truth from the forge — the per-commit `master` CI status, the open revert pull request, any fix-forward claim, and the fix pull request's state and CI — together with the repository's committed reconciler configuration. It MUST take AT MOST ONE next step. No decision MAY depend on an LLM call.

**Red master.** `master` is red when the repository's single all-green gate job reports failure on the newest `master` commit with a completed verdict. A failure of a workflow the gate job does not gate MUST NOT start an episode or select a culprit.

**Classification.** On a red `master` the reconciler MUST re-run the failed jobs once. It MUST classify the failure as flake or infrastructure when the re-run passes, when the same failure appears on unrelated commits, or when the failure text names an outage listed in committed configuration. A flake or infrastructure failure MUST NOT produce a merged revert; the reconciler MUST raise a needs-attention signal instead.

**Culprit and revert.** For a genuine regression, the culprit MUST be the earliest red `master` commit whose parent was green. A culprit that cannot be proven, that has no pull request, or that is a release-please release commit MUST raise needs-attention instead of a revert. The reconciler MUST open the revert pull request with auto-merge HELD. The revert commit MUST be created by the forge through `createCommitOnBranch` under the fleet GitHub App installation identity, restoring the culprit's parent bytes at every path the culprit changed and carrying `This reverts commit <culprit sha>.` on its own line. When any `master` commit after the culprit changed a path the culprit changed, the reconciler MUST NOT create the revert and MUST raise needs-attention naming the obstructing commit. The reconciler MUST NOT revert a revert it created, and MUST revert a given culprit at most once per episode. Once a later non-revert `master` commit is green, a held revert MUST be closed as superseded, not released.

**Release without a claim.** With no valid fix-forward claim in force, the reconciler MUST release the revert for merge as soon as its own CI is green. A revert whose own CI is not green MUST NOT be merged; the reconciler MUST raise needs-attention.

**Fix-forward claim.** A claim is a comment on the reconciler's revert pull request naming one fix pull request. A claim is valid only when posted by the maintainer's forge login, or by the identity that opened the culprit pull request with a `Claimed-By:` line naming the owning session; the reconciler MUST ignore every other claim and proceed as though unclaimed. A valid claim MUST hold the revert while the fix makes a forward transition within the stall duration of its current step. The forward transitions are, in order: the fix pull request is opened or receives a new commit; fix CI starts; fix CI goes green or reports fewer failing checks; auto-merge is armed; the fix merges; `master` CI on the fix starts; `master` CI goes green. Any forward transition restarts the step clock. The reconciler MUST release the held revert when the fix thrashes: the same check fails repeatedly, a new commit does not reduce the failing set, a new check starts failing, the fix merged while `master` stays red, more than one fix pull request is claimed, or no forward transition occurs within the current step's stall duration.

**Hard cap.** Once `master` has been red for the hard cap, the reconciler MUST release the revert regardless of fix-forward progress, but only when the revert's own CI is green. When it is not green at the cap, the reconciler MUST NOT merge it and MUST raise needs-attention.

**Committed configuration, failing closed.** The hard cap (fleet default 120 minutes), each step's stall duration (the measured p90 of that step × 1.5, rounded up to the next five minutes), the outage strings and the gating workflow MUST be read from the repository's committed configuration, never set by hand at run time. A missing or malformed hard cap or stall duration MUST fail closed to revert-by-default: the reconciler MUST treat every claim as not holding, and MUST still merge only a revert whose own CI is green.

**Needs-attention signal.** Every needs-attention signal MUST be one idempotent forge issue per red episode carrying a fixed label, so that it is reachable from a hosted runner without ledger access. A `master` red longer than the configured threshold with no revert pull request in flight MUST itself raise needs-attention. A scheduled drill MUST prove the revert path end to end on a throwaway branch by reverting a change that touches product implementation code; a failed drill, including a drill revert the Red-Green-Replay range gate convicts, MUST raise needs-attention.

**Distribution and conformance.** The reconciler MUST run from a thin per-repository workflow shim on GitHub-hosted runners, triggered on completion of `master` CI, on events of the pull requests it manages, and on a schedule of at most five minutes. The shim MUST be installed and reconciled by `wire-fleet-member`. The fleet conformance row `workflow-master-health-reconcile` MUST fail a fleet member whose shim is missing or drifted from the canonical shim.

Add the following scenarios to SPECIFICATION/scenarios.md, each a `## Scenario:` H2 with Given/When/Then lines in the file's existing style:

## Scenario: a red master whose re-run passes is classified a flake and never merges a revert
Given `master`'s gate job reports a completed failure on the newest commit
When the reconcile run re-runs the failed jobs once and the re-run passes
Then the run classifies the episode as a flake, MUST NOT merge any revert, and raises one needs-attention issue for the episode

## Scenario: a genuine regression opens a held revert of the earliest red commit with a green parent
Given a red `master` classified as a genuine regression, whose earliest red commit has a green parent and a pull request
When the reconcile run takes its next step
Then it opens a revert pull request with auto-merge held, whose forge-created commit restores the culprit's parent bytes and carries `This reverts commit <culprit sha>.`

## Scenario: a later master commit touching a culprit path blocks the revert
Given a genuine regression whose culprit changed a path that a later `master` commit also changed
When the reconcile run takes its next step
Then it MUST NOT create the revert and raises needs-attention naming the obstructing commit

## Scenario: an unclaimed revert is released as soon as its own CI is green
Given a held revert pull request with no valid fix-forward claim
When the revert's own CI reports green
Then the reconcile run releases the revert for merge

## Scenario: a valid fix-forward claim holds the revert while the fix makes progress
Given a held revert carrying a valid fix-forward claim naming one fix pull request
When the fix makes a forward transition within the stall duration of its current step
Then the reconcile run keeps the revert held

## Scenario: a thrashing fix-forward releases the held revert
Given a held revert carrying a valid fix-forward claim
When the fix repeats red on the same check, adds a commit that does not reduce its failing checks, fails a new check, or merges while `master` stays red
Then the reconcile run releases the revert

## Scenario: a stalled or contested fix-forward releases the held revert
Given a held revert carrying a valid fix-forward claim
When no forward transition occurs within the current step's stall duration, or a second fix pull request is claimed
Then the reconcile run releases the revert

## Scenario: at the hard cap a revert with green CI lands regardless of fix-forward progress
Given `master` has been red longer than the configured hard cap and the revert's own CI is green
When the reconcile run takes its next step
Then it releases the revert even while a valid claim's fix is still making progress

## Scenario: at the hard cap a revert whose CI is not green is not merged
Given `master` has been red longer than the configured hard cap and the revert's own CI is not green
When the reconcile run takes its next step
Then it MUST NOT merge the revert and raises needs-attention

## Scenario: a fix-forward claim from outside the claimant set is ignored
Given a held revert whose only claim comes from an identity that is neither the maintainer's forge login nor the culprit pull request's opener with a `Claimed-By:` line
When the reconcile run takes its next step
Then it ignores the claim and treats the revert as unclaimed

## Scenario: missing or malformed reconciler configuration fails closed to revert-by-default
Given the committed hard cap or a step's stall duration is absent or malformed
When the reconcile run evaluates a held revert carrying a valid claim
Then it does not hold the revert for the claim, and releases it only once its own CI is green

## Scenario: a master red past the threshold with no revert in flight raises needs-attention
Given `master` has been red longer than the configured threshold
And no revert pull request is in flight
When the reconcile run takes its next step
Then it raises needs-attention for the episode

## Scenario: a failed revert-path drill raises needs-attention
Given the scheduled drill reverts a product-implementation change on a throwaway branch
When the drill's revert is not merged green, including when the range gate convicts it
Then the drill raises needs-attention

## Scenario: a fleet member whose master-health shim is missing or drifted fails conformance
Given a fleet member whose master-health reconcile shim is absent or differs from the canonical shim
When fleet conformance evaluates the `workflow-master-health-reconcile` row
Then the row reports an error-severity finding for that member

The revise that accepts this proposal MUST co-edit `tests/heading-coverage.json` in the same change, adding one entry for `## Master-health reconciler` and one for each new `## Scenario:` heading. An entry MAY carry `test: "TODO"` with a non-empty reason naming the work item that owes it (joqff6, bznobs, yilv6p, 4xrhck or reslr6); where an already-merged test exercises the heading, the entry SHOULD name that test.
