---
topic: the-flake-reader-files-a-root-fix-only-when-a-retry-passed
author: claude-opus-5-5 (seat:fleet-flaky-tests)
created_at: 2026-11-12T17:13:44Z
---

## Proposal: The flake reader files a root-fix item only for a retry whose final outcome is passed

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Narrow the host-side flake reader in the "Untouched-test retry" bullet. It files one root-fix work item only for a node id whose `tmp/flake-retries/` record has the final outcome `passed`. A record whose final outcome is `failed` (every attempt failed) produces no root-fix item. Tighten the existing scenario so its records are passed retries, and add one scenario for a record whose every attempt failed.

### Motivation

A root-fix item exists to remove a flake: a test that failed and then passed with nothing changed. A test that fails every attempt is not a flake. It is a consistent failure that already fails its run, and whoever owns that red owns its fix. Today the reader files a root-fix item for every retried node id, whatever its final outcome. Measured 2026-11-12: four `flake-retries` artifacts in livespec-dev-tooling (13962429913, 13965745127, 13965201724, 13965112998: master 6201dcdb2 and three spec branches) each recorded the same two `tests/spec/test_homelab_worker_runner_set.py` tests failing all 4 attempts. That was master's deterministic WARM_CACHE_DIR red, whose fix is livespec-dev-tooling#4357. The reader filed livespec-dev-tooling-gdm4xc, routed `ready` and dispatchable, and livespec-dev-tooling-wibxsp for it. Both were closed by hand as misfiled, because a factory run on either would have duplicated and raced the owner's fix. Until this lands, every deterministic red on a branch or master files root-fix items that must be swept by hand. The reader is shared, so the narrowing reaches every fleet repository that loads the flake-retry plugin and runs the reader. Owner: plan fleet-flaky-tests (epic livespec-dev-tooling-zwveqp); the coordinator endorsed this proposal on 2026-11-12.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, bullet "Untouched-test retry", replace the sentence "A host-side reader of those records MUST file one root-fix work item per node id at once, and none for a node id that already has an open root-fix item." with:

"A host-side reader of those records MUST file one root-fix work item at once for each node id whose record's final outcome is `passed`, meaning a later attempt passed after an earlier one failed, and none for a node id that already has an open root-fix item. A record whose final outcome is `failed`, because every attempt failed, is not a flake: the reader MUST NOT file a root-fix item for it, and MUST treat that record as accounted for without writing to the work-item store."

Every later sentence of the bullet that speaks of the items the reader files (capture path, intake routing, the non-zero exit on a refused routing, routing again on a later pass, and no second item while one is open) applies unchanged to the items this narrowed sentence files.

In `SPECIFICATION/scenarios.md`, keep the heading `## Scenario: every retried failure files one root-fix work item` and replace its body with:

"Given `tmp/flake-retries/` holds records for two node ids, each with final outcome `passed`, one of which already has an open root-fix work item

When the host-side flake reader runs

Then it MUST file exactly one root-fix work item, for the node id that had none"

Add a new scenario directly after it:

"## Scenario: a retry whose every attempt failed files no root-fix work item

Given `tmp/flake-retries/` holds a record whose final outcome is `failed` after 4 attempts, for a node id that has no open root-fix work item

And a record whose final outcome is `passed`, for a second node id that has no open root-fix work item

When the host-side flake reader runs

Then it MUST file exactly one root-fix work item, for the node id whose final outcome is `passed`

And it MUST NOT file a root-fix work item for the node id whose final outcome is `failed`

And the reader's pass MUST exit zero"

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the revise commit, with a TODO row naming the integration tier and an owning work item, and MUST regenerate the debt register.
