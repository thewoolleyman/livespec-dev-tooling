---
proposal: primary-checkout-hook-check-documents-all-arms.md
decision: modify
revised_at: 2026-10-30T21:19:41Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

DRIFT-ORIGIN, decided by the MAINTAINER, not by a delegated decider. drift_acceptance_mode is human. Maintainer direct answers are recorded on epic livespec-dev-tooling-dfixhe: comment 01a18ea5 (2026-10-30T21:09:52Z, attended) accepts the proposal as written, and comment 01a18eab (2026-10-30T21:15:39Z, attended) directs that item 4's hint text be corrected to match the shipped check. The change brings contracts.md §"`primary_checkout_commit_refuse_hook_installed` check" up to the shipped verifier: the worktree-pack and vendored-copy failure modes, byte identity against CANONICAL_HOOK_BODY, the exit-4 branches, and the corrective hints. Applied by the delegated-gate-fleet-rollout seat on coordinator gitops-fleet-capacity-monitoring's relay.

## Modifications

Items 1-3 are applied as written. Item 2 required two consistency edits: the tolerant-fingerprint paragraph and algorithm step 5 now state byte identity, and the sentence saying both detection mechanisms are recognized is removed, because byte identity rejects the legacy body. Item 4 is corrected per the maintainer's 21:15:39Z answer, after the first independent review found its as-written 'both installers' wording false against the shipped hints. body_mismatch and file_missing now point to 'just install-worktree-pack' (or 'just bootstrap' where the recipe is absent); unreadable says to fix the read fault for the named path and re-run; vendored_copy_present says to delete the vendored copy. Residual drift remains out of scope: the hook_unreadable, git_probe_failed, foreign_lefthook_wrapper, worktree_pack_absent, worktree_pack_not_imported and worktree_discipline_malformed modes; three hooks rather than two; and body_mismatch versus the spec's non_canonical_body.

## Resulting Changes

- contracts.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-30T21:17:54Z
verdict: NO BLOCKERS
proposal_stem: primary-checkout-hook-check-documents-all-arms
content_digest: 38765e2645a5dd734ec8124e0242118fbb4fd8b201c2343ad23c61c15386d4a7
