---
proposal: homelab-worker-lend-idle-share.md
decision: accept
revised_at: 2026-11-09T16:02:18Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:homelab-k8s-worker-nodes
---

## Decision and Rationale

Accepted as written under delegated mode. It implements the 2026-11-09 08:38Z ruling relayed by legacy-coordinator-agent on plan epic livespec-dev-tooling-ko26ez: a workload share with no workload enrolled is lent to the enrolled classes, never left idle. The amendment changes only the default split in the Derived per-class capacity bullet and its scenario. The churn-slot rule, the cohort-quota reconciliation and the no-pinned-capacity test rule are unchanged. macbook-m4-max-homelab-worker has run these values (2 churn slots, a 6000m gate share) since 09:16Z, so the ratified text now matches live state. The independent read-only reviewer (sonnet) found no blockers on the exact bytes.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T16:01:28Z
verdict: NO BLOCKERS
proposal_stem: homelab-worker-lend-idle-share
content_digest: 73cdb2f17fc158205fa304e5ce707eca12573891713acef6a0f939137b7fd4e3
