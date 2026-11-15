---
proposal: self-hosted-routing-refuses-a.md
decision: modify
revised_at: 2026-11-15T03:52:48Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:stale-base-merge-options-helper
---

## Decision and Rationale

Accepted with modification. legacy-coordinator-agent decided this proposal under the maintainer's delegated revise authority (R301). Condition (f) of the guarded merge_group exception requires the guard job to run on every event, but the ratified text did not say that a guard job carrying an `if:` fails (f) or what the check reports, so a guard skipped on some event could leave `needs:` unsatisfied unreported. The added sentence closes that gap, and the matching scenario clause states the failure. Origin item: livespec-dev-tooling-o3fbhe (plan stale-base-merge-options, epic livespec-dev-tooling-xowhol). No `## ` heading changes.

## Modifications

In contracts.md item (f), the appended sentence uses normative MUST language instead of the proposal's declarative wording. It reads exactly: "A guard job that carries an `if:` condition MUST NOT satisfy (f), and the check MUST report it as a finding naming the workflow file and the guard job." The scenarios.md clause stays declarative, as proposed: "And when the guard job carries an if: condition, so it does not run on every event, self_hosted_routing fails naming the workflow file and the guard job".

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T03:52:29Z
verdict: NO BLOCKERS
proposal_stem: self-hosted-routing-refuses-a
content_digest: dede56d5837122265f5486862f9a7196980757b314b49ab2eedd3cc2c61ea0d1
