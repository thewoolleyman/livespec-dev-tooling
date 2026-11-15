---
topic: the-incident-fleet-audit-lists
author: claude-opus-5-5 (bqnzcm plan seat)
created_at: 2026-11-15T18:51:12Z
---

## Proposal: the fleet audit lists an adopter ready only when its observer-dependent CI can reach the observer

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Extend the fleet audit's ready-list rule in contracts.md §"Expedited incident execution". The audit MUST NOT list an adopter ready while any of three adopter-side conditions holds, and each MUST be named in its findings: (1) the adopter's incident-ci job, or the job that runs its check-red-green-replay leg, takes its runs-on from a label expression that does not resolve first to a tailnet-reaching runner label set; (2) the adopter's check-red-green-replay step lacks any of LIVESPEC_INCIDENT_OBSERVER_URL, LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR or LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN; (3) a member the adopter's released inventory classes not-applicable runs unconditionally on an incident pull request with no incident-policy omission. A new scenario states the refusal.

### Motivation

Work item livespec-dev-tooling-7jxppa (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm; spec-change tier, linked topic the-incident-fleet-audit-lists, v229). This is the routing half of the root cause of the eight-generation orchestrator adoption smoke run (livespec-dev-tooling-s6jt4u, incident bd-ib-r4xzme), which the maintainer on 2026-11-15 asked to be fixed everywhere and permanently. The audit checked that each adopter's observer was installed and bound to its repository, but never that the CI jobs needing the observer could reach it. The orchestrator's CI_RUNNER_LABELS was ["ubuntu-latest"], so its incident CI ran on GitHub-hosted runners that cannot reach the tailnet-only observer, and each generation failed one job at a time. The same class recurred on 2026-11-15 in livespec-dev-tooling itself: drill PR livespec-dev-tooling#4801's incident-ci (run 43734431225) timed out reading /current because CI_INCIDENT_RUNNER_LABELS was ["ubuntu-latest"], while the audit had no way to say so. The ratified fleet-audit text (the paragraph beginning "The fleet audit MUST be runnable") lists a repository ready once its controller, recovery and driver-hook rows carry implemented claims, and says the incident CI entrance reads the observer's query route; it states none of these adopter-side readiness findings.

### Proposed Changes

In SPECIFICATION/contracts.md §"Expedited incident execution", add a paragraph immediately after the paragraph beginning "The fleet audit MUST be runnable":

> The fleet audit MUST read each adopter's default-branch `.github/workflows/ci.yml` and MUST NOT list that adopter ready while any of the following holds, and its findings MUST name the adopter and the condition:
> (1) the adopter's `incident-ci` job, or the job that runs its `check-red-green-replay` leg, takes its `runs-on` from a label expression whose first resolved label set is not a tailnet-reaching runner set (for example a repository variable reading `["ubuntu-latest"]`, or an inline `ubuntu-latest` fallback taken because the variable is unset); the finding MUST name the job and the label expression;
> (2) the adopter's `check-red-green-replay` step lacks any of `LIVESPEC_INCIDENT_OBSERVER_URL`, `LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR` or `LIVESPEC_INCIDENT_OBSERVER_QUERY_TOKEN`; the finding MUST name each missing input;
> (3) a member the adopter's released incident CI inventory classes `not-applicable` runs unconditionally on an incident pull request with no incident-policy omission; the finding MUST name the member.
> A repository variable the audit cannot read MUST count as unverified, never as conforming. An adopter onboarded after this rule is held to it before its first ready listing. The enablement step, which reads only the audit's ready list, therefore MUST refuse such an adopter.

In SPECIFICATION/scenarios.md, add after §"Scenario: the incident fleet audit command refuses enablement for a consumer without verified serving evidence":

```gherkin
## Scenario: the incident fleet audit refuses readiness when an adopter's observer-dependent CI cannot reach the observer

Given an adopter whose observer installation and every incident surface row carry verified implemented claims
And whose incident-ci job takes its runs-on from a repository variable reading ["ubuntu-latest"]
When the operator runs `just incident-fleet-audit`
Then the ready list MUST NOT include that adopter
And its findings MUST name the adopter, the incident-ci job and the label expression
And the same audit MUST also refuse readiness, naming the missing input, when the adopter's check-red-green-replay step lacks LIVESPEC_INCIDENT_OBSERVER_CONNECT_ADDR
And the incident enablement step run for that adopter MUST refuse and enable nothing.
```
