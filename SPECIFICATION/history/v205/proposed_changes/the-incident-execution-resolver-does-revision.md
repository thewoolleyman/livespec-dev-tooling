---
proposal: the-incident-execution-resolver-does.md
decision: modify
revised_at: 2026-11-12T13:53:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-fable-5-2
---

## Decision and Rationale

The enablement record, the arm-gated fence and the bounded manifest read are accepted as graded by legacy-coordinator-agent on livespec-dev-tooling#4305 (PASS with one fix, already in the proposal), for work item livespec-dev-tooling-2xxnku under plan expedited-incident-response-flag. A pre-merge doctor pass walked the drafted text through incident_hook_entry.py, incident_ci_entry.py, incident_observer_control.py and the incident_observer role and returned two high findings (a scratch drill no runner can reach; a scenario demanding receipts an emergency revert never produces) and five lesser ones; the independent ratification review returned one blocker in each of two rounds (a revoked record with two readings; an unreachable vantage both required and forbidden to refuse) before NO BLOCKERS on the final bytes. Each is repaired in the modifications. No design record is contradicted: the text extends the ratified one-enablement-step paragraph and keeps the rule that an operator can deliver an expedited repair before the fence is armed.

## Modifications

Relative to the proposal: (1) 'the bounded freshness rule the next proposal states' reads 'this section states below'; (2) a record superseded by a later record reads as that later record reads, and one superseded by a revocation reads `revoked`, instead of both reading as absent, which contradicted the `revoked` reading and the scenario that names the revocation; (3) the controller's current and admitted refusal is stated subject to the emergency-revert exception for `unavailable`; (4) a vantage other than the controller that cannot reach its installation's query route reads `unavailable`, records it and does not refuse, because it cannot know the arming state and the controller's own answers are the fence no entrance can skip; the two armed-refusal sentences are scoped to a vantage that holds the installation's answer; a vantage may cache its last confirmed manifest identity in local state, which is never the enablement record; (5) `armed`, `disarmed` and `the arming write` are stated to mean the fence alone, distinct from the controller's existing per-pull-request arm and its arm receipt, and scenario 3 says 'attempts the arming write for the installation's fence'; (6) a reading recorded in the CI plan is not part of the plan identity the CI entrance rechecks; (7) the ordering paragraph's drill reads against the still-disarmed production installation, because the ratified scratch rule makes a scratch listener reachable only from its host, so it cannot answer a runner; (8) the bootstrap sentence states it is not an exception to enablement only through the one enablement step; (9) scenario 4 records each `unavailable` reading in the artefact its vantage already produces, because an emergency revert produces no CI plan and no arm receipt. Scenario bodies are fenced as gherkin.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T13:52:55Z
verdict: NO BLOCKERS
proposal_stem: the-incident-execution-resolver-does
content_digest: 8fe69132d1a322fb2d2417856e7a78c451bb0cebc05969678b94b423eeafdfb1
