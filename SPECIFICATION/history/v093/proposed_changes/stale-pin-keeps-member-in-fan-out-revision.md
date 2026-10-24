---
proposal: stale-pin-keeps-member-in-fan-out.md
decision: accept
revised_at: 2026-10-24T11:55:39Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted. A stale pin keeps its member in the release fan-out: staleness findings stay error-severity and are named in the preflight's exclusion summary, but no longer exclude the member, because the sibling-released dispatch is the remedy for a stale pin. A can't-parse pin finding and every non-pin-currency error row still exclude. Evidence: livespec-console-beads-fabro went seven days without a sibling-released dispatch (livespec-dev-tooling-epcoja), and on 2026-10-24 livespec missed dev-tooling v1.129.0-v1.129.2 on a stale orchestrator compat pin, which blocked plan delegated-gate-fleet-rollout until a manual pin-freshness sweep. The design record livespec-dh9r keeps both intents: no member blocks the others, and no stall is silent, since the findings stay error and are named. DEPARTURE FROM LITERAL TEXT, explicitly acknowledged by the maintainer as this revision requires. The proposal departs from 'An error finding for a member in the release's dispatch sibling set excludes that member'. Maintainer acknowledgment, verbatim, 2026-10-24 ~11:3xZ, relayed by coordinator gitops-fleet-capacity-monitoring and recorded on livespec-dev-tooling-dfixhe: "Okay that one's fine. Go ahead with it." Ratification: Fable, separate read-only reviewer, NO BLOCKERS. Non-blocking notes deferred to an editorial pass: restore the section-sign cross-reference form in the replaced paragraph, and align 'exclusion summary' with 'the run's summary'.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-24T11:54:16Z
verdict: NO BLOCKERS
proposal_stem: stale-pin-keeps-member-in-fan-out
content_digest: fa060a1bda2bb70e15ffacd3d9f6b38482c2253cda1f9ff73d98b82874b60b04
