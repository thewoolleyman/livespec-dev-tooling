---
topic: port-fabro-hosts-check-settings
author: claude-opus-5-5
created_at: 2026-11-05T08:12:27Z
---

## Proposal: The fabro-hosts drift report compares each instance's resolved settings with its declaration

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend §"Fabro factory host provisioning" **One play, applied after a drift read.** so that `just ansible-drift ansible/fabro-hosts.yml` reports every resolved setting of each Fabro server instance that differs from the instance's host_vars declaration. This replaces fabro-hosts' hand-run check-settings.sh. Add one scenario.

### Motivation

Research note 001 of plan ci-pool-provisioning-leftovers found four class (a) host-glue rows in the fabro-hosts repository with no role and no owner: services/fabro-server/check-settings.sh, its per-host hosts/*.env (five files, one for the retired hp-xubuntu factory role) and *.settings.expected. They compare GET /api/v1/settings against an expected file, a step fabro-hosts' AGENTS.md calls "an open decision". The plan session decided to port the comparison into the fabro_server role's drift report, which already compares plugin pins. The carrier is livespec-dev-tooling-po2nrg, which the filing-time tier classifier held at spec-change tier because the ratified drift clause covers plugin pins only.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Fabro factory host provisioning", append to the paragraph **One play, applied after a drift read.**:

`just ansible-drift ansible/fabro-hosts.yml` MUST also report, for each Fabro server instance on a host, every setting that the instance's settings endpoint (`GET /api/v1/settings`) resolves to a value different from the one that instance's mapping in host_vars declares, and MUST report each such difference as drift, naming the instance, the setting, and both values. A setting the mapping does not declare MUST NOT be reported. The comparison MUST read the live server and MUST NOT change it. When an instance's settings endpoint cannot be reached, the drift report MUST say so for that instance and MUST NOT report it as matching. No per-host expected-settings file outside `ansible/` is a source for this comparison.

In SPECIFICATION/scenarios.md, add after §"Scenario: an apply refuses a plugin binary whose digest differs from an instance pin, and drift compares live pins to the installed binary":

## Scenario: drift reports a Fabro instance whose resolved setting differs from its declaration

Given a Fabro server instance whose host_vars mapping declares a setting with one value

And that instance's `GET /api/v1/settings` resolving the same setting to a different value

When `just ansible-drift ansible/fabro-hosts.yml` runs against the host

Then the report MUST name the instance, the setting, the declared value and the resolved value as drift

And the instance's live settings MUST be unchanged

And an instance whose settings endpoint cannot be reached MUST be reported as unreachable rather than as matching
