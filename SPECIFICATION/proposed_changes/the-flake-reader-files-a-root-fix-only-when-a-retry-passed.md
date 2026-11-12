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

Narrow the host-side flake reader in the "Untouched-test retry" bullet. It files one root-fix work item only for a node id whose `tmp/flake-retries/` record has the final outcome `passed`. A record with any other final outcome, such as `failed` (every attempt failed), produces no root-fix item. Rename and tighten the existing scenario so its records are passed retries, and add one scenario for a record whose every attempt failed.

### Motivation

A root-fix item exists to remove a flake: a test that failed and then passed with nothing changed. A test that fails every attempt is not a flake. A flake is a test whose outcome changes between attempts on the same code, and only a later passing attempt shows that. A failure that repeats on every attempt is consistent with a deterministic defect, and it already fails its run, so whoever owns that red owns its fix. This proposal narrows the maintainer rulings on livespec-dev-tooling-6tgd2z of 2026-11-02 18:38:21Z ("Every flake MUST be immediately assigned to a plan to fix as a priority") and 18:39:54Z, whose recorded rule reads "Every retried failure still gets an owning plan's root-fix item at once". The maintainer's words name flakes. The recorded rule's "every retried failure" also covers a failure that repeats on every attempt, which is not a flake. This proposal keeps the root-fix duty for every flake and drops it only for that case. Today the reader files a root-fix item for every retried node id, whatever its final outcome. Measured 2026-11-12: four `flake-retries` artifacts in livespec-dev-tooling (13962429913, 13965745127, 13965201724, 13965112998: master 6201dcdb2 and three spec branches) each recorded the same two `tests/spec/test_homelab_worker_runner_set.py` tests failing all 4 attempts. That was master's deterministic WARM_CACHE_DIR red, whose fix is livespec-dev-tooling#4357. The reader filed livespec-dev-tooling-gdm4xc, routed `ready` and dispatchable, and livespec-dev-tooling-wibxsp for it. Both were closed by hand as misfiled, because a factory run on either would have duplicated and raced the owner's fix. Until this lands, every deterministic red on a branch or master files root-fix items that must be swept by hand. The reader is shared, so the narrowing reaches every fleet repository that loads the flake-retry plugin and runs the reader. Owner: plan fleet-flaky-tests (epic livespec-dev-tooling-zwveqp); the coordinator endorsed this proposal on 2026-11-12. Once this is ratified, `.ai/coordinator-duties.md` §2 needs a follow-up edit. Its sentence "every retried failure gets a root-fix item at once" should read "every retried failure whose retry passed gets a root-fix item at once; one that failed every attempt goes to the owner of that red".

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, bullet "Untouched-test retry", replace the sentence "A host-side reader of those records MUST file one root-fix work item per node id at once, and none for a node id that already has an open root-fix item." with:

"A host-side reader of those records MUST file one root-fix work item at once for each node id whose record's final outcome is `passed`, meaning a later attempt passed after an earlier one failed, and none for a node id that already has an open root-fix item. A record with any other final outcome MUST NOT file a root-fix item and is accounted for without a store write. A record whose final outcome is `failed`, because every attempt failed, is not a flake."

Every later sentence of the bullet that speaks of the items the reader files (capture path, intake routing, the non-zero exit on a refused routing, routing again on a later pass, and no second item while one is open) applies unchanged to the items this narrowed sentence files.

In `SPECIFICATION/scenarios.md`, rename the heading `## Scenario: every retried failure files one root-fix work item` to `## Scenario: every flaky retry that passed files one root-fix work item` and replace its body with:

"Given `tmp/flake-retries/` holds records for two node ids, each with final outcome `passed`, one of which already has an open root-fix work item

When the host-side flake reader runs

Then it MUST file exactly one root-fix work item, for the node id that had none"

The revise that accepts this proposal MUST re-key that scenario's `tests/heading-coverage.json` row (currently at line 2238, owned by livespec-dev-tooling-o4j3kg) to the new heading in the revise commit. The fixture of o4j3kg's owed test MUST use records whose final outcome is `passed`.

Add a new scenario directly after it:

"## Scenario: a retry whose every attempt failed files no root-fix work item

Given `tmp/flake-retries/` holds a record whose every attempt failed, so its final outcome is `failed`, for a node id that has no open root-fix work item

And a record whose final outcome is `passed`, for a second node id that has no open root-fix work item

When the host-side flake reader runs

Then it MUST file exactly one root-fix work item, for the node id whose final outcome is `passed`

And it MUST NOT file a root-fix work item for the node id whose final outcome is `failed`

And the reader's pass MUST exit zero"

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the revise commit, with a TODO row naming the integration tier and livespec-dev-tooling-o4j3kg as the owning work item. If o4j3kg has closed by then, the revise files an item for the reader's integration test and names that item instead. The revise MUST also regenerate the debt register.
