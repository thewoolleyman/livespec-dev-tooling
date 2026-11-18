---
proposal: a-delegated-pre-push-gate-that-reaches-no-verdict-falls-back-to.md
decision: modify
revised_at: 2026-11-18T07:12:06Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-sonnet-5-5 (gate-job-resources plan seat)
---

## Decision and Rationale

Maintainer ruling on livespec-dev-tooling-6wueag (relayed by throughput-plans-coordinator, 2026-11-17) requires the delegated gate to fall back to running its checks locally when the cluster or gate gives no verdict. The pre-push Verdict bullet was the one remaining fail-closed point; commits and the unreadable-kubeconfig push already fall back. Two independent sonnet reviews of the drafted bytes: the first found seven places where the old refusal still stood; this decision includes those corrections and the second review returned NO BLOCKERS. Intent preserved: a verdict the gate returned (red tree, validation refusal, non-Linux host) is never replaced by the fall-through. The proposal's new scenario is applied by the follow-up revise (v249) for the register reason stated in the modifications.

## Modifications

Accepted with modifications. The proposal swapped only the Verdict sentence in contracts.md Delegated pre-push gate and added one scenario. Independent review found that leaves the old refusal rule standing elsewhere, so this decision also: (1) removes the scenario 'an opted-in push is refused when no verdict arrives', the exact inverse of the new scenario, and drops its heading-coverage row; (2) changes the scenarios 'a delegated gate run that reaches no verdict emits a no-verdict outcome event', 'a delegated gate run its own client interrupts emits a client-interrupted no-verdict outcome event' and 'a delegated pre-push wait interrupted by host sleep never reports a pass' to the fall-through; (3) changes the two contracts.md bullets that say a failed private-sibling token mint refuses the push, the pre-commit evidence bullet that points at the Verdict bullet's refusal, and the two commit-side Absent verdict bullets that said the pre-push rule departs from them; (4) changes the non-functional-requirements.md 'A gate always ends with a verdict' sentence that ended an interrupted wait with a refused push; (5) states in the Verdict bullet that a run the gate client itself ends on SIGTERM, SIGINT or SIGHUP starts no fall-through and the push does not complete, since a killed client cannot run one; (6) DEFERS the new scenario 'a delegated pre-push gate that reaches no verdict falls back to the local gate' and its spec-first heading-coverage row to a follow-up revise, because the heading-coverage debt register admits a new TODO heading only when the same change removes no existing heading and this revise removes the inverse scenario; livespec-dev-tooling-6jwz3x owns that scenario's test and changing the tests that assert the old refusal. (7) Corrects the Telemetry bullet's 'A push that takes the local fall-through starts none' so it covers only an ineligible host, since a push that reached no verdict has already emitted its one outcome event; and extends the signal sentence to a gate client whose working tree stops existing, matching the client-interrupted cause. These two were found by the doctor's LLM phase before merge.

## Resulting Changes

- contracts.md
- scenarios.md
- non-functional-requirements.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-18T07:11:43Z
verdict: NO BLOCKERS
proposal_stem: a-delegated-pre-push-gate-that-reaches-no-verdict-falls-back-to
content_digest: d08a7ff2884438d86c9f2c0a4c3342025bec2222fa1ad6fb7a7304e21aac8acb
