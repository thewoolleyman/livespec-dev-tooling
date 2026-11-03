---
topic: master-push-ci-routing
author: claude-opus-5-5
created_at: 2026-11-03T10:58:34Z
---

## Proposal: Master-push CI may route to its own self-hosted target through a second variable that falls back to the shared one

### Target specification files

- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Extend the merge-gating routing contract with an optional `CI_RUNNER_LABELS_MASTER` repository variable. Only a `push` event's gating jobs read it, and they fall back to `CI_RUNNER_LABELS` and then to the hosted literal. A master push can then run on a dedicated self-hosted scale set with a reserved, non-lendable capacity slice, instead of queuing behind pull-request CI. Pull-request routing is unchanged, and the hosted-literal floor and the manual-revert property are kept.

### Motivation

Measured 2026-11-03 (plan ci-runtime-and-cost, research 003; livespec-dev-tooling epic livespec-dev-tooling-ib3oe3). Over 24 hours, livespec-dev-tooling master-push CI jobs waited p90 50.7 min (max 109.7) to start, against p90 19.3 min for pull_request jobs. Every master run in the release storms 23:30–03:15Z and 08:13–10:00Z waited 28–110 min. Master and pull-request jobs share one `runs-on` target, so they share one GitHub assignment queue, one scale set capped at 12 runners, and one Kueue ClusterQueue where every workload has priority 0. ARC creates the runner pod before GitHub assigns it a job, so no pod-level priority can distinguish them; only `runs-on` can. A starved master is not just slow. The orchestrator Dispatcher's master-CI preflight refuses every dev-tooling dispatch while master CI stays pending beyond its bounded wait, and items ftgiu4 and dnokt2 were refused that way. legacy-coordinator-agent ruled the change on 2026-11-03: a dedicated master scale set and a Kueue slice of 3 churn slots taken from this repository's 6, with lendingLimit 0 and preemption Never. Today the constraint names `CI_RUNNER_LABELS` with its inline fallback as "the entire routing contract", so a second variable needs this amendment first.

### Proposed Changes

In `constraints.md` §"CI matrix shape", replace the second paragraph (beginning "This repository's merge-gating CI routes to self-hosted capacity through the `CI_RUNNER_LABELS` repository variable") with:

This repository's merge-gating CI routes to self-hosted capacity through the `CI_RUNNER_LABELS` repository variable, read directly at each gating job's `runs-on` with an inline literal fallback naming GitHub-hosted capacity. This is the fleet's standard self-hosted routing pattern. Setting the variable to a self-hosted target routes there. Restoring it to the hosted literal, or deleting it so the inline fallback applies, returns the gate to GitHub-hosted capacity.

A gating job running for a `push` event MAY instead route through the `CI_RUNNER_LABELS_MASTER` repository variable, read at the same `runs-on` ahead of `CI_RUNNER_LABELS`, in the form `fromJSON(github.event_name == 'push' && vars.CI_RUNNER_LABELS_MASTER || vars.CI_RUNNER_LABELS || '<hosted literal>')`. Only push events read it, so pull-request and merge-group routing are unchanged by it. While it is unset or empty, a push routes exactly as a pull request does. It exists so that a default-branch push can run on a dedicated self-hosted target whose capacity is reserved for it, rather than queuing behind pull-request CI on a shared one. The orchestrator's master-CI preflight refuses dispatch while the default branch's CI stays pending, so default-branch CI latency gates the whole factory, not only the branch.

Both reverts are MANUAL and operator-driven. Deleting `CI_RUNNER_LABELS_MASTER` returns pushes to `CI_RUNNER_LABELS`, and deleting both returns every gating job to the inline hosted literal. No health probe or automatic runtime failover stands between the variables and the routing decision, so the two variables' settings together with the inline fallback are the entire routing contract. The inline fallback MUST be the last term of that expression, MUST name hosted capacity, and MUST NOT name self-hosted capacity, so that deleting or emptying either variable leaves the merge gate on capacity that is always present. The reusable check workflows this library ships to consumers remain on GitHub-hosted runners and MUST NOT require the shared factory host's self-hosted labels. The matrix and required-check semantics are unchanged; only the execution capacity changes.

In `scenarios.md`, append:

## Scenario: a default-branch push routes to the master runner target and a pull request does not

Given this repository's `ci.yml` gating jobs read `CI_RUNNER_LABELS_MASTER` ahead of `CI_RUNNER_LABELS` for `push` events, with the hosted literal as the last term

When `CI_RUNNER_LABELS_MASTER` names a self-hosted target and a commit is pushed to master

Then every gating job of that push run MUST run on the target `CI_RUNNER_LABELS_MASTER` names

And every gating job of a pull-request run opened at the same time MUST run on the target `CI_RUNNER_LABELS` names

And when `CI_RUNNER_LABELS_MASTER` is deleted, the next push run's gating jobs MUST run on the target `CI_RUNNER_LABELS` names

And the last term of every gating job's `runs-on` expression MUST be a GitHub-hosted literal

In the revise commit, add the matching `tests/heading-coverage.json` row for the new scenario heading. It is a `"test": "TODO"` row whose reason names the consumer tier (a test reading `ci.yml`'s gating `runs-on` expressions) plus a host-captured observation of a live push run, and the owning work item. Regenerate `tests/heading-coverage-debt.json`. The existing `## CI matrix shape` row's test stays valid, because the matrix entry set is unchanged.
