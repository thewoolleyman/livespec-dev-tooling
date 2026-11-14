---
proposal: the-scratch-incident-observer-shares.md
decision: modify
revised_at: 2026-11-14T19:53:05Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified (livespec-dev-tooling-whzwtw), applying the two notes from legacy-coordinator-agent's PASS grade of livespec-dev-tooling#4439 (3e750bae, 2026-11-14 ~12:3xZ). A scratch observer installation gets its own Python environment and release, named by its own role variable defaulting to production's pin, so a release can be proved on scratch before production rolls; every existing scratch guarantee is kept, a scratch apply or teardown never writes production's environment or release, and the preflight compares every scratch path, the environment included, against the production set.

## Modifications

Two wording changes from the coordinator's grade of livespec-dev-tooling#4439, no change of behaviour: (1) Edit 2's last sentence, which read 'Production's home and configuration directory remain parents a scratch path MAY sit inside, never be or contain.' and so appeared to contradict the refusal sentence before it (the production set includes /opt/livespec-incident), is folded into that refusal as an explicit 'except': a scratch path MAY sit inside production's home directory or configuration directory, and still MUST NOT be or contain either, or be, contain or sit inside any other production path. (2) The new scenario's '## Scenario:' heading is placed outside its gherkin fence, matching the surrounding scenarios, so its heading-coverage row matches.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T19:50:56Z
verdict: NO BLOCKERS
proposal_stem: the-scratch-incident-observer-shares
content_digest: 9326a9849413a9bf12705fe08a8e364a5da274444e3afa634c33ac22eb48f4ff
