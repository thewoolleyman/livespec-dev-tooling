---
proposal: incident-recovery-target-branch.md
decision: accept
revised_at: 2026-11-09T22:07:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:expedited-incident-response-flag
---

## Decision and Rationale

Accepted as filed. The ratified rollback clause in contracts.md §"Expedited incident execution" fixed the recovery principal's inverse to current master, so livespec-dev-tooling-thhgeg's Definition of Done (a configured target branch, master by default, proven through a moved-head overlap on a scratch branch on the real forge) stated behaviour the spec did not, and the dispatcher's spec-stated judgement would hold it as spec-change tier. The amended clause keeps master as the production default with no configured branch, admits a non-master branch only to prove or drill recovery, confines such an installation to its configured repository/branch pair, refuses rather than falls back to master, and never counts it as recovery capability for master, so every master-facing obligation is unchanged. One scenario states the scratch-branch behaviour. Pre-emptive filing ruled by legacy-coordinator-agent (session 9fe54cde, 2026-11-09T19:38:30Z). Independent review (sonnet, 2026-11-09T21:18:10Z) reported NO BLOCKERS over the exact bytes; its notes (the new scenario is slightly stricter than the clause in forbidding a scratch-configured principal to read master, and the existing incident-revert scenario keeps its narrower default-master wording) are non-blocking. The heading-coverage co-edit (spec-first TODO owned by livespec-dev-tooling-thhgeg, registered in the debt register) rides in the revise commit.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T21:18:10Z
verdict: NO BLOCKERS
proposal_stem: incident-recovery-target-branch
content_digest: 1e7dd65fa78b49087a12ac8683c3a22281cb59d0f96f2f385ede6542498c6993
