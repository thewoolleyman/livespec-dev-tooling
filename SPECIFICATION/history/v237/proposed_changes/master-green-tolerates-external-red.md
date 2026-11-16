---
topic: master-green-tolerates-external-red
author: claude-opus-5-5 (bqnzcm plan seat)
created_at: 2026-11-15T23:24:54Z
---

## Proposal: master_ci_green tolerates an external red on master-health evidence for at most one day

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Add a shared external-cause helper that records {dependency, kind, evidence} from the transport or HTTP layer. Each failed gating job publishes its records, its defect-finding count and an external_only verdict that is true only when every failed step ended on a recorded external failure and it found no defect. Add a master-health check run that ci-green publishes from master's own push run, conclusion neutral on a red master, verdict in a fixed machine-read field, reading external only when every failed gating job published external_only true, otherwise defect. master_ci_green reads it only from master's own push runs of the head commit, with at most one additional forge read: it exits 1 on defect, absent or unreadable; warns and admits on external while the episode ci-green wrote into master-health is within 24 hours; and exits 1 once it is past the limit. ci-green, not the gate, computes the episode (the earliest run of the unbroken external-only sequence, no restart on a new head) and raises one idempotent needs-attention issue per episode from CI, so the gate stays read-only; master-health is never a required status check. ci-green's own red verdict is unchanged, and no lever changes the decision. Add eight scenarios.

### Motivation

Maintainer, verbatim, 2026-11-15 ~23:1x-23:5xZ (recorded in the plan-scope-event on livespec-dev-tooling-6tgd2z, the copy marked SUPERSEDES): "we want some easy way to incorporate this concept into future situations that are the same, where master is read for something external, and we don't want to stop everything completely"; "it should be designed flexibly so it can handle any sort of external outage that meets this category of failure. Whether it's any GitHub failure or something else, it could be that the internet is down. It could be anything else: a third-party tool is down or something that we rely on is down but we can still do commits and push things through. That's the category of error that we care about: things that are not our own problem to fix or cannot be fixed immediately for some reason external to us"; and "Make the time limit like a day. Hopefully all external errors can be resolved within a day". From another seat, pasted by the maintainer: "The whole point is to not let failures stack up" / "But this failure is external. It's not due to anything we can fix". This realizes the companion livespec core rule for the shared check. It answers the vacuous-gate objection recorded at fleet/_manifest_git.py:40-45 (z4qi, sh71, x7ml): the failing check's own verdict stays red, and only the local gate's decision changes, on evidence. Fleet scope: master_ci_green and ci-green are fleet-shared.

### Proposed Changes

Add to `contracts.md` a new section, after `## Master-health reconciler`:

## Master-green gate and external red

This section realizes livespec core `non-functional-requirements.md` §"The master-green gate tolerates an external red, on evidence and for at most one day" for the shared check `master_ci_green` and the shared `ci.yml` aggregate.

**External-cause records.** The library MUST provide one shared helper that every gating job and check calls when a call to a dependency fails at the transport or HTTP layer. The helper MUST classify the failure from that layer's own result and MUST emit an external-cause record `{dependency, kind, evidence}` only for an external kind: a forge rate-limit or quota response, a forge 5xx, a connect failure, DNS failure or timeout to a host the fleet does not run, or a documented outage response of a third-party dependency. The rate-limit kind MUST be recognised from the response's rate-limit evidence — `x-ratelimit-remaining: 0`, a `retry-after` header, or a rate-limit-exceeded message in the body — whatever the status code, because the forge returns it as 403 as well as 429. A 401 or 403 that carries no rate-limit evidence on a credential the fleet configures, a test, lint or type failure, and a configuration error MUST NOT yield a record.

**What a failed gating job publishes.** A gating job that fails MUST publish, with its result, the external-cause records produced during its run, its count of defect findings, and an `external_only` verdict that is `true` only when every failed step of the job ended on a recorded external failure and the defect-finding count is `0`. A job with any defect finding, or any failed step without a record, publishes `external_only: false`. A failed job that published no result counts as `external_only: false`.

**The master-health check run.** On a `push` to `master`, `ci-green` MUST publish one additional check run named `master-health` on the head commit, from master's own push run. Its conclusion MUST be `success` when every gating job succeeded and `neutral` when any gating job failed, never `failure`, so it neither duplicates `ci-green`'s verdict nor reads green on a red master. Its verdict MUST be carried in a FIXED machine-read field: `output.title` MUST be exactly one of `master-health: green`, `master-health: external` or `master-health: defect`, and `output.summary` MUST be one JSON object `{verdict, head_sha, run_id, episode, expired, jobs: [{name, external_only, defect_findings, records: [{dependency, kind, evidence}]}]}`; free text MAY appear only in `output.text`. The verdict MUST be `external` only when every failed gating job published `external_only: true`, and `defect` otherwise. `ci-green`'s own conclusion MUST NOT change: it stays `failure` whenever a gating job failed. `master-health` MUST NOT be a required status check, because the forge counts a `neutral` required check as passing.

