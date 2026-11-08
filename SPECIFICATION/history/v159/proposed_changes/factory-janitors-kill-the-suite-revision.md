---
proposal: factory-janitors-kill-the-suite.md
decision: accept
revised_at: 2026-11-08T07:25:31Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed. A suite-green stall kill today names only the window, so the two gmktec janitor kills of 2026-11-07 (bd-ib-ivm24w and bd-ib-t3bnab, both on passing trees) could not be told apart from a hung test, a long test or a silent tail, and their drained output was discarded. The Progress bound refusal now names elapsed seconds, completed out of collected tests (or that collection had not finished), the last completed test and its instant or that no test had completed, every still-running test with its elapsed time and worker, mid-suite versus post-last-test, and the drained output. These facts come from a per-test record rather than the -q stream, and a run that completes no test within the window is still ended with the same failed verdict. The stall window, its default, its variable and the optional ceiling are unchanged, and the existing stall scenario keeps its heading and text. Three scenarios state the new behaviour. The independent read-only sonnet review found no contradiction with the existing scenario, the section's intro or the generic gate stall rules. Implementation carriers: livespec-dev-tooling-h2i4u2 (the first two scenarios) and livespec-dev-tooling-6o3m6m (the no-test-completed scenario).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-08T07:24:06Z
verdict: NO BLOCKERS
proposal_stem: factory-janitors-kill-the-suite
content_digest: a98b1f109f4859679188150c3f9fbe19a51283d15af5e06ef28c5fb1e8a1ebb0
