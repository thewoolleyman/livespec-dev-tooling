---
topic: per-pr-fleet-sweep-scope
author: claude-opus-5-5
created_at: 2026-11-16T02:37:07Z
---

## Proposal: Per-PR fleet sweep is scoped to the running member unless the change touches fleet code

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

livespec-dev-tooling's pull_request and merge_group runs of check-fleet-conformance --member-ci evaluate every row of the running member, and every manifest member's rows only when the change touches the fleet checker's own code or its dependency set. master push runs, the scheduled sweep and the release fan-out preflight keep the full every-member sweep.

### Motivation

Incident livespec-dev-tooling-zq2i4c: concurrent PR and merge-group sweeps on the shared org App installation 182016479 hit GitHub's secondary rate limit and made rows blind, so the merge queue merged nothing. FIX 2 (f1b5eade2) cut one sweep from 521 calls (2026-11-15) to about 50 (2026-11-16 02:34Z measurement), but every PR and merge group still sweeps every member, although under --member-ci only the running member's violations move the exit code. The current text requires the CI job to assert every member, and contracts.md:949 relies on per-PR CI to surface some findings the fan-out preflight passes over, so narrowing the PR run is a ratification question, not a conformance fix. The master push run keeps that surfacing duty, because every merge lands as a master push. A result cache keyed on member head shas was considered and rejected: state rows (compat-pin-currency reads releases/latest and its published_at, plus rulesets, variables and app installation) change with no member head changing, so the cache would serve stale verdicts. Filed at throughput-plans-coordinator's ruling (2026-11-16 02:4xZ) under work item livespec-dev-tooling-n35tv5.

### Proposed Changes

Add the following paragraph to contracts.md §"Fleet surface — central conformance and reconcile", directly after the **Assert mode** bullet:

> **Per-PR scope.** A `check-fleet-conformance --member-ci` run in livespec-dev-tooling's own CI whose triggering event is `pull_request` or `merge_group` MUST evaluate every obligation row of the running member. It MUST evaluate every manifest member's rows only when the change under test touches a path that can alter a verdict about another member: any file under `livespec_dev_tooling/fleet/`, `uv.lock`, or `pyproject.toml`. Otherwise it MUST skip the other members' rows, and it MUST log one line naming the event, the skipped members and the reason. A `push` run on `master`, the scheduled `fleet-conformance.yml` sweep and the release fan-out preflight MUST evaluate every member, whatever changed. The per-PR scope MUST NOT change any row's severity, MUST NOT drop any row of the running member, and MUST NOT be settable by a lever, environment variable or label.

Amend contracts.md:949: the sentence that ends "that finding is surfaced by the scheduled central sweep and livespec-dev-tooling's per-PR CI rather than by this dispatch" becomes "that finding is surfaced by the scheduled central sweep and by livespec-dev-tooling's `master` push CI rather than by this dispatch".

Add to scenarios.md:

```gherkin
## Scenario: a livespec-dev-tooling pull request that touches no fleet code is swept for its own member only
Given livespec-dev-tooling's CI runs check-fleet-conformance --member-ci on a pull_request event
And the pull request changes no file under livespec_dev_tooling/fleet/, uv.lock or pyproject.toml
When the sweep runs
Then it evaluates every obligation row of livespec-dev-tooling
And it reads no other member's files or state
And it logs one line naming the event and the skipped members

Given the same CI runs on a pull_request event whose change touches livespec_dev_tooling/fleet/contract.py
When the sweep runs
Then it evaluates every manifest member's rows
```

Co-edit `tests/heading-coverage.json` with the new scenario heading at revise time.
