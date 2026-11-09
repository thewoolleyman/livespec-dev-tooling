---
proposal: a-compilation-cache-warm-build.md
decision: modify
revised_at: 2026-11-09T08:34:12Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The proposal carries livespec-dev-tooling-uyevam (spec-change tier partial): the busy-pool guardrail is correct and stays, but nothing records how long a repository's compilation-cache warm set has lagged because of busy skips. It adds a per-repository skipped-busy count and last-built record to the populate manifest, a host gauge, and a report-only lag trigger, with two scenarios. Accepted in substance, modified so the text works against the live populator, gauge emitter and trigger system (warm-cache-populate.sh, ci-cache-gauges.sh, ci-runner/observability/triggers/ at 8618b7e9). The modifications came from a pre-merge doctor objective/subjective pass over the first draft, which also corrected that draft's wrong replacement of 'populate manifest'.

## Modifications

(1) 'populate manifest' is kept and DEFINED on first use as the record the populator writes at the end of each run and the host's liveness-path gauges read: it is $WARM_ROOT/populate-manifest.json (warm-cache-populate.sh ~l.1276, read by ci-cache-gauges.sh), which already carries sccache_skipped_busy; last-run.json is written before the sccache loop and read by the lifecycle sweep, so it is not the record. (2) 'compilation-cache warm build' and 'warm set' are defined on first use (the populator's writer build of the default branch into the compilation cache, and the cache entries it writes), so the target-generation builds are not read in. (3) The last-built record, the reset, the lag gauge and the trigger name the default-branch commit AND toolchain, the toolchain being the one the repository's checkout resolves: the already-in-cache test compares a per-repository sha@toolchain marker. (4) The manifest also records the start time of the first run that found the warm set behind, the reset clears it, and the lag gauge and the trigger's two-interval span are measured from it; without it the emitter cannot compute a lag and the threshold has no start point. (5) 'older than' became 'other than'. (6) The host-gauge emit list is separated by semicolons so the new per-repository item parses. (7) Scenario 1's trigger line says the description names the repository, lag and count 'as the fields it reports', because a Honeycomb trigger description is static text; scenario 2's When line covers both reset paths. (8) Scenarios are in scenarios.md's plain Given/When/Then style. The busy-pool guardrail text is unchanged. (9) The record moved into its own **Warm-set record.** paragraph after **Populator guardrails**. Every outcome of a repository's compilation-cache warm build now has a defined effect: a build from the current head and toolchain that is recorded in the cache, or finding that pair already recorded, resets the count and clears the lag start time; any other outcome (a failed or refused build, a build whose record cannot be written, an unreachable cache, an unreadable admitted-job count) resets the count and keeps the lag start time; a run that does not attempt the build (no writer credential, binary or Rust toolchain, so it stops before reading the cache's record) leaves both unchanged. (10) From a pre-merge doctor pass on 2026-11-09 against warm-cache-populate.sh, ci-cache-gauges.sh and the trigger JSON: the lag also starts when the cache holds no record of any build, since the marker key can be evicted under memory pressure; the last-built record stays unchanged when the cache cannot be read; the two per-repository gauges are emitted together with a repository attribute under names distinct from the existing per-run skipped-busy gauge; the trigger's run count is the number of runs the schedule starts in two intervals; and the trigger must stop being met within one trigger evaluation window (its query time range plus one evaluation frequency), because a trigger reads a trailing window of gauge values. (11) A third scenario covers a failed build ending the busy-skip streak while keeping the lag start time. Rebuilt as v163 on master 07fe1fc9 (v162).

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T08:33:40Z
verdict: NO BLOCKERS
proposal_stem: a-compilation-cache-warm-build
content_digest: 83ec17567f5e6319b0ec62988e37a0daa215fe4b66a17dca436eb7798ca5e2ac
