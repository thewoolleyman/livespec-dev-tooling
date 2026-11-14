---
proposal: place-the-hetzner-xubuntu-dolt.md
decision: accept
revised_at: 2026-11-13T00:18:07Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted unchanged after two coordinator grades (PASS-WITH-FIXES, then PASS at 51f8f0dd5). It adds the managed authorized_keys obligation under ## Host provisioning tree: declared and marked entries, other unmarked lines byte-for-byte, pinned order and 0600 mode, --check reporting add/change/remove, and a no-op reapply. Forward-only entries are locked to exact forwards, with the unused direction closed by permitlisten/permitopen="invalid.invalid:1" (measured on OpenSSH 10.0p2; 'none' refuses the whole key). It requires host OpenSSH, never Tailscale SSH. A hand-placed key may be retired by its key blob, and a managed-and-retired conflict refuses. The repo-private control is check-ansible-authorized-keys-managed. Three scenarios cover it; their heading-coverage TODO rows are owned by livespec-dev-tooling-sr46h2. It serves sr46h2 (the hetzner-xubuntu Dolt tunnel) and the coordinator's RETIRE ruling on homelab hl-rz6pdp.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-13T00:17:57Z
verdict: NO BLOCKERS
proposal_stem: place-the-hetzner-xubuntu-dolt
content_digest: 6887edf4be37878b8e7d56d9dbafa521aa5fdb4593b1f06b0cff4fac7b3b9c32
