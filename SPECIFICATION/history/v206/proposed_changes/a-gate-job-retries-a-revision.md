---
proposal: a-gate-job-retries-a.md
decision: modify
revised_at: 2026-11-12T18:42:32Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The Forge reads bullet and its two scenarios are accepted as graded by legacy-coordinator-agent on livespec-dev-tooling#4336 (PASS with one fix, already in the proposal: an anonymous 401 counts as transient even when an absent or private repository caused it), for work item livespec-dev-tooling-yjcyay under plan gate-job-resources. It is the stop-the-line answer to the anonymous github.com 401 class that failed delegated gates from about 13:20Z on 2026-11-12. A pre-merge doctor pass walked the text through forge-retry.sh, render-gate-job.sh and mint-private-sibling-token.sh on branch chore/gate-forge-retry (livespec-dev-tooling#4352) and found no clause the code cannot satisfy. The independent ratification review (sonnet) returned NO BLOCKERS on the final bytes at 2026-11-12T16:56:02Z. No design record is contradicted: the text adds a bounded retry beside the existing Cross-repository siblings and Verdict bullets, and keeps the rule that no new or standing credential is introduced.

## Modifications

Relative to the proposal: (1) the Forge reads bullet gains one passage covering the pushing host's mint of the private-sibling installation token. The mint MUST retry a transient refusal (an HTTP 429 or 5xx answer, or a transport failure) within the same kind of bound, log each attempt's HTTP status and never the response body, and fail at once on any other refusal; a mint still failing once the bound is spent refuses the push as a missing verdict, as Cross-repository siblings requires. (2) A third scenario states that behaviour, as authoring discipline (i) requires of a behaviour clause. Basis: at 2026-11-12T16:34Z a pre-push gate in livespec-orchestrator-beads-fabro failed on 'mint-private-sibling-token ... error: 500' and passed on a re-run, measured by spec-implementation-lockstep. legacy-coordinator-agent endorsed folding it into this cut rather than spending a separate revise cycle on one sentence.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T16:56:02Z
verdict: NO BLOCKERS
proposal_stem: a-gate-job-retries-a
content_digest: b8868f6f94c9baef588cfa6095f79d088a2ebddffdeb06a499be1cf827bf955c
