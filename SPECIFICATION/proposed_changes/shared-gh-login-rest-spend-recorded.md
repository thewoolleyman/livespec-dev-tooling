---
topic: shared-gh-login-rest-spend-recorded
author: claude-opus-5-5 (seat github-request-budget-discipline)
created_at: 2026-11-14T07:30:46Z
---

## Proposal: The shared GitHub login's REST spend is recorded per caller on every seat host

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add one obligation under Host provisioning tree. Each provisioned host where agent sessions use the shared gh user login carries a role that samples the login's rate-limit reading once a minute and records every REST request with caller, host, time and endpoint. It also carries a per-caller, per-hour report that reconciles against the sampled budget. The login is an asserted out-of-band precondition.

### Motivation

On 2026-11-13 the shared `gh` user login's REST `core` budget read 0/5000 from 21:56Z to 22:30Z. Factory launches bounced at the master-CI preflight for about 33 minutes, and commit gates failed `check-master-ci-green`. A second exhaustion on the VPS near 04:31Z on 2026-11-14 surfaced as a false Fabro-currency dispatch refusal (livespec-orchestrator-beads-fabro bd-ib-kvy72t). About 30 agent seats on several hosts, plus the factory launcher's preflight, spend that one bucket, and GitHub does not attribute spend per caller. A one-host look-back found hetzner-xubuntu spent only about 100 to 150 REST requests over 20:00 to 23:00Z on 2026-11-13. A live reading at 00:00Z on 2026-11-14 showed about 2,100 requests per hour, over 95% of it from other hosts (livespec plan/github-request-budget-discipline/research/02-caller-inventory-2026-11-14.md). Nothing in the fleet can say which caller spent it, which blocks every mitigation under livespec-j49m's measure-before-mitigating disposition. Counting invocations would undercount the leading suspect, because `gh run watch` polls REST every 3 seconds by default from one invocation. This ruling governs livespec-dev-tooling-w4dicq, which builds the gh_request_ledger role in ansible/. Its pre-dispatch Definition-of-Done judgement at 2026-11-14T07:20:54Z found no ratified clause stating the sampler, wrapper and report behaviour. The clause sits under Host provisioning tree because that section already governs roles that install onto provisioned hosts, and their out-of-band preconditions. Plan github-request-budget-discipline (livespec epic livespec-httc), throughput track rank 10.

### Proposed Changes

In non-functional-requirements.md section "Host provisioning tree", insert this paragraph directly after the paragraph beginning **Out-of-band preconditions fail at the start.**:

> **The shared GitHub login's REST spend is recorded per caller.** Each host this tree provisions on which agent sessions call GitHub through the shared `gh` user login, and each host whose own provisioning consumes this tree's roles at a pinned commit, MUST carry a role that records that login's REST spend. The role MUST sample the login's rate-limit reading at least once a minute into a durable per-host log, through the rate-limit endpoint alone, which spends no budget. It MUST record every REST request made through the login on that host with a caller label, the host, a UTC timestamp and the endpoint, counting each HTTP request a long-running `gh` process makes rather than one record per invocation. It MUST pass each wrapped command's arguments, exit status, standard output and standard error through unchanged. A report command MUST print REST requests per caller per UTC hour for a chosen day beside the rise in the login's `core` used that the sampled log shows for that hour. The record covers requests made through the `gh` command; a process that calls the REST API with the login's token directly, without `gh`, is out of its scope, so the report MUST also print, for each hour, an unattributed row equal to the sampled `core` rise minus the recorded requests. GraphQL requests draw on a separate budget and are excluded from both the record and the report. Both logs MUST be rotated so that each host keeps at most 14 days of them, which MUST NOT be shorter than the report's window. The shared login is an out-of-band input under **Out-of-band preconditions fail at the start**: the role MUST assert it before its first task that changes the host, and a converge without it MUST fail at that assert naming the missing login.

No `## ` heading is added, changed or removed, so tests/heading-coverage.json needs no co-edit.
