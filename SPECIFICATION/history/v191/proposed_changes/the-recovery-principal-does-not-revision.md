---
proposal: the-recovery-principal-does-not.md
decision: accept
revised_at: 2026-11-11T11:15:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accept as filed. Follow-up (b) of plan expedited-incident-hardening (epic livespec-dev-tooling-dh3hub), work item livespec-dev-tooling-52die6. thhgeg cycle B (2026-11-10T21:19:32Z on livespec-dev-tooling-thhgeg) showed a restart between the principal's prepared publication and the ref update leaves the action pending until an operator sends POST /reconcile with retry_publish true, while master stays red. The ratified §"Expedited incident execution" requires immutable intent and post-timeout receipt recovery but not completion on restart. The paragraph makes the released controller resume every pending action whose principal reports an unresolved publication attempt, on each service start and later due sweep pass, as the same exactly-once publication the explicit retry reaches: forge facts first, only the one recorded commit through the expected-head compare-and-swap, head movement handled by the preceding paragraph, persisted back-off, terminal state and retry bounds honoured, and principal calls made outside the repository fence so first-failure recovery of another action is never delayed. One scenario covers it, with a spec-first TODO coverage row owned by livespec-dev-tooling-52die6. The anchors it names are unchanged on master at v190, so the text applies as written.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T11:14:58Z
verdict: NO BLOCKERS
proposal_stem: the-recovery-principal-does-not
content_digest: b9d50c0ba9e6b74039baf0d5e5384aeade8e58325e9300b9fe0d70a3d8a58a9a
