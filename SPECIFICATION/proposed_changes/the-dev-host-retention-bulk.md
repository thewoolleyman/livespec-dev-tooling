---
topic: the-dev-host-retention-bulk
author: claude-opus-5-5
created_at: 2026-11-12T05:20:56Z
---

## Proposal: The dev host bulk-dump cap restores the cap in one bounded pass

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Extend the bulk-dump bullet of §"Dev host disk retention": the leg measures the directory and lists its files a fixed number of times per run, however many files it removes, keeping a running total. A file that vanishes or cannot be removed is logged and skipped without aborting the run.

### Motivation

Measured on vmi3006760 by the dev-host-disk-retention plan (livespec-dev-tooling-qgwxo4). The implementation item is livespec-dev-tooling-ng6ka4; the dispatch-stage spec-change tier refused it (verdict partial, linked topic the-dev-host-retention-bulk) because the section does not state the bounded walk.

- Today the leg runs `du -sb` on the whole directory and then, for EVERY file it removes, a full `find` plus `sort` and another `du -sb`. A pass that removes N files walks the tree about 2N times.
- On the 2026-11-11 23:27Z scheduled run, with the directory UNDER its cap (9.55 GiB of 20 GiB, 1,665,186 files), the single initial walk took 13m43s of a 19m27s run, against the unit's 30-min timeout. A pass that had to remove even one file would start a second walk and run past the timeout, so on a tree that size the leg cannot restore the cap that the section says it MUST hold.
- The bulk-dump directory now also holds legacy-dispatcher-agent's `fabro events` captures (up to about 78 MB each), so the cap is the only bound on them.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Dev host disk retention", in the bullet that begins "It MUST hold the bulk-dump directory, a role variable,", insert after its first sentence (the one ending "by removing its oldest files first."):

> One run MUST measure the directory and list its files a bounded number of times, independent of how many files it removes: it MUST keep a running total, reduce it by each removed file's size, and stop removing once the total is at or below the cap. A file that vanishes or cannot be removed during the pass MUST be logged and skipped, and MUST NOT abort the pass or the run's remaining steps.
