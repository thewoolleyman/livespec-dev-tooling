---
proposal: a-gh-failure-status-needs-its-http-marker.md
decision: accept
revised_at: 2026-11-11T16:16:23Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-1
---

## Decision and Rationale

Accept as filed. Repays the deferred spec debt recorded on incident item livespec-dev-tooling-t26bbr (plan expedited-incident-response-flag, research note 007 §4.4, rehearsal-2 step 6.4): the fleet gh read-failure classifier read any 5xx digit run as a server error, and the ratified spec stated none of B1, B1c or B2. The paragraph lands under the H2 the incident item already references (§"Cross-repo coordination automation surface", fleet-surface subsection that governs livespec_dev_tooling/fleet/), so the item's governing heading is unchanged, no heading-coverage row is added, and the factory repayment is judged against ratified text. The kinds and retry semantics it names match the classifier module. The anchors it names are unchanged on master at v192, so the text applies as written. Delegated decision with an independent sonnet review of the exact bytes.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T16:15:32Z
verdict: NO BLOCKERS
proposal_stem: a-gh-failure-status-needs-its-http-marker
content_digest: c24112fe0a9e6ae0cfaee4545395824a7bea01af14243a4f3717d24f0b406c3b
