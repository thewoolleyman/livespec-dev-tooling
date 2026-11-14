---
proposal: homelab-worker-leaving-rejoining-and-pod-span-endpoint.md
decision: modify
revised_at: 2026-11-14T11:20:24Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2
---

## Decision and Rationale

Modified. The four bullets are added inside the existing Homelab worker nodes section as proposed, stating behaviour measured on macbook-m4-max-homelab-worker on 2026-11-13 and 2026-11-14 that the dispatch spec-change-tier screen refused as unstated: a not-Ready worker offers no quota and a gate Job lost to node failure is retried (livespec-dev-tooling-u45iv6); leaving a class removes everything its enrollment wrote and placement depends on enrollment (livespec-dev-tooling-ondpf6, -xgic4t, -qb3esy); a removed worker's pods are gone before its Node name registers again and a join proves its pod subnet (livespec-dev-tooling-fvxlzc); the pod-span endpoint follows the Node's pod subnet (livespec-dev-tooling-f2rft5). legacy-coordinator-agent graded livespec-dev-tooling#4661 PASS-WITH-FIXES and the fix is applied. The modification repairs a doctor finding on the first cut: load-bearing behaviour needs a scenario, so one scenario per bullet is added to scenarios.md, each stating only what its bullet states; and one BCP14 wording error is corrected.

## Modifications

Two changes relative to the proposal. (1) scenarios.md gains four scenarios directly after 'a worker that leaves mid-run loses no work and rejoins on its own', one per new bullet: 'a worker that is not Ready offers no quota, and a gate lost to its failure is retried'; 'a worker that leaves a workload class keeps nothing that class's enrollment wrote'; 'a removed worker rejoins only after its old pods are gone, and the join proves its pod subnet'; 'a worker's pod-span endpoint follows its pod subnet on a join and on a return'. The proposal added behaviour with no scenario, which the revise discipline treats as malformed. (2) In the bullet 'A departed worker leaves admission', 'no factory run MAY be placed on it' reads 'a factory run MUST NOT be placed on it', a BCP14 wording correction.

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
proposal_stem: homelab-worker-leaving-rejoining-and-pod-span-endpoint
content_digest: 79e02899a0ddd71bcd0fa5437c8fa4f3926a1e0d9db5ddd5c608c2c0e86eb3f9
