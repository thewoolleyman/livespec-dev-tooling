---
topic: a-capacity-quota-or-lane
author: claude-opus-5-5
created_at: 2026-11-14T05:36:16Z
---

## Proposal: Every capacity, quota or lane change carries a dated derivation section with a CI-side read and a measured revert trigger

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Every change to the self-hosted pool's admission capacity, a Kueue queue's quota, or a gate lane's size must carry a dated section in the committed derivation record. That section must name two things. The first is a CI-side read taken about two hours after the apply, covering CI queue wait, CI job duration counted only on spans shorter than one day, and each affected node's CI-slice CPU pressure. The second is a measured revert trigger: a named metric, a window, and the committed values the change reverts to. The check aggregate must refuse a change that lacks either, naming the section and each missing element. The rule is a property and fixes no metric threshold.

### Motivation

This is guard G2 of the 2026-11-14 CI-stall retro (scope event on livespec-dev-tooling-r7iuj6), approved by the maintainer and assigned to plan gate-job-resources (epic livespec-dev-tooling-ukoeah). One of the stall's five contributing causes was the 2026-11-11 PowerEdge gate-lane growth from two to six gates. Nothing required a CI-side read after it, so the CPU it took from the node's BestEffort CI pods went unmeasured. A livespec-dev-tooling master coverage job later ran 102.5 min there instead of 27.0, ended red on starvation timeouts, and held the master-push concurrency group for 106 minutes. The changes made that night (livespec-dev-tooling#4628, the 1-slot queue floor, and #4635, the PowerEdge lane back to four gates) carry both elements by hand; this makes them a rule. The existing "Admission capacity sums to the cohort quota" paragraph already requires a capacity change to update its derivation record in the same change; this extends what that record must contain and covers quota and lane changes too. Fleet scope is every node and queue of the k3s pool. The implementation is livespec-dev-tooling-rl2dqp, filed alongside this proposal, as throughput-plans-coordinator asked, so it does not sit on an unfiled spec-tier hold. It aligns with the in-flight proposal per-node-cpu-budget-honest-requests (livespec-dev-tooling#4565): that change would itself need such a section.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Runner-pool node rebuild recipe", add one paragraph immediately after the **Admission capacity sums to the cohort quota.** paragraph:

```
**A capacity, quota or lane change carries its CI-side read and revert trigger.** A change to any pool node's declared admission capacity, to any Kueue ClusterQueue's nominal quota, lending or borrowing limit, or to any gate lane's quota MUST add or change a dated section in the committed derivation record (`ci-runner/k3s/phase2/kueue/DERIVATION.md`) in the same change. That section MUST name a CI-side read to be taken about two hours after the apply, covering CI queue wait, CI job duration counted only on spans shorter than one day, and the CPU pressure of the CI slice on each node the change affects. It MUST also name a measured revert trigger: the metric it watches, the window after the apply in which it is judged, and the committed values the change reverts to. The section MUST NOT need to fix a numeric threshold; the trigger MAY be stated relative to the metric's pre-apply value and noise band. The check aggregate MUST refuse a change that alters such a value without such a section, and a section that records such a change without both elements, naming the section heading and each missing element. A section dated before this paragraph's ratification is not refused. This paragraph is spec-first: as of its ratification no check enforces it, and work item livespec-dev-tooling-rl2dqp owns the change.
```

In SPECIFICATION/scenarios.md, add two scenarios at the end of the file:

```
## Scenario: a gate lane quota change without a CI-side read is refused naming the missing element

Given a change that raises a gate lane's cpu quota in `ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml`

And a new dated section in `ci-runner/k3s/phase2/kueue/DERIVATION.md` that records the change and names a measured revert trigger but no CI-side read

When the check aggregate runs on that change

Then it MUST fail

And it MUST name that section's heading and the missing CI-side read

## Scenario: a queue quota change whose derivation section carries both elements passes

Given a change that moves a Kueue ClusterQueue's nominal quota

And a new dated section in `ci-runner/k3s/phase2/kueue/DERIVATION.md` that names a CI-side read about two hours after the apply and a measured revert trigger with its metric, window and revert-to values

When the check aggregate runs on that change

Then this rule MUST NOT fail it
```

The revise that accepts this proposal adds both new scenario headings to `tests/heading-coverage.json` in the same commit.
