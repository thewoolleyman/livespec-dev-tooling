---
topic: the-arc-runner-version-pin
author: claude-opus-5-5 (ci-runtime-and-cost)
created_at: 2026-11-12T05:25:13Z
---

## Proposal: A runner version bump leaves every scale set serving jobs on the new version

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Appends one sentence to the paragraph "The runner version pin stays ahead of GitHub's cutoff." in non-functional-requirements.md section "Runner-pool node rebuild recipe". A runner version bump MUST reach the live pool through the committed converge. After it converges, every AutoscalingRunnerSet in the arc-runners namespace MUST have a listener and an EphemeralRunnerSet, and CI jobs of livespec-orchestrator-beads-fabro and livespec-dev-tooling MUST complete on k3s runners of the new version. Adds one scenario to scenarios.md. The paragraph has no H2 of its own, so the only new heading is the scenario's.

### Motivation

Revise v161 ratified this topic (decision modify, 2026-11-08) for work item livespec-dev-tooling-jkwzwv, the root fix for the 2026-11-05 ~08:05Z ARC incident. GitHub stopped serving the pinned runner version. arc-gha-rs-controller v0.14.2 marked every EphemeralRunnerSet outdated, deleted each listener and stopped about 24 busy workflow pods across all three nodes. At 08:28Z eight scale sets still had no listener and no EphemeralRunnerSet. v161 stated the bump pull request, the 14-day trigger and the same-version check. It did not state the outcome the bump exists to secure: after the bump, the pool is serving again. On 2026-11-12 the dispatcher refused jkwzwv at spec-change tier on this topic (verdict partial, hold reason awaiting-rejudgement, spec v199, orchestrator v0.320.0). The judgement found three of its four Definition-of-Done bullets stated. It found the fourth unstated: after the bump every AutoscalingRunnerSet has a listener and an EphemeralRunnerSet, and CI jobs complete on runners of the new version. It also found that "Live converge from the control node" covers only applying a merged change to the cluster. This proposal states that outcome, so the item grades against ratified text.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Runner-pool node rebuild recipe", append the following sentence to the end of the paragraph that begins "**The runner version pin stays ahead of GitHub's cutoff.**":

A runner version bump MUST reach the live pool through the committed converge, and once it has converged every AutoscalingRunnerSet in the `arc-runners` namespace MUST have a listener and an EphemeralRunnerSet, and CI jobs of `livespec-orchestrator-beads-fabro` and `livespec-dev-tooling` MUST complete on k3s runners of the new version.

In SPECIFICATION/scenarios.md, append the following scenario:

## Scenario: after a runner version bump converges, every scale set has a listener and serves jobs on the new version

Given the scale-set values files pin actions/runner 2.338.2

And the pull request that moves every values file to actions/runner 2.339.0 has merged

When the committed converge applies it to the live pool

Then every AutoscalingRunnerSet in the `arc-runners` namespace MUST have a listener and an EphemeralRunnerSet

And a CI job of `livespec-orchestrator-beads-fabro` and a CI job of `livespec-dev-tooling` MUST each complete on a k3s runner whose runner version is 2.339.0

The revise that accepts this proposal MUST add a tests/heading-coverage.json row for the new scenario heading, a spec-first TODO row whose reason names the e2e tier and whose work_item is livespec-dev-tooling-jkwzwv, and MUST register it in tests/heading-coverage-debt.json.
