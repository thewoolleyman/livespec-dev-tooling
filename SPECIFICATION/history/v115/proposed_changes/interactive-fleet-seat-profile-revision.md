---
proposal: interactive-fleet-seat-profile.md
decision: modify
revised_at: 2026-11-02T17:48:31Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:token-spend-analysis
---

## Decision and Rationale

Interactive fleet seats are about 80% of the fleet's Anthropic spend in livespec/llm-spend (anthropic-burn-mitigation, epic bd-ib-b2jzxw, 2026-11-02), and no heading of this specification governs where a seat's model, effort and context bound are set. Work items livespec-dev-tooling-3fxp3u and -jwmsk6 carry the change and are held out of ready by a mechanical no-References finding; naming §'LLM-spend telemetry pricing' would be a false reference, since it governs prices only. The section is contributor-only fleet infrastructure, so it is placed in non-functional-requirements.md per §'Boundary', with one scenario for the launcher behaviour. It fixes only that there is one committed place to set the values and that what runs matches it; the values stay the maintainer's.

## Modifications

Two wording tweaks against the proposal text, no change of meaning: the 'Observable in llm-spend' clause is split into two sentences, and the scenario's Then line ends 'all taken from the profile'.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T17:48:29Z
verdict: NO BLOCKERS
proposal_stem: interactive-fleet-seat-profile
content_digest: ee1ee77990a720d0cc79e9e02b179a7c241da09c5b41cfeb08545af8eb97a65c
