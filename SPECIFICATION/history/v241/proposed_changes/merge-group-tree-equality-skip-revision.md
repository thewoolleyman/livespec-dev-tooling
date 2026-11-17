---
proposal: merge-group-tree-equality-skip.md
decision: accept
revised_at: 2026-11-17T00:27:40Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5
---

## Decision and Rationale

Accepted as written, unmodified (ratified as a real CI contract; safety bounds kept, nothing widened). Implementation comparison against livespec-dev-tooling#4881 merge_group_skip.py: (1) one-entry is derived from group head == first queue entry head (cut == [0]), equivalent to or stricter than 'exactly one entry'; (2) the incident-omitted set is read from the head's ci-green step 'Report members omitted-by-incident-policy' being skipped, not from incident-ci's omitted output, fail-closed (any other value or missing step gives skip=false) and no less safe, but coupled to a step name; (3) the implementation additionally requires the pull request's base ref to equal the group's branch, which only narrows. No divergence makes the implementation less safe than the text. Adds one scenario heading; heading-coverage row owned by livespec-dev-tooling-ymog6r with the debt register regenerated in the same commit.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-17T00:27:08Z
verdict: NO BLOCKERS
proposal_stem: merge-group-tree-equality-skip
content_digest: 5ca75eb64c6a2d561c1dcdb3298717b590bd9e5bc7230232d2d6dea28c772c48
