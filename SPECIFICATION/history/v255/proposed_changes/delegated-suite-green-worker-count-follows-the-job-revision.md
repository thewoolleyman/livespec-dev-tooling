---
proposal: delegated-suite-green-worker-count-follows-the-job.md
decision: accept
revised_at: 2026-11-19T20:21:41Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: gate-job-resources-session
---

## Decision and Rationale

Accepted as filed. A delegated suite-green replay leg took its pytest -n from the committing host's CPU count (max(1, visible_cpus // 4); 16 on the 64-CPU dev host) while the Job runs in an 8Gi container; measured OOM kills at -n 16 (gate-livespec-dev-tooling-xgf8d: 8,589,946,880 bytes, oom_kill 5) against 4.12 GiB and no kills at -n 4. The amendment ties the delegated leg's worker count to the Job's own size (LIVESPEC_TEST_PARALLELISM on the committing host, else the declared gate_parallelism, else 4) and adds one scenario with a heading-coverage row owned by livespec-dev-tooling-ovzmcn. No design-record contradiction. Independent sonnet review: NO BLOCKERS on digest 569b9c8be36e8aabbe08ea2253d36687aba58460748d6c566ce030a5f338a7e2. Its three non-blocking notes are carried to ovzmcn rather than reworded here: the sentence on a locally run leg should not be read to exclude an explicit LIVESPEC_TEST_PARALLELISM; the test_nprocs override and LIVESPEC_CI_LANE=hosted are pre-existing inputs the bullet does not name; the implementation must move worker selection after the local-versus-delegated decision.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-19T20:19:45Z
verdict: NO BLOCKERS
proposal_stem: delegated-suite-green-worker-count-follows-the-job
content_digest: 569b9c8be36e8aabbe08ea2253d36687aba58460748d6c566ce030a5f338a7e2
