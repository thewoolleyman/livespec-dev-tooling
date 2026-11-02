---
proposal: execution-target-pressure-telemetry.md
decision: accept
revised_at: 2026-11-02T16:10:59Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:radar-and-deterministic-admission
---

## Decision and Rationale

Two admission inputs the plan reads from Honeycomb do not exist: pressure stall information on any execution target, and the dev host's host metrics in livespec. A prior-art scan of both ledgers found no item that owns either. The proposal adds them as BCP14 clauses, each backed by one of three scenarios. It extends §'Runner-pool node telemetry' without replacing it, and it requires an emitter converged by Ansible that fails loudly instead of reporting a false zero.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T16:08:31Z
verdict: NO BLOCKERS
proposal_stem: execution-target-pressure-telemetry
content_digest: 8cdb5569147bc446a97291449b981ad72dfe04ce2f6cef56c561d99ed5bbdf1c
