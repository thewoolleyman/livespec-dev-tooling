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

A capacity change in the self-hosted pool must carry a dated section in the committed derivation record. The term covers a node's admission capacity, a Kueue queue's quota or lending or borrowing limit, a gate lane's quota, a scale set's runner ceiling, or the per-node CPU budget, each defined by path and key. The section must carry three things:
- a plan for a CI-side read about two hours after the apply, naming who takes it;
- a measured revert trigger;
- later, the read's result, recorded within 24 hours.

The check aggregate refuses a change that lacks any of them, naming the section and each missing element. It exempts only sections that already existed when this rule was ratified. The rule is a property and fixes no metric threshold.

### Motivation

This is guard G2 of the 2026-11-14 CI-stall retro (scope event on livespec-dev-tooling-r7iuj6), approved by the maintainer and assigned to plan gate-job-resources (epic livespec-dev-tooling-ukoeah). Two of that night's contributing causes were capacity changes with no CI-side read:
- the PowerEdge gate lane grew from two to six gates on 2026-11-11 (99231b3e, 84e3c346, `gates-poweredge-flavor` nominalQuota);
- the per-node CPU budget cut moved ADMISSION_CAPACITY_C, a ClusterQueue quota, and one scale set's maxRunners from 16 to 14 (0787ea64).

The CPU the gate lane took from the PowerEdge's BestEffort CI pods went unmeasured. A livespec-dev-tooling master coverage job later ran 102.5 min there instead of 27.0, ended red on starvation timeouts, and held the master-push concurrency group for 106 minutes.

The changes made that night carry the plan and the trigger by hand: livespec-dev-tooling#4628, the 1-slot queue floor, and #4635, the PowerEdge lane back to four gates. This makes them a rule a check can decide.

The existing "Admission capacity sums to the cohort quota" paragraph already requires a capacity change to update its derivation record in the same change. This paragraph defines what counts as a capacity change and what the record must contain.

Fleet scope is every node, queue and scale set of the k3s pool. The implementation is livespec-dev-tooling-rl2dqp, filed alongside this proposal so that it does not sit on an unfiled spec-tier hold. The proposal aligns with the in-flight per-node-cpu-budget-honest-requests (livespec-dev-tooling#4565): that change would itself need such a section.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Runner-pool node rebuild recipe", add one paragraph immediately after the **Admission capacity sums to the cohort quota.** paragraph:

```
**A capacity change carries its CI-side read and revert trigger.** A *capacity change* is a change to the value of any of these keys; a change to comments or whitespace alone is not one:
- `ADMISSION_CAPACITY_C` in `ci-runner/k3s/phase0-bare-metal/profiles/*.env`;
- `nominalQuota`, `lendingLimit` or `borrowingLimit` in any `ci-runner/k3s/phase2/kueue/**/cluster-queue-*.yaml`, which includes the worker queues, the gates and repro-gates lanes, and the fabro queue;
- `maxRunners` in any `ci-runner/k3s/phase2/arc/**/values-*.yaml`;
- any value in `ci-runner/k3s/phase2/node-cpu-budget.yaml`.

A capacity change MUST add or change, in the same change, a dated section of the committed derivation record (`ci-runner/k3s/phase2/kueue/DERIVATION.md`). A dated section is a heading of level two or three whose text ends in the date in parentheses as `(YYYY-MM-DD)`. That section MUST carry two things at the time of the change:
- a plan for a CI-side read about two hours after the apply, naming its owner and covering CI queue wait, CI job duration counted only on spans shorter than one day, and the CPU pressure of the CI slice on each node the change affects;
- a measured revert trigger: the metric it watches, the window after the apply in which it is judged, and the committed values the change reverts to.

The trigger MAY be stated relative to the metric's pre-apply value and noise band. Neither element needs a numeric threshold.

The read's result MUST be recorded in that section within 24 hours of the commit that added the section. Once 24 hours have passed with no recorded result, the check aggregate MUST refuse every change, naming the section and its owner, until the result is recorded.

The check aggregate MUST refuse a capacity change with no such section, and a dated section recording a capacity change that lacks the plan, its owner or the trigger. Each refusal MUST name the section heading and each missing element.

The exemption is keyed on content, not on the date a heading claims. A section that exists byte-identical in the derivation record at the revise commit that ratifies this paragraph is exempt. Any section added or changed in a later diff is always judged.

This paragraph is spec-first: as of its ratification no check enforces it, and work item livespec-dev-tooling-rl2dqp owns the change.
```

In SPECIFICATION/scenarios.md, add three scenarios at the end of the file:

```
## Scenario: a gate lane quota change without a CI-side read plan is refused naming the missing element

Given a change that raises `nominalQuota` of a gate lane in `ci-runner/k3s/phase2/kueue/cluster-queue-gates.yaml`

And a new dated section in `ci-runner/k3s/phase2/kueue/DERIVATION.md` that records the change and names a measured revert trigger but no CI-side read plan

When the check aggregate runs on that change

Then it MUST fail

And it MUST name that section's heading and the missing CI-side read plan

## Scenario: a scale set ceiling change whose derivation section carries the plan, its owner and the trigger passes

Given a change that moves `maxRunners` in a `ci-runner/k3s/phase2/arc/values-*.yaml`

And a new dated section in `ci-runner/k3s/phase2/kueue/DERIVATION.md` that names a CI-side read plan with its owner and a measured revert trigger with its metric, window and revert-to values

When the check aggregate runs on that change

Then this rule MUST NOT fail it

## Scenario: a derivation section whose CI-side read result is missing after 24 hours refuses the next change

Given a dated section in `ci-runner/k3s/phase2/kueue/DERIVATION.md`, added by a commit more than 24 hours ago, that records a capacity change and names its read plan, owner and trigger but no recorded result

When the check aggregate runs on any later change

Then it MUST fail

And it MUST name that section's heading and its owner
```

The revise that accepts this proposal adds all three scenario headings to `tests/heading-coverage.json` in the same commit. Each row is `"test": "TODO"`, with a `reason` naming the tier the owed test runs at and `"work_item": "livespec-dev-tooling-rl2dqp"`. The same commit stages the regenerated `tests/heading-coverage-debt.json` (`just generate-heading-coverage-debt-register`).
