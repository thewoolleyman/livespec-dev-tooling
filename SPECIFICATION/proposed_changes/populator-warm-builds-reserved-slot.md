---
topic: populator-warm-builds-reserved-slot
author: claude-opus-5-5
created_at: 2026-11-14T01:19:07Z
---

## Proposal: Populator warm builds run in a reserved slot outside the pool's admitted-job count

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Replace the Populator guardrails rule that the populator MUST NOT start a build while the pool's admitted-job count is above a configured threshold. In its place, the populators' Rust warm builds run in one reserved warm-build slot, shared by the regular and the fabro populator and held outside the pool's Kueue admission count. They keep their CPU-parallelism cap and lowest CPU and I/O priority, and are never skipped or deferred because of the admitted-job count. Their cost to the pool is bounded by throughput: a warm build during a saturated pool MUST cost the pool's jobs no more than one more admitted job would. The Warm-set record's consecutive skipped-busy count, the Warm-set lag trigger's closing sentence and the busy-skip lag scenario are redefined around the one remaining deferral, a slot held by the other populator's running warm build. A slot whose holder has ended, outlived its Job deadline or cannot be read is free, so a crashed build cannot block warming. The cost bound names its sources: `livespec.ci_kueue.admitted` for the admitted count, in hourly bands of 4, and `ci.job.*` spans in `github-ci` for job wall time, queue wait and throughput. Two new scenarios state the saturated-pool cost bound and the stale-slot takeover.

### Motivation

Work item livespec-dev-tooling-n734d6 (child of plan epic livespec-dev-tooling-7zozck, ci-cache-optimization), filed and directed by legacy-coordinator-agent on 2026-11-14. The admitted-job threshold (16, half the churn-slot cap) assumed that 'a skipped tick costs nothing — the marker key makes the next idle tick build' (warm-cache-cronjob.yaml). The pool no longer has idle ticks. Over 24 h to 2026-11-14 ~01:20Z, Honeycomb livespec.ci_kueue.admitted on poweredge-xubuntu (query run 5j1nd3K8sB2) read at or under 16 in only 2 of the 24 hourly buckets holding the fabro populator's :05 tick, and in only 14 of 144 ten-minute buckets (04:40Z and 11:20-16:40Z). The gauge under-reads the populator's own count (30 against 41 at about 01:00Z), so this is an upper bound. In 48 h only 2 fabro warm pods did real work (k8s.pod.cpu.time, query run GGCoM1T2tKJ). Every retained regular populate run logged its compilation-cache and target-generation builds as skipped busy. The fork's compilation cache is therefore warmed at most about once in 12 hours, the regular populator's warm sets lag the same way, and the warm-set lag trigger reports a lag the guardrail itself causes. An off-peak schedule was considered and rejected: the measured quiet windows are narrow and shift with the fleet's work, and a fixed schedule would still skip whenever its window is busy. The throughput bound follows the maintainer's capacity rule recorded in .ai/ci-node-capacity-reads.md ('Utilization is not the target; throughput is'): the warm build is judged by what it costs the pool's jobs, not by an admitted-count proxy.

### Proposed Changes

### non-functional-requirements.md, section "Runner-pool build cache tiers", paragraph **Populator guardrails.**

The paragraph MUST be replaced by:

> **Populator guardrails.** The populator's Rust builds run on the node the jobs use. The populator MUST cap their CPU parallelism and MUST schedule them at a lower CPU and I/O priority than jobs. The regular populator and every per-repository populator (the fabro fork's is the shipped example) MUST share ONE warm-build slot, so that at most one Rust warm build runs on the node at a time. A populator that finds the slot held by a running warm build MUST defer its build to its next run. The slot MUST be released when its holder ends, whether the holder succeeds, fails or is killed. A slot whose holder is no longer running, or whose hold has lasted longer than the holding populator Job's own run deadline (its CronJob's `activeDeadlineSeconds`), MUST be treated as free and MAY be taken over. A slot whose holder cannot be read MUST NOT block warming: the populator MUST then treat the slot as free and build. The slot MUST be held outside the pool's admission control: a warm build MUST NOT be counted in any Kueue ClusterQueue's admitted workloads and MUST NOT consume a churn slot. A populator MUST NOT skip or defer a build because of the pool's admitted-job count. A warm build's cost to the pool is bounded by throughput instead, measured over a trailing 24 hours as follows. The admitted-job count is the gauge `livespec.ci_kueue.admitted` in the Honeycomb `metrics` dataset, filtered to the pool's server node (`host.name = poweredge-xubuntu`). Each UTC clock hour is assigned the mean of that gauge over the hour, and its admitted band is that mean rounded down to a multiple of 4; "hours at the same admitted count" means hours in the same band. The job figures come from the routed CI job spans (span `name` starting `ci.job.`) in the Honeycomb `github-ci` dataset: the hour's p50 of `duration_ms` (job wall time), the hour's p95 of `ci.job.queue_ms` (queue wait), and the hour's count of those spans (jobs completed). The cost of one additional admitted job is each figure's least-squares slope against the hourly mean admitted count, over every hour of the window. A warm build that runs during an hour whose mean admitted count is at or above 30 MUST NOT raise that hour's job wall time p50 or queue wait p95 above the mean of the same figure over the same band's hours that contain no warm build by more than that figure's slope. It MUST NOT lower that hour's jobs completed below the same band's no-warm-build mean. When a measurement shows the bound exceeded, the populator's CPU cap or priority MUST be lowered; an admitted-job gate MUST NOT be reintroduced. The populator's duration and per-repository outcome MUST be recorded per generation. A RAM-resident compilation-cache backend MUST have a fixed memory ceiling with an eviction policy, and that ceiling MUST be sized against the pool's concurrency cap so that cache memory and job memory do not compete for the same headroom.

