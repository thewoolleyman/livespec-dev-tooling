---
proposal: evacuation-needs-an-always-on-node-and-three-wording-fixes.md
decision: accept
revised_at: 2026-11-14T11:20:22Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2
---

## Decision and Rationale

Accepted as written. All four proposals are follow-ups to v215 that legacy-coordinator-agent ruled on 2026-11-13 and graded PASS at livespec-dev-tooling#4642 (e21891db5): the evacuation play refuses unless another always-on node that is Ready and not cordoned can take the listener pods it would delete (a new scenario states it; the play change is owned by livespec-dev-tooling-w66r34), the runner version pin rule names the homelab worker values directory (owned by livespec-dev-tooling-cpyspi), the Scope paragraph of Consent-gated pool-node disruption names every disruption the section governs, and the Cluster controllers telemetry paragraph calls a listener an AutoscalingListener. The first two are spec-first until their owning items land. The new scenario heading's heading-coverage row is co-edited in this revise's commit.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T11:19:40Z
verdict: NO BLOCKERS
proposal_stem: evacuation-needs-an-always-on-node-and-three-wording-fixes
content_digest: ef6d5f4cfa5fc3522ddfb6b185a634a487e104fa7164a6aa8548c716d7bf87e3
