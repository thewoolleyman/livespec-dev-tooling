---
proposal: alert-thresholds-match-packed-fleet.md
decision: modify
revised_at: 2026-11-06T04:03:38Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Modified in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Delegated decider: legacy-coordinator-agent under R301/R493, which ruled ACCEPT on both proposals on 2026-11-04 for plan address-honeycomb-alerts (epic bd-ib-xkwdap in livespec-orchestrator-beads-fabro). On 2026-11-06 it ordered this revision re-landed and confirmed the decision on these exact bytes. Why it is re-landed: the same resolution was ratified as v131 on 2026-11-04 on branch spec/alert-thresholds-match-packed-fleet (commits 42f7cd23 and 31b47cac). PR #3413 merged with only the propose commit, e7479fa7, so the revision and its trigger change never reached master. The live Honeycomb triggers already matched v131, so live state was ahead of master. kubernetes-observability (epic livespec-dev-tooling-s2aqob) measured that drift on 2026-11-06 at about 04:05Z. This revision re-applies v131's resolution unchanged on top of v143. Basis: measured noise with no actionable signal. The node CPU-idle trigger sent 220+ emails in 7 days and the factory quota trigger 80+. The pool is packed to capacity by design, so CPU idle stays on the board, and saturation is actionable only through the outcome triggers. The longest normal full-quota stretch measured over 72 h was 75 minutes, so the quota window becomes 2 hours. The decision is modify rather than accept because scenarios.md's quota-trigger scenario still stated 15 minutes. Its window is co-edited to 2 hours so that it agrees with the revised clause. That is an internal-consistency repair; the decision content is unchanged. No design record is cited by the touched clauses, and none is contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes. It found no other statement in the v143 tree that still requires a CPU-idle trigger or a 15-minute quota window. Its non-blocking notes name the implementation co-changes, which land in the same pull request: delete ci-runner/observability/triggers/k8s-node-cpu-saturation.json, set k8s-factory-quota-near-hard.json time_range to 7200, and update the definitions test.

## Modifications

Both proposals are applied as filed, with the clause text lightly re-punctuated (an em dash introduces the outcome-trigger list). In addition, scenarios.md's quota-trigger scenario changes 'for 15 minutes' to 'for 2 hours' so that it agrees with the revised clause.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-06T04:02:07Z
verdict: NO BLOCKERS
proposal_stem: alert-thresholds-match-packed-fleet
content_digest: 6cf6afe23086481ab58386838570de0b117801e5fe82ca5fb105b6dc55eb9b4c
