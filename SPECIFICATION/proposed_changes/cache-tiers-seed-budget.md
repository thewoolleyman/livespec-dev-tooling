---
topic: cache-tiers-seed-budget
author: claude-fable-5-1 (plan ci-runner-pod-lifecycle-reliability session, livespec-1qpt)
created_at: 2026-09-06T17:13:03Z
---

## Proposal: Re-base the Tiers clause's start-burst premise onto the checked per-start seed budget (livespec-1qpt, Carrier F4c)

### Target specification files

- non-functional-requirements.md

### Summary

One sentence of the **Tiers.** paragraph in §"Runner-pool build cache tiers" changes; nothing else in the file and no `## ` heading changes. The sentence that grounds the host-served preference in a hardware figure ("about six simultaneous job starts saturate the array") is replaced by the media-independent rule the pool now enforces: every byte and file a seed adds to a job start is overhead on any medium, so a host-served realization MUST be preferred over a seeded tree wherever the package manager can consume one, and a seeded tree MUST NOT ship unbounded — its per-start cost MUST be capped by one byte budget and one file budget stated in exactly one committed place that both the populator and the node's lifecycle sweep read; the populator MUST refuse to publish a generation over either budget, leaving the previous generation live; and the sweep MUST report, as lifecycle findings with gauges, a live generation over budget and a seed whose measured bytes or duration exceed their budgets. A per-start byte copy of a cache MUST NOT ship in any tier. The six-starts figure is demoted to measurement history: the clause records that it was a 2026-09-02 measurement of the previous three-drive array and that the rebuilt array showed no start-burst knee at 32 concurrent jobs and 18 starts per minute, and that the figure lives in the plan record, not as a premise of the clause. The text names the PROPERTY (one budget place, populator refusal, sweep report) and not the shipped file or ConfigMap names, because the specification constrains architecture, not mechanism.

### Motivation

**Why the premise is a drift.** The Tiers clause ratified "about six simultaneous job starts saturate the array" as the reason for the host-served preference. That reading came from the 2026-09-02 fan-out on the CI host's previous three-drive array (sysstat: 84–119 MB/s written at 64–98% util, await 35–160 ms). The 2026-09-04 measurement on the rebuilt seven-drive array — livespec plan `ci-runner-pod-lifecycle-reliability`, `plan/ci-runner-pod-lifecycle-reliability/research/005-start-burst-measurement-and-mitigation.md` §4 — shows twice the write rate at a fifth of the latency, %util under 10, and no knee at 24–32 concurrent jobs and 18 starts per minute. A ratified premise the live host contradicts is a drift. The rule survives for a media-independent reason: per-start bytes and file creates are pure overhead, so the limit MUST be a stated budget enforced by shipped checks, not a hardware figure.

**The shipped mechanism the new text names** (both on livespec-dev-tooling master, both closed with live evidence on 2026-09-06): (a) the populator's budget refusal — the `warm-cache-budget` ConfigMap (`bytes`, `files`) under `ci-runner/k3s/phase2/warm-cache/` is read by `warm-cache-populate.sh`, which refuses to publish over either budget with exit 3 and leaves the previous generation live (livespec work-item `livespec-41w4`, Carrier F2); (b) the node lifecycle sweep's classes `warm-cache-oversize` (live generation bytes/files over the same ConfigMap's budget, or stale) and `start-seed-cost` (the newest seeded work volume's measured seed bytes and seconds over their budgets), emitted as `livespec.ci_lifecycle.*` gauges beside `livespec.ci_warm.live_generation_*` and `livespec.ci_seed.*` (`ci-runner/k3s/phase2/runner-pod-lifecycle/scan-runner-pod-lifecycle.sh`; livespec work-item `livespec-44qx`, Carrier F4b). Live proof 2026-09-06: generation 423 MB / 11,513 files against budget 1 GB / 20,000; seed 423 MB in 2 s; patching the budget to 100 MB made the populator refuse and the sweep report `warm-cache-oversize=1`. The spec text names the property and not these file or ConfigMap names.

**Dangling antecedents.** The sibling proposal `warm-seed-reflink-trust-closure` (ratified in livespec-dev-tooling v055) deliberately left these to this item: "per-start copy" and "a copied realization" are both inside the replaced sentence and go with it; "through the copy mechanism" no longer appears in the live clause (already removed at v055). The §"Runner-pool cache telemetry" phrases "copy outcome" / "copy method" describe the per-job seed span and stay accurate for a reflink seed; they are unchanged.

**Cross-repo check.** livespec core's `SPECIFICATION/non-functional-requirements.md` §"Self-hosted CI runner host requirements" carries no statement depending on the six-starts figure (grep for "six", "simultaneous", "per-start", "start-burst" at origin/master finds none); no co-change there.

**Ratification mechanics.** Single-file change, no `## ` heading change, so no `tests/heading-coverage.json` co-edit; front-matter topic equals the file stem `cache-tiers-seed-budget`. Filed on behalf of livespec work-item `livespec-1qpt` (plan `ci-runner-pod-lifecycle-reliability`, epic `livespec-ifwnqj`, Carrier F4c).

### Proposed Changes

In `non-functional-requirements.md` §"Runner-pool build cache tiers", paragraph **Tiers.**, replace exactly one sentence. The replace target below exists verbatim in the live file (verified at origin/master before filing). No other file, paragraph, or `## ` heading changes; no `tests/heading-coverage.json` co-edit is needed.

The replacement MUST keep the host-served preference and MUST re-ground it: a host-served realization MUST be preferred over a seeded tree; a seeded tree MUST NOT ship unbounded; its per-start cost MUST be capped by one byte budget and one file budget stated in exactly one committed place that both the populator and the node's lifecycle sweep read; the populator MUST refuse to publish a generation over either budget and leave the previous generation live; the sweep MUST report over-budget generations and seeds as lifecycle findings with gauges; a per-start byte copy of a cache MUST NOT ship in any tier; and the six-starts figure MUST be recorded as measurement history rather than as a premise.

```diff
--- a/non-functional-requirements.md
+++ b/non-functional-requirements.md
@@ **Tiers.** @@
-Because per-job start writes are the pool's measured disk knee (about six simultaneous job starts saturate the array), a host-served realization MUST be preferred over a per-start copy wherever the package manager can consume one, and a copied realization MUST NOT ship without its per-start bytes measured against the pool's start-burst budget.
+Because every byte and file a seed adds to a job start is overhead on any medium — the pool's largest single write source whatever array is beneath it — a host-served realization MUST be preferred over a seeded tree wherever the package manager can consume one, and a seeded tree MUST NOT ship unbounded: its per-start cost MUST be capped by one byte budget and one file budget stated in exactly one committed place that both the populator and the node's lifecycle sweep read; the populator MUST refuse to publish a generation over either budget, leaving the previous generation live; and the sweep MUST report, as lifecycle findings with gauges, a live generation over budget and a seed whose measured bytes or duration exceed their budgets. A per-start byte copy of a cache MUST NOT ship in any tier. The pool's start-burst limit is that budget, not a hardware knee: the figure this clause once cited — about six simultaneous job starts saturating the array — was a 2026-09-02 measurement of the previous three-drive array, and on the rebuilt array no start-burst knee was observed at 32 concurrent jobs and 18 starts per minute; that figure is measurement history held in the plan record, not a premise of this clause.
```

