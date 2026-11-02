---
proposal: radar-readiness-reader-blockers-from.md
decision: accept
revised_at: 2026-11-02T23:12:03Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:radar-and-deterministic-admission
---

## Decision and Rationale

Work item livespec-dev-tooling-m2x5pt (plan radar-and-deterministic-admission, assertion 4) was held at factory dispatch on 2026-11-02T19:54Z, because the spec-stated judgement found ## Maintainer radar silent on two behaviours in its Definition of Done. The first is that readiness names each open blocker as <tenant>:<id>. The second is that a closed target is reported as DONE rather than as ready or blocked. The proposal states the three readiness states and the blocker-naming rule as BCP14 clauses at the end of the section, and adds one scenario that exercises both. It agrees with the existing rules that a closed entry is DONE, that a closed blocked_by is a cleared blocker, and that non-blocking edges do not block. The plan owner chose to close the gap at the spec rather than weaken the item's Definition of Done, and the coordinator acknowledged that on 2026-11-02. The independent reviewer found no blockers. Its one cosmetic finding, the blank lines around the scenario, is applied in the final bytes, which it re-reviewed.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T23:11:59Z
verdict: NO BLOCKERS
proposal_stem: radar-readiness-reader-blockers-from
content_digest: bf86624e7be04ea063ac6e86cee40acb570707401862b6cad364b2747c5792ca
