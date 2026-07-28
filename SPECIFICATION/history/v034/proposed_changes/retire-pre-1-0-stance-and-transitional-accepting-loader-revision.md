---
proposal: retire-pre-1-0-stance-and-transitional-accepting-loader.md
decision: accept
revised_at: 2026-07-28T22:17:40Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-5
---

## Decision and Rationale

ACCEPTED, both proposals, under the maintainer ruling of 2026-07-29 delegating the accept/reject decision at revise to this thread. Neither proposal was re-litigated and neither was reworded while applying.

Proposal 1 (pre-1.0 stance) is accepted because the clause is NORMATIVE and false: it told a future editor that a breaking change may land in a lower component, which under a released and fleet-consumed v1.0.0 is an instruction to ship an unsignalled incompatibility. The v0.54.12 deviation record is PRESERVED and rescoped to the regime then in force rather than deleted, because recording that deviation is the paragraph's purpose; a new paragraph states the post-1.0 rule and explicitly forbids reading the historical record as a standing licence.

Proposal 2 (transitional accepting loader) is accepted because the spec stood in active contradiction of the shipped loader: the spec said the loader MUST accept and WARN; since Phase 4 (b36e0b8, released as v1.0.0) it rejects. Ratifying the transitional clause at v033 was CORRECT and is what authorized Phase 4, so this amendment corrects a standing DESCRIPTION and is not a repudiation of that decision.

Two things were deliberately preserved rather than swept along with the retirement. The harden-first ordering clause SURVIVES as a standing rule for future required-key schema changes -- the transition was one application of it, and deleting the rule with its occasion would discard the general constraint. And Section 'Clean role keys retain []' is left intact: a bare [] stays legitimate for the five CLEAN keys, where emptiness removes exemptions rather than files and so makes the consuming check stricter rather than blinder.

The scenario was REWRITTEN rather than deleted, per authoring split (i): the behavior it governs -- a consumer declaring a union role key as a bare [] or "" -- still exists and is still load-bearing; only its outcome changed from WARN to hard failure. No other scenario covers that input; the neighbouring 'declared-absent variant with an empty payload' scenario governs a blessed variant NAME carrying an empty payload, which is a different input. The final 'And the emptiness MUST NOT be reported as a sanctioned opt-out' was carried over verbatim: it is the invariant the union exists to enforce and it survives the change in outcome.

Out-of-target, recorded here so it is not lost: tests/heading-coverage.json links the rewritten scenario to test_legacy_empty_target_dirs_is_announced_at_warn, a test Phase 4 DELETED; its live replacement is test_legacy_empty_target_dirs_is_now_rejected_at_load. That registry sits outside the spec target and is corrected as implementation work accompanying this revision.

Process note: the Step 3.5 stale-branch precondition FAILED, flagging this revise pass's OWN branch (spec/retire-pre-1-0-and-transitional-warn, 1 commit ahead -- the filing commit 62413ab). It cannot distinguish an abandoned spec/* branch from the branch the revise is running on. Overridden deliberately with --skip-stale-branch-check and narrated rather than silently skipped.

## Resulting Changes

- contracts.md
- scenarios.md
