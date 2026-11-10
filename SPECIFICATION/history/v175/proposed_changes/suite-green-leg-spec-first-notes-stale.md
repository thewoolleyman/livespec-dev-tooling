---
topic: suite-green-leg-spec-first-notes-stale
author: claude:dev-host-test-gate-load
created_at: 2026-11-09T19:20:29Z
---

## Proposal: Retire the shipped progress-bound and same-tree-reuse spec-first notes

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Remove the three spec-first notes in contracts.md §"Suite-green replay leg" that still describe the pre-t4rx4t / pre-z5fwwn leg (a fixed 2400 s total timeout, and a leg that always starts its own suite run). Both behaviours shipped, so the notes now contradict the code. No normative clause changes.

### Motivation

implement-test-performance's v170 doctor pass found the section intro and the Same-tree reuse bullet stale, and legacy-coordinator-agent routed the correction to plan dev-host-test-gate-load (epic livespec-dev-tooling-6vuiwe), which owns gate runtime. The Progress bound bullet's own closing note is stale for the same reason.

What shipped, read from master on 2026-11-09:
- Progress bound (livespec-dev-tooling-t4rx4t, closed 2026-11-02T21:35Z): livespec_dev_tooling/checks/_red_green_replay_suite_runner.py sets DEFAULT_STALL_SECONDS = 900 and STALL_ENV = "LIVESPEC_SUITE_GREEN_STALL_SECONDS" (lines 32-33). It keeps LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS only as the OPTIONAL CEILING_ENV (line 34), which applies only when that variable holds a positive value (suite_bound, lines 100-101). No DEFAULT_TIMEOUT_SECONDS = 2400 remains.
- Same-tree reuse (livespec-dev-tooling-z5fwwn, closed 2026-11-03T08:04Z): livespec_dev_tooling/checks/_red_green_replay_suite.py:229 calls reuse_pre_commit_evidence (_red_green_replay_pre_commit.py) for a full-suite scope. When the pre-commit evidence names the index tree, it records the TDD-Suite-Green-* trailers from that evidence, plus TDD-Suite-Green-Producer naming the run, and starts no suite run.

A spec-first note that outlives its change misleads the next reader: they will believe a 2400 s wall-clock bound still kills long suites, and that every commit re-runs the suite. This section is read during gate-stall diagnosis, where that wrong belief costs the most (livespec-dev-tooling-54usvh, 2026-11-09, was exactly such a diagnosis). The other spec-first notes in the section stay, because their owning items (5uobsl, 4scqti, svjqbe) are still open.

In-flight alignment: aligns with v170 (spec/revise-v170-4scqti-svjqbe, already on master), which last edited this section and left these three notes in place. No open spec pull request touches this section.

### Proposed Changes

In SPECIFICATION/contracts.md §"Suite-green replay leg", delete exactly these three sentences and change nothing else. No BCP14 clause, bullet, scenario or H2 heading changes, so tests/heading-coverage.json and scenarios.md are not touched.

1. Section intro: delete the final sentence of the intro paragraph, verbatim:

   > The progress-bound and same-tree-reuse bullets are spec-first: as of ratification the shipped leg bounds each run by a fixed total timeout (default 2400 s, `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS`) and always starts its own suite run.

   The intro paragraph then ends with "...and when an earlier run on the same tree stands in for it."

2. **Progress bound.** bullet: delete its closing spec-first note, verbatim:

   > This bullet is spec-first: the shipped leg still bounds each run by a fixed total timeout, `DEFAULT_TIMEOUT_SECONDS = 2400`, overridable by `LIVESPEC_SUITE_GREEN_TIMEOUT_SECONDS`, and it ends a run that is still printing output when that timeout expires. Work item livespec-dev-tooling-t4rx4t owns the change.

   The bullet then ends with "...so a slow run and a fast run of the same green suite record the same checksum."

3. **Same-tree reuse.** bullet: delete its closing spec-first note, verbatim:

   > This bullet is spec-first: the shipped leg always starts its own suite run. Work item livespec-dev-tooling-z5fwwn owns the change.

   The bullet then ends with "A reused result MUST NOT turn a failing or absent run into a green one."

Keep, unchanged, the spec-first notes on the **Behaviour-preserving claim** (livespec-dev-tooling-5uobsl), **Local-aggregate evidence entry point** (livespec-dev-tooling-4scqti), **Affected-tests scope in a factory sandbox** (livespec-dev-tooling-svjqbe) and **Outcome telemetry** (livespec-dev-tooling-4scqti) bullets: their owning work items are still open, so those notes are still true.