**The episode clock and the alert are computed and raised from CI, never from the gate.** When the verdict is `external`, `ci-green` MUST compute the episode: it MUST read master's own push runs backwards from the head commit, through the unbroken sequence of runs whose `master-health` read `external`, stopping at the first run that read green or `defect`, and MUST write `episode: {earliest_run_id, started_at}` into `output.summary`, where `started_at` is the completion time of the earliest run in that sequence; a new head commit MUST NOT restart it. When `started_at` is more than 24 hours before the publication, `ci-green` MUST write `expired: true` and MUST raise the repository's needs-attention signal as the one idempotent forge issue per external-only episode, keyed on `earliest_run_id`, so that repeated publications raise nothing new; otherwise `expired: false`. When the verdict is `green` or `defect`, `episode` MUST be `null` and `expired` `false`. The same publishing step MUST also run on the repository's existing schedule against master's head commit, so that a quiet master during a long outage still crosses the limit and alerts. The 24-hour limit is a module constant of the publishing step.

**The gate.** `master_ci_green` MUST stay a read-only, world-reading check: its only forge access is the read-only `gh_read` wrapper it uses today, it MUST write nothing to the forge, and it MUST keep its existing purity declaration, so a memoized green tree still runs it on every push. It MUST read `master-health` only from master's own push runs of the head commit, selected exactly as the `ci-green` check run is today (branch `master`, event `push`, the head commit, and a check suite belonging to one of those runs), with no more than one additional forge read beyond the reads it makes today; a `master-health` run from a scratch branch or any other run is not evidence. When `ci-green` is red and `master-health` is absent, unreadable, or reads `defect`, the check MUST exit `1` (fail closed; the warn-only tolerance for a missing `ci-green` run does NOT extend to a missing `master-health`). When `master-health` reads `external`, the check MUST compare `episode.started_at` with the current time: while that is within the 24-hour limit and `expired` is `false`, it MUST exit `0` with a structured `warning` naming each dependency and kind, for every commit and push, until master's push run reads green; when `expired` is `true`, or `started_at` is more than 24 hours before now, or `episode` is missing or unreadable, it MUST exit `1` and raise nothing itself, because the alert belongs to the publishing step above. The 24-hour limit the gate compares against is the same module constant. No environment variable, flag or configuration key MAY change any of these decisions.

Add to `scenarios.md`:

## Scenario: master_ci_green warns and admits a push while master is red only for an external cause

```gherkin
Given master's head push run has a failed gating job whose only failure is a forge 503 recorded by the external-cause helper, published with external_only true and 0 defect findings
And ci-green reads failure and master-health reads external with that record
When master_ci_green runs in a pre-push gate
Then it exits 0 with one warning naming the forge dependency and the 5xx kind
```

## Scenario: master_ci_green blocks when master-health states defect

```gherkin
Given master's head push run has a failed gating job that published no external-cause record
And master-health reads defect
When master_ci_green runs in a pre-push gate
Then it blocks, naming that job
```

## Scenario: master-health reads defect for a job with an external record and one defect finding

```gherkin
Given a gating job on master fails with a rate-limited forge read recorded by the external-cause helper and also reports one defect finding
When ci-green publishes master-health
Then that job's published verdict is external_only false
And master-health reads defect
And master_ci_green blocks, naming that job
```

## Scenario: master_ci_green treats a 403 on the fleet's own App as a defect

```gherkin
Given a gating job on master fails because the fleet's own App token receives a 403 with no rate-limit evidence
When the external-cause helper classifies the failure
Then it emits no external-cause record
And master-health reads defect
```

## Scenario: a rate-limited 403 reads external

```gherkin
Given a gating job on master fails because a forge read returns 403 with x-ratelimit-remaining 0 and a rate limit exceeded message
And no other step of that job failed and it reports 0 defect findings
When the external-cause helper classifies the failure
Then it emits an external-cause record of the rate-limit kind
And master-health reads external
```

## Scenario: master_ci_green blocks when ci-green is red and master-health is absent

```gherkin
Given master's head push run reads ci-green failure and published no master-health check run
When master_ci_green runs in a pre-push gate
Then it exits 1
```

## Scenario: ci-green alerts once and master_ci_green blocks after one day of external-only red

```gherkin
Given master's push runs have read external in an unbroken sequence whose earliest run completed more than 24 hours ago, with no green run between
When ci-green publishes master-health for the head commit twice
Then each publication carries that earliest run's id and completion time as the episode and expired true
And exactly one needs-attention forge issue exists for that episode, keyed on the earliest run's id
And master_ci_green, reading that master-health in a pre-push gate, exits 1 and writes nothing to the forge
```

## Scenario: master_ci_green blocks when master-health reads external without a readable episode

```gherkin
Given master's head push run reads ci-green failure and master-health external
And master-health's output.summary carries no readable episode
When master_ci_green runs in a pre-push gate
Then it exits 1
```

The new `## ` headings MUST receive `tests/heading-coverage.json` rows, and any spec-first `TODO` row its debt-register entry, in the revise commit.
