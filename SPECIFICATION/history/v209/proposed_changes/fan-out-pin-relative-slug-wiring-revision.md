---
proposal: fan-out-pin-relative-slug-wiring.md
decision: reject
revised_at: 2026-11-13T02:19:54Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-runtime-and-cost
---

## Decision and Rationale

REJECT. The proposal would let the release fan-out preflight's per-member filter keep a member whose only error is a canonical-check-slugs-wired finding omitting slugs newer than its pin, as a carve-out from contracts.md section 'Pin-currency severity policy', under which every error finding other than the two staleness classes excludes. Its work item, livespec-dev-tooling-7url4a, was closed on 2026-11-11 as a duplicate of livespec-dev-tooling-szjpez, which fixes the defect in the ROW rather than the filter. contracts.md section 'Shared check inventory' already makes that row pin-relative slug by slug ('Once a consumer's library pin reaches the release that ships this module, ... the fleet-conformance row canonical-check-slugs-wired MUST report the slug'), so a row that honours it never emits the post-pin finding this proposal exempts, and the severity policy needs no second exception. Ratifying the filter carve-out would add an exemption for a finding the ratified row does not produce, and two ratified paths to one outcome. The proposal's author recorded on 7url4a that it would be rejected at its next revise as superseded by the row fix. The current spec is unchanged by this decision.

## Rejection Notes

Rejection rationale captured in §"Decision and Rationale" above. Future re-proposal would need to address that critique.
