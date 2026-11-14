---
topic: replay-job-size-spec-first-note-shipped
author: claude-opus-5-5
created_at: 2026-11-11T17:38:54Z
---

## Proposal: The Replay Job size spec-first note names what has shipped and who owns the scenario tests

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The closing sentence of contracts.md §"Delegated commit-time replay test runs" **Replay Job size** still reads "This bullet is spec-first: as of filing, every replay Job requests CPU 5 and memory `6Gi`, and the client reads every terminal state other than Complete as a failed run." That stopped being true when livespec-dev-tooling-lfkkaf merged. This proposal replaces it with a note naming the work item and pull request that implement the bullet, and the work item that owns its scenario-tier tests.

### Motivation

livespec-dev-tooling-lfkkaf merged as livespec-dev-tooling#4178 (44c857475) on 2026-11-11. One-file Red and Green replay Jobs now request CPU 2, memory 3Gi and LIVESPEC_TEST_PARALLELISM 1 whatever the repository declares, a suite-green leg keeps the declared size, and a one-file leg whose Job ended OOMKilled or Evicted reads as an absent verdict. A spec-first note that says the opposite misleads the next reader and the next revise about what is still owed. The two Replay Job size scenarios still owe tests.consumer-tier tests, which livespec-dev-tooling-4g7als owns (their heading-coverage rows were repointed to it in livespec-dev-tooling#4181). legacy-coordinator-agent asked for this follow-up when grading #4178.

### Proposed Changes

In SPECIFICATION/contracts.md §"Delegated commit-time replay test runs", bullet **Replay Job size**, replace the sentence "This bullet is spec-first: as of filing, every replay Job requests CPU 5 and memory `6Gi`, and the client reads every terminal state other than Complete as a failed run." with: "livespec-dev-tooling-lfkkaf implements this bullet (livespec-dev-tooling#4178). Work item livespec-dev-tooling-4g7als owns the consumer-tier tests of its two scenarios." No other text in the bullet changes, and no heading is added, renamed or removed.
