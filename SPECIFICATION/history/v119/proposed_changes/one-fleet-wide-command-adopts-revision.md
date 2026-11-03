---
proposal: one-fleet-wide-command-adopts.md
decision: accept
revised_at: 2026-11-03T10:04:50Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:gmktec-factory-placement
---

## Decision and Rationale

Accepted under delegated decision mode. The proposal states, as MUST clauses with a matching scenario, the operator surface that work item livespec-dev-tooling-jzwgjw implements:  runs every fleet manifest member's own ensure-plugins, prints the builds before and after, isolates failures, and refuses a split adoption. The behaviour was unstated, which is why the dispatch wall held jzwgjw as spec-change tier. The clauses take the member set from the fleet manifest as §"Sibling discovery" does and carry no member list, so nothing in contracts.md is contradicted. The independent reviewer (sonnet) reported NO BLOCKERS for these exact bytes. It noted two convergence edge cases left unspecified as non-blocking: a member with no install record for its path, and the 'before' read with no prior install.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T10:03:52Z
verdict: NO BLOCKERS
proposal_stem: one-fleet-wide-command-adopts
content_digest: 13a2a4a5354cd994fe6db571d2c2b2cbd12dd7457056c9a0c99419e7dbbfd96b
