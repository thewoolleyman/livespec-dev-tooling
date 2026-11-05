---
proposal: port-fabro-hosts-check-settings.md
decision: accept
revised_at: 2026-11-05T08:25:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Delegated decider: legacy-coordinator-agent under R301. Plan ci-pool-provisioning-leftovers found fabro-hosts' hand-run services/fabro-server/check-settings.sh and its per-host expected files with no role and no owner. The plan decided to port the comparison into the fabro-hosts.yml drift report, which until now compared plugin pins only. Carrier: livespec-dev-tooling-po2nrg. No ratified statement conflicts, and no design record is contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes. It noted, as non-blocking, that the correspondence between mapping keys and endpoint setting names is left to the implementing item.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T08:23:30Z
verdict: NO BLOCKERS
proposal_stem: port-fabro-hosts-check-settings
content_digest: 5fa4afee5506733dbb3d981c754d5035e0e039947d20809d56509dd84c7cb2f8
