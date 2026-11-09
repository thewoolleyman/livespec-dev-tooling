---
topic: incident-recovery-target-branch
author: claude:expedited-incident-response-flag
created_at: 2026-11-09T19:49:39Z
---

## Proposal: The incident recovery principal targets a configured branch, master by default

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" so the recovery principal builds and merges its inverse against the current head of a CONFIGURED target branch rather than a fixed `master`. The controller's installation configuration MAY name the target branch; when it names none the target MUST be `master`, the production default. A non-master branch MAY be named only to prove or drill recovery against a scratch branch, and an installation so configured recovers only that branch. Add one scenario stating the scratch-branch behaviour, including the moved-head overlap that becomes an owned rollback-conflict.

### Motivation

Work item livespec-dev-tooling-thhgeg (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm) carries the moved-head overlap bullet that legacy-coordinator-agent moved off livespec-dev-tooling-7536jf on 2026-11-09. The released principal hard-codes `_BRANCH = "master"` (livespec_dev_tooling/incident_recovery_principal.py), so its 2026-11-09 host capture on vps (v1.188.1) could not exercise the moved-head overlap path without a deliberate red master, and the 2026-11-07 forge rehearsal could drive only the effects layer, not the principal service, against a scratch branch. thhgeg's Definition of Done makes the target branch configurable (default master) and proves the overlap against a scratch branch on the real forge. The ratified clause says the principal constructs its inverse "against current master", so the factory's spec-stated judgement would class thhgeg as spec-change tier: its Definition of Done needs behaviour the spec does not state. Coordinator ruling (session 9fe54cde, 2026-11-09T19:38:30Z): file a pre-emptive propose-change for a configured recovery target branch allowed for proof, with master the production default. Ordinary non-incident policy and every master-facing obligation are unchanged: with no configured branch the behaviour is exactly today's.

### Proposed Changes

1. In SPECIFICATION/contracts.md §"Expedited incident execution", in the rollback paragraph, replace the sentence

> The recovery principal MUST construct its inverse against current master using expected-head compare-and-swap, preserving later unrelated edits, recomputing on head movement and recording an owned overlap conflict rather than overwriting files.

with:

> The recovery principal MUST construct its inverse against the current head of its target branch using expected-head compare-and-swap, preserving later unrelated edits, recomputing on head movement and recording an owned overlap conflict rather than overwriting files. The target branch is configured: the installation configuration of the independently hosted released controller that runs the principal MAY name it, and when the configuration names none the target branch MUST be `master`, the production default. An installation MAY name a branch other than `master` only to prove or drill recovery against a scratch branch. A principal so configured MUST publish, merge and record conflicts only on that branch, MUST refuse any request whose repository or branch differs from its configured pair rather than falling back to `master`, and MUST NOT be counted as recovery capability for `master`.

The rest of the paragraph (the narrow recovery capability merging the validated inverse with no local tests, factory or pre-merge CI waits; no toggling of ordinary protection; forge-policy proof before activation; unchanged ordinary non-incident reconciler policy) is unchanged. The existing "## Scenario: an incident revert preserves later changes without waiting for CI" is unchanged and continues to describe the default `master` target.

2. In SPECIFICATION/scenarios.md, add after "## Scenario: an incident revert preserves later changes without waiting for CI":

## Scenario: an incident recovery principal configured for a scratch branch recovers only that branch

```gherkin
Given a recovery principal whose released controller's installation configuration names a non-master scratch branch as its target branch
And an authorized recovery action for an incident patch landed on that scratch branch
And the scratch branch's head has moved since the action was authorized, through a later change that overlaps the incident patch
When the principal publishes the action's inverse
Then it MUST recompute the inverse against the scratch branch's current head
And it MUST record the genuine overlap as an owned rollback-conflict instead of a merge
And it MUST NOT read or move master
And a request naming any other branch MUST be refused rather than applied to master
And an installation configuration that names no target branch MUST target master.
```

3. In tests/heading-coverage.json, add an entry for the new scenario heading (spec_file scenarios.md) with test "TODO", work_item livespec-dev-tooling-thhgeg, and a reason naming the tier: "A real test at the integration tier or above is owed for this heading: the fake-forge recovery principal tests must drive a principal configured for a non-master branch through a moved-head overlap; livespec-dev-tooling-thhgeg owns it." Regenerate tests/heading-coverage-debt.json with `just generate-heading-coverage-debt-register`.
