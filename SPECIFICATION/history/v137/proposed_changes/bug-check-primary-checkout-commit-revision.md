---
proposal: bug-check-primary-checkout-commit.md
decision: modify
revised_at: 2026-11-05T03:59:40Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:expedited-incident-response-flag
---

## Decision and Rationale

Accepted in delegated mode by seat expedited-incident-response-flag. legacy-coordinator-agent accepted this exact digest under R301 on 2026-11-05 (first as 37b53359 for v136, then re-confirmed as 5c4254f0 after the rebase onto livespec-dev-tooling#3462 renumbered it to v137), conditional on an independent NO BLOCKERS review, which was returned. livespec-dev-tooling-oonqhx (the body_mismatch diagnostic slice, routed by the coordinator; root fix bd-ib-v4gghg) was refused at dispatch on 2026-11-05T02:54Z as spec-change tier, held for this topic. The ratified non_canonical_body finding carried only hook, hooks_dir, failure_mode and hint, so factory runs 01M6KQ3M9Y7W and 01M6K8RKNRZY failed on a count with no way to tell a stale installed body from a changed canonical constant. The clause adds the hook path, both SHA-256 digests and the first differing line, and makes the just check tail digest restate them per hook. It is consistent with livespec core contracts.md, which says the narration MAY name the failure mode for diagnostic clarity while the structural fail finding is identical; no design record is contradicted. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes.

## Modifications

Two wording modifications to the proposal's text. (1) path reads 'otherwise empty' for every mode other than non_canonical_body, so no other mode's contract changes. (2) One added paragraph declares the three new fields and the non-empty path to be diagnostic narration under that section's existing MAY: they MUST NOT change status, the exit code or the corrective action, which stay identical across the three hook-installation modes. missing and not_executable keep path empty and carry none of the fields, and a matching hook still passes with exit 0 and no new output. The scenario uses this repository's blank-line Given/When/Then style. No rule was added or dropped.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T03:58:50Z
verdict: NO BLOCKERS
proposal_stem: bug-check-primary-checkout-commit
content_digest: 5c4254f0dea4cafe4e9dd0d1f1a122b294b5a2df33cd34454139188cb9929867
