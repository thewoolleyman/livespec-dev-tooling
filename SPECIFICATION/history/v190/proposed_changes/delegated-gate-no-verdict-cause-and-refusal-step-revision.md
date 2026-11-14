---
proposal: delegated-gate-no-verdict-cause-and-refusal-step.md
decision: accept
revised_at: 2026-11-11T10:21:21Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept both proposals in the file as written. They are consistent with each other and with the ratified outcome vocabulary: they keep the three outcome words, add two no-verdict-only attributes (cause and refusal step), and narrow the required trigger without hiding any event from the data. The second proposal also repairs a standing contradiction: the existing no-verdict scenario required a Job name on a run that never submitted a Job, against the never-guessed rule its own covering test already recorded. Both edits are stated as BCP14 clauses with Gherkin scenarios, and the new scenario heading gets a spec-first heading-coverage row owned by the implementing item livespec-dev-tooling-donph5. Measured motivation: 12 no-verdict outcomes in 7 days, at least two caused by the pushing client itself (gate runs 20261107T170438Z-2028504 and 20261111T002432Z-2338868), and no Job name on any of the 12 spans. The tests/heading-coverage.json row is co-edited in the same commit, outside resulting_files, as v189 did.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T10:21:14Z
verdict: NO BLOCKERS
proposal_stem: delegated-gate-no-verdict-cause-and-refusal-step
content_digest: cc7d98566f588a2d2414d90e6588a2aa196c404f322bda4a087c834d2666bf1c
