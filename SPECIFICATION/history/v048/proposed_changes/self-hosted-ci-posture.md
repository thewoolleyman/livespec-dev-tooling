---
topic: self-hosted-ci-posture
author: claude-opus-5
created_at: 2026-08-17T14:10:05Z
---

## Proposal: Self-hosted CI routing posture via CI_RUNNER_LABELS with a manual hosted revert

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/contracts.md

### Summary

Replace the stale hosted-only-posture paragraph in constraints.md §"CI matrix shape" with the routing posture this repository actually adopts: gating CI routes to self-hosted capacity through the CI_RUNNER_LABELS repository variable, read directly at each gating job's runs-on, with an inline literal fallback naming GitHub-hosted capacity and a MANUAL operator-driven revert. Also retire the same stale premise where it survives in contracts.md §"codex-acp factory gate". The reusable check workflows shipped to consumers stay hosted, and the matrix and required-check semantics are unchanged.

### Motivation

The existing paragraph asserts a fleet-wide 'hosted-only posture' that no longer holds: seven sibling fleet repositories already route gating CI to self-hosted k3s capacity via the CI_RUNNER_LABELS repository variable, and this repository is the last one still on hosted-only. Ratifying the corrected posture is a precondition for routing this repository's gating CI the same way.

The replacement text deliberately describes MANUAL revert rather than automatic failover. This repository previously carried a health-probe-based automatic failover design (reusable-ci-runner-router.yml plus the ci-runner-health composite Action) that selected self-hosted capacity only after two healthy observations. That design is architecturally incompatible with the ARC (Actions Runner Controller) scale sets the fleet now runs, for two independent reasons, both verified live on 2026-08-17 against livespec-driver-claude (a repository already cut over to k3s):

1. ARC gha-runner-scale-set runners register with an EMPTY label array. A sample of 14 registered scale-set runners showed 13 offline and 1 online, every one of them reporting zero labels. The probe decides health by requiring the configured label set to be a subset of a runner's labels, so a non-empty required set can never match. In ARC scale-set mode the scale set NAME is the routing token, not a label set.

2. The scale sets run min-runners: 0. An idle scale set therefore has zero registered runners by design, so a pre-flight probe observes an apparent outage during normal operation. Raising min-runners above zero to satisfy the probe would permanently pin node capacity, against the fleet's existing ClusterQueue oversubscription pressure.

Specifying automatic failover would therefore commit the spec to a guarantee the mechanism cannot honor. The honest, achievable property is the one the seven sibling repositories already rely on: an inline hosted fallback plus a manual variable flip.

The second edit, to contracts.md, was surfaced by the independent pre-ratification review: the phrase this proposal exists to retire survives one file over, where it is cited as the operative current premise for the codex-acp receiver's disablement. Left unamended it would contradict the ratified constraint immediately. The receiver's disablement is administrative and independent of the fleet's runner posture, so the causal attribution is simply dropped; the rule itself is unchanged.

### Proposed Changes

### Edit 1 — `SPECIFICATION/constraints.md`, section `## CI matrix shape`

Replace this paragraph verbatim:

```
Under the fleet's current hosted-only posture, this repository's merge-gating CI and the reusable check workflows execute on GitHub-hosted runners and MUST NOT require the shared factory host's self-hosted labels. The matrix and required-check semantics are unchanged; only the execution capacity moves off the factory host.
```

with:

```
This repository's merge-gating CI routes to self-hosted capacity through the `CI_RUNNER_LABELS` repository variable, read directly at each gating job's `runs-on` with an inline literal fallback naming GitHub-hosted capacity. This is the fleet's standard self-hosted routing pattern. Setting the variable to a self-hosted target routes there; restoring it to the hosted literal, or deleting it so the inline fallback applies, returns the gate to GitHub-hosted capacity. That revert is MANUAL and operator-driven: no health probe or automatic runtime failover stands between the variable and the routing decision, so the variable's setting together with the inline fallback is the entire routing contract. The inline fallback MUST name hosted capacity and never self-hosted, so that a deleted or emptied variable leaves the merge gate on capacity that is always present. The reusable check workflows this library ships to consumers remain on GitHub-hosted runners and MUST NOT require the shared factory host's self-hosted labels. The matrix and required-check semantics are unchanged; only the execution capacity changes.
```

### Edit 2 — `SPECIFICATION/contracts.md`, section `## codex-acp factory gate`

Replace this sentence fragment verbatim:

```
While the privileged host-only golden-master receiver workflow is administratively disabled under the fleet's hosted-only CI posture, the freshness scan MAY still open or find a codex-acp bump PR and MAY emit its `repository_dispatch` event.
```

with:

```
While the privileged host-only golden-master receiver workflow remains administratively disabled, the freshness scan MAY still open or find a codex-acp bump PR and MAY emit its `repository_dispatch` event.
```

The rest of that paragraph is unchanged. The receiver's disablement is administrative and independent of which runner capacity the fleet's gating CI uses, so removing the causal attribution retires the stale premise without altering the rule.

No `## ` heading is added, changed, or removed by either edit, so no `tests/heading-coverage.json` co-edit is owed.
