---
proposal: commit-refuse-hook-check-port.md
decision: accept
revised_at: 2026-05-28T21:01:31Z
author_human: Test User <test@test.test>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accept. Replaces the deleted `primary_checkout_bare_flag_set` shared-check entry with the actually-shipped `primary_checkout_commit_refuse_hook_installed` entry in both the CI-alignment family enumeration and its own subsection, eliminating a spec↔impl contradiction. The new subsection faithfully ports the OLD section's house style and is reconciled against the impl docstring and finding-emission code. Epic li-unbare Phase 5 (exhaustive sweep).

## Resulting Changes

- contracts.md
