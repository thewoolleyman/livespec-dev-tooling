---
topic: the-claim-token-race-drill
author: claude-opus-5-5
created_at: 2026-11-12T14:10:00Z
---

## Proposal: The claim-token race drill releases both writers from one event, so a late release under load never decides whether the race happened

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph to non-functional-requirements.md, section "Consent-gated pool-node disruption". It states the claim-token race drill (`ansible/claim-token-race-drill.yml`) as a disruption that section covers, and states the one property that work item livespec-dev-tooling-ek36t5 delivers. In its overlapping case the drill releases both claim writers from one event the play makes once, after both have reached the barrier. How long the play takes to deliver that release to either writer does not decide whether the race happened. Adds one scenario to scenarios.md.

### Motivation

Work item livespec-dev-tooling-ek36t5 (plan expedited-incident-hardening, epic livespec-dev-tooling-dh3hub) was classified spec-change at dispatch on 2026-11-12 at 13:46:10Z: verdict unstated, linked topic `the-claim-token-race-drill`. The rationale says the ratified text never mentions the claim-token race drill, its barrier lead and tolerance, or releasing both writers from one event.

The drill exists to give the orchestrator's claim-token protocol host-captured evidence: of two claim writers on different hosts, sharing only the Beads server, exactly one changes a contested dispatch claim (orchestrator bd-ib-4eeefv; plan expedited-incident-response-flag). Its overlapping case today names one wall-clock instant with `date -u +%s` on the control node. It then writes "at <instant + lead>" into each host's go FIFO in a two-item loop, one Ansible module start per host. A writer that reads its signal more than 5 s past that instant reports `barrier-missed` (`ansible/files/claim_token_race_drill_barrier.py`, `_BARRIER_TOLERANCE_SECONDS`). On a loaded host the two release writes can together take longer than the lead plus the tolerance. Measured on the old test harness at host load ~100 with each release write delayed 8 s and a 6 s lead, the control-node writer read its signal 13.4 s past the instant. So the drill fails, in its test and in a live run, because of how slowly the play delivered the release, not because of anything the claim-token protocol did. legacy-coordinator-agent graded wacdfl's lead raise from 6 s to 30 s (livespec-dev-tooling#4045) as a margin rather than a root fix, and filed ek36t5 for the root fix.

The paragraph also records the drill's committed, confirmation-fenced shape, which the play already has, so the section's existing rules visibly apply to it. It adds no rule the current play does not already meet, except the single-event release that ek36t5 delivers. The live drill's host-captured records were taken against the current play. A later run under the changed release is new evidence and does not invalidate those records.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "Consent-gated pool-node disruption", insert the following paragraph immediately after the paragraph that begins "**A factory sandbox loss drill deletes exactly one named run's sandbox pod.**" and before the section's next `## ` heading. No heading is added, removed or renamed in that file.

**A claim-token race drill releases both writers from one event.** A playbook that races a claim writer on one runner-pool host against a claim writer on the control node `vps`, for one claim token of a ledger tenant, to exercise the claim-token protocol's promise that exactly one of two writers on different hosts changes a contested claim, is a disruption this section covers. It MUST be committed and applied from `vps` with `just ansible-apply`, it MUST act only on the pool host its confirmation variable names, and it MUST read nothing and change nothing when the confirmation is absent or names another host. In the case where the two writers overlap, the play MUST release both writers from one release event that it makes once, and only after both writers have reported that they reached the barrier. Whether the two writers raced MUST NOT depend on how long the play takes to deliver that release to either of them. A release that reaches a writer late, for example because the host is loaded, MUST NOT make that writer report that it missed the barrier, and both writers MUST still contend for the same contested token. A wall-clock instant the play still names MAY schedule the writers' attempt, but it MUST NOT be what decides whether the race happened.

In `SPECIFICATION/scenarios.md`, insert the following scenario immediately after the scenario "a factory sandbox loss drill deletes exactly one named run's sandbox pod and nothing else" and before the scenario "a new heading-coverage TODO row absent from the debt register fails the authoring-time armed tier".

## Scenario: a claim-token race drill's overlapping case still races both writers when the release reaches one writer late

Given the claim-token race drill applied from the control node with its confirmation naming one runner-pool host

And both claim writers of its overlapping case have reported that they reached the barrier

When the play's release reaches one writer later than the configured barrier lead plus the barrier tolerance, because delivering it to that host was slow

Then that writer MUST NOT report that it missed the barrier

And both writers MUST contend for the same contested claim token, and the drill MUST read back that exactly one of them changed the claim

The revise that accepts this proposal MUST add a `tests/heading-coverage.json` entry for the new scenario heading in the same commit. A spec-first `"test": "TODO"` row is acceptable when its reason names the integration tier and it carries `"work_item": "livespec-dev-tooling-ek36t5"`, with the heading-coverage debt register regenerated.
