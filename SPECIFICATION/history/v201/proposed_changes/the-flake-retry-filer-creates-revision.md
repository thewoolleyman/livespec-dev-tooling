---
proposal: the-flake-retry-filer-creates.md
decision: modify
revised_at: 2026-11-12T05:49:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The proposal's intent is accepted: a root-fix item the host-side flake reader files must be routed through intake, a refused routing must be visible, and the item must be re-routed rather than re-filed (livespec-dev-tooling-5bbk5n measured a raw bd create with no claim token stranding items unrouted while the reader marked them filed). A pre-merge doctor pass against live code found that the text as proposed (a) let a refusal abort the pass, contradicting the ratified 'at once' for other node ids; (b) would re-route already-routed items, demoting an in-flight dispatch through intake; (c) let the claim token be named after creation, outside the store's claim protocol; and (d) contradicted itself with 'never stays unrouted', left the success path without a scenario, (e) forbade a second item for a node id unconditionally, contradicting the ratified 'none while one is open', and (f) gave no observable for 'not yet routed'. The modifications fix each, keeping BCP14 MUST clauses beside the rule they extend plus two Given/When/Then scenarios. The independent sonnet review returned NO BLOCKERS on these exact bytes. legacy-coordinator-agent graded the proposal PASS (livespec-dev-tooling#4246).

## Modifications

Landed with these modifications from two pre-merge LLM doctor passes that walked the proposal through live code (flake_retry_filer.py; the orchestrator's file_captured_work_item, apply_intake_dor and intake triage marker). (1) The reader creates each item only through the store's capture path and routes it through the intake Definition-of-Ready gate, cross-referencing livespec-orchestrator-beads-fabro contracts.md §"`capture-work-item`". In a tenant whose `.livespec.jsonc` commits `dispatcher.claim_tokens`, that path names the first claim token in the creating write, so the reader MUST NOT create the item any other way. (2) 'never stays unrouted' became a tenant-wide rule: a pass that exits zero leaves no filed item unrouted. (3) A refused routing no longer aborts the pass: other node ids are still filed and routed, then the pass exits non-zero. (4) The log names the item id only when one was created. (5) Re-routing is keyed on intake's triage marker: route again only an item without it, never one that carries it. (6) No second item is filed while the node id's item is OPEN, so a recurrence after closure files again, matching the ratified rule. (7) A claim-token success-path scenario was added (stated as what the reader controls), and the refusal scenario uses two node ids.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T05:47:58Z
verdict: NO BLOCKERS
proposal_stem: the-flake-retry-filer-creates
content_digest: b92487ebe82df90b49388f8d250bcce5e5dd30100385ce1d40ac796d04996a78
