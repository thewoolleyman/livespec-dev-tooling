---
topic: fabro-server-s-settings-comparison
author: claude-opus-5-5
created_at: 2026-11-12T12:29:40Z
---

## Proposal: A Fabro instance whose settings all match is named as matching in the drift report

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Require `just ansible-drift ansible/fabro-hosts.yml` to state, for each Fabro server instance whose declared settings all resolve to their declared values, that the instance matches, naming it and the number of settings compared. Today the clause requires drift and unreachable to be reported by instance and says nothing about a clean comparison, so a clean comparison is visible only as the absence of output.

### Motivation

Measured 2026-11-12 on gmktec-xubuntu from master a87b63d36 (livespec-dev-tooling#4272 merged): the fabro_server role read all four Fabro instances' resolved settings, and none drifted or was unreachable. For each matching instance the run printed nothing naming the instance and its result: both report tasks skipped, and only the role-include line named the instance. The run was correct under the ratified clause, but a silent clean result is not evidence an operator or a host-captured proof can point to (the same lesson as livespec-dev-tooling-lgbrc2, where a skipped task let a drift read changed=0 while work was pending). legacy-coordinator-agent ruled the positive match line new behaviour at spec-change tier (2026-11-12 ~12:3xZ). Implementation work item: livespec-dev-tooling-vlfuo5 (plan ci-pool-provisioning-leftovers, epic livespec-dev-tooling-fby3sx).

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, §"Fabro factory host provisioning", paragraph **One play, applied after a drift read.**, insert one sentence immediately after "When an instance's settings endpoint cannot be reached, the drift report MUST say so for that instance and MUST NOT report it as matching.":

> When every setting that an instance's mapping declares resolves to its declared value, the drift report MUST say so for that instance, naming the instance and the number of declared settings it compared, and MUST NOT report that instance as drifted or unreachable.

Nothing else in the paragraph changes. In particular, a setting the mapping does not declare is still never compared or reported, and the comparison still MUST read the live server without changing it.

In `SPECIFICATION/scenarios.md`, append this scenario after "## Scenario: drift reports a Fabro instance whose resolved setting differs from its declaration":

```
## Scenario: drift names a Fabro instance whose resolved settings all match their declarations

Given a Fabro server instance whose host_vars mapping declares a number of settings

And that instance's `GET /api/v1/settings` resolving each of those settings to its declared value

When `just ansible-drift ansible/fabro-hosts.yml` runs against the host

Then the report MUST name the instance as matching and MUST give the number of declared settings it compared

And the report MUST NOT name that instance as drifted or as unreachable

And the instance's live settings MUST be unchanged
```

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` row for the new scenario heading, plus its debt-register entry, in the same commit.
