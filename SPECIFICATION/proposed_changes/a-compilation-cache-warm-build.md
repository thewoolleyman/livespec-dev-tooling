---
topic: a-compilation-cache-warm-build
author: claude-opus-5-5
created_at: 2026-11-07T20:37:08Z
---

## Proposal: The populator records compilation-cache warm builds skipped as busy, and a trigger reports a warm set lagging its default branch

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Require the populate manifest to record, per repository, the consecutive skipped-busy count of the compilation-cache warm build and the default-branch commit its warm set was last built from. Require the host to emit those values, and require a value trigger that fires when a repository's warm set lags its default-branch head for longer than two populate intervals and every run in that span skipped it as busy. The busy-pool guardrail is unchanged.

### Motivation

This carries work item livespec-dev-tooling-uyevam, filed 2026-11-05 at the maintainer's request as the "sccache warm-up skipped under contention" gap from the 2026-11-04 cache audit. The item's spec-change-tier verdict is `partial`: the telemetry section requires a trigger for a generation older than twice the populate interval, and **Populator guardrails** requires the busy skip and a per-repository outcome, but neither states a skipped-busy count, a last-built commit, or a trigger scoped to lag caused by busy skips.

The skip is correct and stays. What is missing is any signal of how long it has lasted. `warm-cache-populate.sh` counts `sccache_skipped_busy` per run only, as one total, so nothing shows which repository is lagging or for how many runs. On 2026-09-06 a busy pool skipped every refill for hours and livespec-console-beads's hit ratio fell from 59.3% to 0.35% (`ci-runner/k3s/phase2/sccache/README.md`). The existing per-repository hit-floor trigger is a trailing-day read, and it cannot tell a lagging warm set from any other cause of a low ratio.

The new trigger reports only. Letting the populator build under load after a maximum lag would change the guardrail, and this proposal does not do that. If this measurement shows a reason to, that is a separate proposal.

The description names the fields rather than live values because a Honeycomb trigger description is static text; the per-repository breakdown is what carries each repository's values.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool build cache tiers", **Populator guardrails**, immediately after the sentence ending "its duration and per-repository outcome MUST be recorded per generation.", insert:

> The populate manifest MUST record, for each repository that has a compilation-cache warm build, how many consecutive populate runs have skipped that build as busy and the default-branch commit the repository's warm set was last built from. A populate run that builds the warm set from the repository's current default-branch head, or that finds that head already in the cache, MUST reset the repository's consecutive count to zero.

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool cache telemetry", **Host gauges and triggers**, make two changes.

First, in the sentence listing what the CI host MUST emit, after "per-repository success and failure counts and toolchain version,", insert "per repository, the consecutive skipped-busy count of the compilation-cache warm build and how long its warm set has lagged the default-branch head,".

Second, immediately before the sentence beginning "Every trigger description MUST name the emitter path", insert:

> The fleet MUST carry a value trigger for compilation-cache warm-set lag. Its threshold MUST be met when a repository's warm set has been built from a default-branch commit older than that repository's current default-branch head for longer than two populate intervals and every populate run in that span skipped the build as busy, and it MUST NOT be met once the warm set is built from the current default-branch head. The trigger MUST report per repository, and its description MUST name the repository, the lag and the skipped-busy count as the fields it reports. This trigger reports the lag only: the **Populator guardrails** rule that the populator MUST NOT start a build while the pool's admitted-job count is above its threshold applies unchanged while the trigger is met.

In `SPECIFICATION/scenarios.md`, immediately after `## Scenario: a stale warm-cache generation fires the trigger`, add:

```gherkin
## Scenario: a compilation-cache warm build skipped as busy past two populate intervals fires the lag trigger

Given a repository's default-branch head has moved past the commit its compilation-cache warm set was last built from

And the pool's admitted-job count stayed above the populator's threshold, so every populate run for longer than two populate intervals skipped that repository's warm build as busy

When the host's liveness path emits that repository's skipped-busy count and warm-set lag

Then the populate manifest MUST show that repository's consecutive skipped-busy count and last-built commit

And the warm-set lag value trigger MUST fire for that repository, and its description MUST name the repository, the lag and the skipped-busy count

And the populator MUST NOT have started a build for that repository while the admitted-job count was above the threshold

## Scenario: rebuilding a lagging compilation-cache warm set clears the lag trigger

Given the warm-set lag value trigger is firing for a repository

When a populate run builds that repository's warm set from its current default-branch head

Then the populate manifest MUST show that repository's consecutive skipped-busy count as zero and its current default-branch head as the last-built commit

And the warm-set lag value trigger MUST NOT remain met for that repository
```

Revise co-edit: the two scenario headings are new H2 headings, so the revise commit MUST add a row for each to `tests/heading-coverage.json` and regenerate `tests/heading-coverage-debt.json`. Each row is a spec-first `"test": "TODO"` row whose `reason` names the consumer tier and whose `work_item` is `livespec-dev-tooling-uyevam`. No existing heading changes.

