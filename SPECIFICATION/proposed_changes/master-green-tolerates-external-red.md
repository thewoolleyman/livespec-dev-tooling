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

Add a shared external-cause helper that records {dependency, kind, evidence} from the transport or HTTP layer. Add a master-health check run that ci-green publishes on master pushes, stating external only when every failed gating job published a record, otherwise defect. master_ci_green reads it in its existing forge call: it blocks on defect, absent or unreadable; warns and admits on external; and blocks again with a needs-attention signal after 24 hours. ci-green's own red verdict is unchanged, and no lever changes the decision. Add four scenarios.

### Motivation

Maintainer, verbatim, 2026-11-15 ~23:1x-23:5xZ (recorded in the plan-scope-event on livespec-dev-tooling-6tgd2z, the copy marked SUPERSEDES): "we want some easy way to incorporate this concept into future situations that are the same, where master is read for something external, and we don't want to stop everything completely"; "it should be designed flexibly so it can handle any sort of external outage that meets this category of failure. Whether it's any GitHub failure or something else, it could be that the internet is down. It could be anything else: a third-party tool is down or something that we rely on is down but we can still do commits and push things through. That's the category of error that we care about: things that are not our own problem to fix or cannot be fixed immediately for some reason external to us"; and "Make the time limit like a day. Hopefully all external errors can be resolved within a day". From another seat, pasted by the maintainer: "The whole point is to not let failures stack up" / "But this failure is external. It's not due to anything we can fix". This realizes the companion livespec core rule for the shared check. It answers the vacuous-gate objection recorded at fleet/_manifest_git.py:40-45 (z4qi, sh71, x7ml): the failing check's own verdict stays red, and only the local gate's decision changes, on evidence. Fleet scope: master_ci_green and ci-green are fleet-shared.

### Proposed Changes

Add to `contracts.md` a new section, after `## Master-health reconciler`:

## Master-green gate and external red

This section realizes livespec core `non-functional-requirements.md` §"The master-green gate tolerates an external red, on evidence and for at most one day" for the shared check `master_ci_green` and the shared `ci.yml` aggregate.

**External-cause records.** The library MUST provide one shared helper that every gating job and check calls when a call to a dependency fails at the transport or HTTP layer. The helper MUST classify the failure from that layer's own result and MUST emit an external-cause record `{dependency, kind, evidence}` only for an external kind: a forge rate-limit or quota response, a forge 5xx, a connect failure, DNS failure or timeout to a host the fleet does not run, or a documented outage response of a third-party dependency. A 401 or 403 on a credential the fleet configures, a test, lint or type failure, and a configuration error MUST NOT yield a record. A gating job that fails MUST publish, with its result, the external-cause records produced during its run, and none when the helper produced none.

**The master-health check run.** On a `push` to `master`, `ci-green` MUST publish one additional check run named `master-health` on the head commit. Its conclusion MUST be `success` when every gating job succeeded. When a gating job failed, its output MUST state `external` only when every failed gating job published at least one external-cause record, and `defect` otherwise, and it MUST list each failed job with its records. `ci-green`'s own conclusion MUST NOT change: it stays `failure` whenever a gating job failed.

**The gate.** `master_ci_green` MUST read `master-health` from master's own push run of the head commit, in the same forge call it already makes for `ci-green`. It MUST block exactly as today when `master-health` is absent, unreadable, or states `defect` (fail closed). When `master-health` states `external`, it MUST exit `0` with a structured `warning` naming each dependency and kind, for every commit and push, until master's push run reads green. It MUST block again once master's push runs have stated `external` continuously for 24 hours, measured from the earliest consecutive external head's run completion, and it MUST then raise the repository's needs-attention signal. No environment variable, flag or configuration key MAY change this decision; the 24-hour limit is a module constant.

Add to `scenarios.md`:

## Scenario: master_ci_green warns and admits a push while master is red only for an external cause

```gherkin
Given master's head push run has a failed gating job whose only failure is a forge 503 recorded by the external-cause helper
And ci-green reads failure and master-health states external with that record
When master_ci_green runs in a pre-push gate
Then it exits 0 with one warning naming the forge dependency and the 5xx kind
```

## Scenario: master_ci_green blocks when master-health states defect

```gherkin
Given master's head push run has a failed gating job that published no external-cause record
And master-health states defect
When master_ci_green runs in a pre-push gate
Then it blocks, naming that job
```

## Scenario: master_ci_green treats a 403 on the fleet's own App as a defect

```gherkin
Given a gating job on master fails because the fleet's own App token receives a 403
When the external-cause helper classifies the failure
Then it emits no external-cause record
And master-health states defect
```

## Scenario: master_ci_green blocks and alerts after one day of external-only red

```gherkin
Given master's push runs have stated external continuously for 24 hours
When master_ci_green runs in a pre-push gate
Then it blocks
And the repository's needs-attention signal is raised
```

The new `## ` headings MUST receive `tests/heading-coverage.json` rows, and any spec-first `TODO` row its debt-register entry, in the revise commit.
