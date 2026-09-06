---
topic: scale-set-ceiling-bounded-to-fair-share
author: claude-fable-5-1
created_at: 2026-09-06T08:11:05Z
---

## Proposal: A repository's runner-pool ceiling is bounded to a small multiple of its fair share, so a backlog waits at the forge instead of becoming control-plane objects

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Amend the admission-formula clause of §"Adaptive JIT runner admission budget" so the per-repository ceiling term is no longer the doubled matrix width but a ceiling bounded to a small multiple of the repository's fair share of host capacity, stated as the property that queued work beyond a bounded multiple of the admission cap MUST wait at the forge rather than be materialized as pending objects the host's control plane must keep reconciling. The min() formula, fair borrowing, and the physical-cap sentence are kept; the scenario "JIT fleet capacity borrows fairly without exceeding 482 runners" gets the matching Given step. No `## ` heading is added, changed, or removed, so no tests/heading-coverage.json co-edit arises.

### Motivation

The k3s runner pool realizes this clause's `doubled repository logical ceiling` as each ARC scale set's `maxRunners` (ci-runner/k3s/phase2/kueue/DERIVATION.md). On 2026-09-06, with the churn-slot cap C at 32 and the ten ceilings summing to 574, the first fleet-wide backlog on the two-NVMe host (07:38Z–07:50Z) materialized as 119 pending Kueue workloads and 122 gated runner objects while 25–30 jobs ran; every gated object is an EphemeralRunner, a pod, a Workload and events rewritten every reconcile through kine's single writer, and kine logged 11 Slow SQL in ten minutes — more than the 64-slot burst two hours earlier, because the write volume scales with the backlog's depth, not the admitted count. A ceiling read as the doubled matrix width therefore converts every backlog into control-plane load that the admission cap cannot bound; queued work left at the forge costs the host nothing and runs no later, because only the cap's worth can run in either case. The maintainer directed the bound in session (livespec plan poweredge-raid-array-maintenance, epic livespec-g52yrb; capacity owner epic livespec-ifwnqj); the pool applies `maxRunners_i = max(2 x nominalQuota_i, 6)` (sum 76 against 574) and the arithmetic lives in DERIVATION.md "Bounding maxRunners to the quota (2026-09-06)". The clause text still mandates the doubling, so the live pool would read as non-conforming until it is amended.

### Proposed Changes

**Change 1 — SPECIFICATION/non-functional-requirements.md, §"Adaptive JIT runner admission budget".** Replace the sentence:

> Each repository's logical ceiling MUST be doubled to support two concurrent matrix pipelines.

with:

> Each repository's logical ceiling MUST be BOUNDED to a small multiple of that repository's fair share of host-wide capacity — large enough that a repository can borrow unused capacity beyond its guaranteed share, and never so large that a backlog is materialized as pending admission objects the host's control plane must keep reconciling: queued work beyond a bounded multiple of the admission cap MUST wait at the forge, where it costs the host nothing, rather than exist as pending objects on the host. The multiple, and any floor that keeps a small-share repository from draining a lone matrix one job at a time, are pool facts recorded with the pool's admission derivation, never here. Maintainer-directed 2026-09-06.

The following sentence ("The physical host-wide cap remains exactly 482 active runners; no configuration or recovery path may derive or admit 964 runners.") and the `min(queued jobs, doubled repository logical ceiling, fair share of remaining host-wide capacity)` formula sentence are kept verbatim; the formula's `doubled repository logical ceiling` term is read through the amended definition above (the term name is retained so the derivation record's mapping table stays valid).

**Change 2 — SPECIFICATION/scenarios.md, `## Scenario: JIT fleet capacity borrows fairly without exceeding 482 runners`.** Replace the Given step:

> Given repositories have doubled logical ceilings for two matrix pipelines

with:

> Given each repository's logical ceiling is bounded to a small multiple of its fair share, so queued work beyond that bound waits at the forge

Every other step of the scenario is unchanged, and the scenario heading is unchanged.
