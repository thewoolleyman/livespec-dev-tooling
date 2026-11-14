---
proposal: gate-fetch-tree-git-object-seed.md
decision: modify
revised_at: 2026-11-11T06:25:57Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified by the ci-cache-optimization seat (plan epic livespec-dev-tooling-7zozck), which owns the carrier livespec-dev-tooling-zbu7jf. legacy-coordinator-agent ruled the seeded gate fetch-tree a spec change, graded the proposal PASS (livespec-dev-tooling#4096, 4a847b2c) and assigned this pass v189, after v188. A first accept-unmodified draft passed independent review, but a pre-commit LLM doctor pass walked it through the live gate-job-template.yaml, the local-path provisioner and the warm-cache populator. It found that an objects-only seed copy would let the seeded fetch ship with no effect, that scenario 2 asserted a MUST the clause lacked, that gate Jobs cannot read the fleet kill switch, and that the pruning guard was not implementable. Those findings are folded in as M1-M7. A doctor recheck of the modified text found them resolved and nothing unworkable. Recorded on zbu7jf, not in the spec: the seed is not live on master (cc76b2c9 was reverted in 28b206f5, so dciyg5 and qyrmwe re-land it first); provisioner discrimination of gate volumes by namespace and claim name; and hp-xubuntu's gate-volume directory is ext4 with no reflink, so hp gains nothing until the deferred full-node profile change, while the reflink-capable M4 worker (88 s fetch-tree) is the node that benefits. Both scenarios are registered as spec-first TODO rows in tests/heading-coverage.json owned by livespec-dev-tooling-zbu7jf.

## Modifications

M1 (NFR Tiers): each gate-volume seed copy MUST be a git repository holding the seed's objects plus the repository's default-branch and tag refs; git narrows a fetch only against refs beside an alternate's objects (measured: objects-only alternate 123/123 objects received, refs-carrying copy 3/123). M2 (NFR Tiers): the gate-copy pruning guard becomes 'MUST NOT be pruned while a copy from it into a gate volume may still be in progress; a retention window longer than the provisioner's copy timeout satisfies this', because the populator cannot see pod binding and a finished reflink copy does not depend on its generation. M3 (NFR Trust by construction): 'default branch' becomes 'default branch and tags', matching Tiers. M4 (NFR rebuild recipe): 'A job there therefore starts with no seeded tree' becomes 'A runner job there ...', removing the contradiction with the new gate-volume sentence. M5 (contracts Seeded tree fetch): the copy carries refs and the alternate names its object directory; new MUST that a fetch with the alternate transfers fewer objects than the unseeded fetch when the copy's refs reach an ancestor of the base; the connectivity check binds a Job that named the alternate; the gate Job reads the fleet kill switch from the cluster before its fetch, not from the pushing host's environment; the 'including' list adds Delegated commit-time replay test runs. M6 (scenario 1): retitled to a node with no ci-workvols tier seeding only its reflink-capable gate volumes; the Given drops 'not routed', since every delegated-gate repository is routed; a reflink step, a no-reflink step and refs on the copy are added; pruning follows M2. M7 (scenario 2): the Given carries refs and an ancestry condition, the When names the alternate, the Then becomes a gradeable 'MUST transfer fewer objects', and the kill switch is read from the cluster.

## Resulting Changes

- non-functional-requirements.md
- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T06:23:57Z
verdict: NO BLOCKERS
proposal_stem: gate-fetch-tree-git-object-seed
content_digest: 819e555d9fcb7e83ac293b1a6d3fd86749b52082bf6f502c794c10482ac59324
