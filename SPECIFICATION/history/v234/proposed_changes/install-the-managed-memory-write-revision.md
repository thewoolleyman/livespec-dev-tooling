---
proposal: install-the-managed-memory-write.md
decision: modify
revised_at: 2026-11-15T21:26:30Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (no-local-agent-memory seat)
---

## Decision and Rationale

Re-cut on master after the-arc-converge-route-can took v233 (legacy-coordinator-agent ruling of about 19:1xZ; the first cut, #4811 commit fbdefd44b, carried the same text). Modified on legacy-coordinator-agent's ruling of 2026-11-15T18:12:02Z on livespec-dev-tooling-i76rv2, which approved the modify the no-local-agent-memory seat proposed at 17:05:35Z with three conditions. The proposal as filed was blocked by the independent ratification review: its Mac clause ('The converge MUST run on each Mac against its own host, not as a remote mutation from another fleet host') contradicted non-functional-requirements.md section 'Host provisioning tree' Scope, which applies provisioning from the control node with no checkout on a target and covered only the legacy Ubuntu hosts. The guard paragraph for interactive_claude_hosts and the interactive-host scenario are accepted as filed. No design record is contradicted; the modify removes the only contradiction found. The independent sonnet review reported NO BLOCKERS on these exact bytes, with three non-blocking notes: the fail-at-start scenario's Given names an unreachable Mac or a missing Python interpreter but not the cannot-obtain-root case, which the existing 'Out-of-band preconditions fail at the start.' obligation already governs; reversibility and the inventory naming have no dedicated scenario, as in the proposal as filed, and are judged by the drift and apply runs; and the fail-at-start clause implies a pre-flight over every targeted Mac, which the scenario's 'MUST NOT have changed any host' makes explicit.

## Modifications

1. Transport (coordinator condition 1): each member of interactive_claude_macs is reached from the control node by the committed drift and apply commands, from committed source, with no checkout on the Mac, over ordinary ssh to cwoolley@<mac>.perch-rudd.ts.net, with the inventory naming each Mac by its full tailnet name; Tailscale SSH is forbidden because the macOS GUI Tailscale client hosts no Tailscale SSH server. This replaces the filed clause that the converge runs on each Mac against its own host.
2. Scope (coordinator condition 2): the Scope paragraph of non-functional-requirements.md 'Host provisioning tree' now names interactive_claude_macs as the one non-Ubuntu group the tree converges, ONLY for the claude_memory_write_guard role, and the Mac paragraph states the same.
3. Fail at start (coordinator condition 3): a Mac that is unreachable over that transport, that has no Python interpreter Ansible can use, or on which the converge cannot obtain root fails the run at its start naming the Mac and the missing precondition, before any task has changed a host and never part-way through a converge. A third scenario, 'a memory-write guard run fails at its start when a Mac precondition is missing', carries it.
4. The Mac scenario's Given now reads 'applied from the control node to a member of interactive_claude_macs'.
Heading coverage: the interactive-host scenario maps to tests.consumer.test_claude_memory_write_guard.test_a_bash_write_into_memory_is_refused (its filed owner livespec-dev-tooling-pik7f2 is closed); the two Mac scenarios are TODO rows at the integration tier or above owned by livespec-dev-tooling-i76rv2, with the debt register regenerated.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T21:26:28Z
verdict: NO BLOCKERS
proposal_stem: install-the-managed-memory-write
content_digest: 6deb604601e732deca90b6dfb00e01ed6bcc9256cc4c9f9084e07426414a6269