### non-functional-requirements.md, same section, paragraph **Warm-set record.**

The clause defining the consecutive skipped-busy count MUST change from "the consecutive skipped-busy count, how many consecutive populate runs have skipped that build as busy because the pool's admitted-job count was above the threshold" to "the consecutive skipped-busy count, how many consecutive populate runs have deferred that build because another populator's warm build held the shared warm-build slot". In the sentence listing outcomes that are not a busy skip, the example "or an admitted-job count that cannot be read" MUST be deleted: the populator no longer reads the admitted-job count, and a warm-build slot whose holder cannot be read does not defer the build (**Populator guardrails** treats it as free), so neither is an outcome of a deferred build. A deferral behind a stale slot cannot occur, because a stale slot is free. Every other sentence of the paragraph is unchanged.

### non-functional-requirements.md, section "Runner-pool cache telemetry", paragraph **Warm-set lag trigger.**

The closing sentence MUST change from "The trigger reports the lag only: the **Populator guardrails** rule that the populator MUST NOT start a build while the pool's admitted-job count is above its threshold applies unchanged while the trigger is met." to "The trigger reports the lag only: it MUST NOT change when or whether a populator starts a build, which **Populator guardrails** alone governs."

### scenarios.md, "## Scenario: a compilation-cache warm build skipped as busy past two populate intervals fires the lag trigger"

The H2 heading MUST be kept verbatim. Its body MUST be replaced by:

> Given a repository's default-branch head has moved past the commit its compilation-cache warm set was last built from
>
> And another populator's warm build held the shared warm-build slot, so every populate run for longer than two populate intervals deferred that repository's compilation-cache warm build as busy
>
> When the host's liveness path emits that repository's consecutive skipped-busy count and warm-set lag
>
> Then the populate manifest MUST show that repository's consecutive skipped-busy count, the commit and toolchain its warm set was last built from, and a lag start time no later than the first of those deferred runs
>
> And the warm-set lag value trigger MUST fire for that repository, and its description MUST name the repository, the warm-set lag and the consecutive skipped-busy count as the fields it reports
>
> And the populator MUST NOT have deferred or skipped that build because of the pool's admitted-job count

### scenarios.md, two new scenarios after the scenario above

Two new scenarios MUST be added, in this order:

> ## Scenario: a warm build that starts while the pool is saturated costs the pool no more than one admitted job
>
> Given the pool's admitted-job count is at or above 30
>
> And a repository's compilation-cache warm set is behind its default-branch head, and no other warm build holds the shared warm-build slot
>
> When a populate run reaches that repository's compilation-cache warm build
>
> Then the populator MUST start the build in the shared warm-build slot, at its capped CPU parallelism and lowest CPU and I/O priority
>
> And the build MUST NOT be counted in any Kueue ClusterQueue's admitted workloads
>
> And over the trailing 24 hours, measured as **Populator guardrails** defines (hourly mean `livespec.ci_kueue.admitted` on `poweredge-xubuntu` in bands of 4; `ci.job.*` spans in `github-ci` for the p50 of `duration_ms`, the p95 of `ci.job.queue_ms` and the hourly job count), every hour with a mean admitted count of 30 or more that contained a warm build MUST show its job wall time p50 and queue wait p95 no more than that figure's slope above its band's no-warm-build mean, and its jobs completed no lower than its band's no-warm-build mean
>
> ## Scenario: a warm-build slot whose holder has died is taken over
>
> Given the shared warm-build slot is recorded as held
>
> And its holder is no longer running, or its hold has lasted longer than the holding populator Job's run deadline, or its holder cannot be read
>
> When a populate run reaches a repository's compilation-cache warm build that is behind its default-branch head
>
> Then the populator MUST treat the slot as free, take it and start the build
>
> And the populate manifest MUST NOT count that run as a busy skip for the repository

The revise that accepts this proposal MUST add both new headings to `tests/heading-coverage.json` and to the generated debt register in the same commit, naming livespec-dev-tooling-n734d6 as the owning work item and the integration tier or above as the owed test's tier.

A delegated gate Job's own wall time is NOT used as a figure: the `livespec-delegated-gate` dataset's only span (`livespec.delegated-gate.outcome`) records a zero duration, and no gate wall-time gauge exists in `metrics` (read 2026-11-14 ~02:30Z). The routed CI jobs' `ci.job.*` spans carry the same CPU-contention signal with a real duration.
