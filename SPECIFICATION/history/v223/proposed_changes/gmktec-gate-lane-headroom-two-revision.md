---
proposal: gmktec-gate-lane-headroom-two.md
decision: accept
revised_at: 2026-11-14T18:45:45Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted as proposed. The gmktec-xubuntu gates-flavor lane floor drops from three default-size gate Jobs to two (10 CPU, 12Gi). It is still derived from the renderer's default request, and one undeclared full-size Job stays admissible, which Lane capacity relies on. The measured cause, added 2026-11-14 18:4xZ: orchestrator gate pods burst to 14-22.5 CPU each against a 5-CPU request, and in the 18:26-18:41Z episode the gates namespace held about 26 of gmktec's 32 cores, while legacy-dispatcher-agent's BestEffort cpu.pressure tripwire paused factory placements. The committed lane stays at 15 CPU until a separate capacity change with its own G2 read and revert trigger moves it. Revise order ruled by legacy-coordinator-agent (58d68f5e).

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-14T18:45:26Z
verdict: NO BLOCKERS
proposal_stem: gmktec-gate-lane-headroom-two
content_digest: 77f876cedc402694e1842457d75093420af7ff5ab45d21d53cd856ba9e15b724
