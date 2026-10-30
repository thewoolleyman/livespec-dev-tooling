---
proposal: the-fabro-server-role-deletes.md
decision: modify
revised_at: 2026-10-30T20:12:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Ratifies the fabro_server role's declared retired_environments axis as the role-driven form of step 3 of a sandbox-environment rename, releasing the spec-change-tier hold on livespec-dev-tooling-lmuhvi (topic the-fabro-server-role-deletes, filed by petri-factory-on-gmktec under coordinator ruling R214). Decided under delegated revise_decision_mode by the delegated-gate-fleet-rollout seat.

## Modifications

Credential wording sharpened to "authenticating with the same credential the role uses for its other catalog requests" (the role's FABRO_DEV_TOKEN bearer), a § added to the cross-reference, and "leaving the id in the catalog" added to the live-run failure. A scenario is added because this is load-bearing behaviour; its heading-coverage row is a spec-first TODO owned by lmuhvi.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T20:02:51Z
verdict: NO BLOCKERS
proposal_stem: the-fabro-server-role-deletes
content_digest: 522dcd9211f0ac78553e973206e55073bf1b4262bc0fd38d38cc77c0e0a6551a
