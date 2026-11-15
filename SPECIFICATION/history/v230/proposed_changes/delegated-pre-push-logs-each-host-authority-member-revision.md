---
proposal: delegated-pre-push-logs-each-host-authority-member.md
decision: accept
revised_at: 2026-11-15T03:52:48Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:stale-base-merge-options-helper
---

## Decision and Rationale

Accepted as written. legacy-coordinator-agent decided this proposal under the maintainer's delegated revise authority (R301). The delegated pre-push gate already refuses on a failing or unevaluable host-side authority member, but printed nothing for a passing one, so a host-side pass read the same as no host-side run; four measured delegated workflow-editing pushes on 2026-11-15 showed exactly that. The added sentence requires one line per host-side member naming the member, the pushing host, the judged tree hash and the result, and the scenario gains the matching line. Origin item: livespec-dev-tooling-qqkdjc (plan stale-base-merge-options, epic livespec-dev-tooling-xowhol). Its resulting files are cumulative over the self-hosted-routing-refuses-a decision in this pass. No `## ` heading changes.

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
proposal_stem: delegated-pre-push-logs-each-host-authority-member
content_digest: 7274a19cd091a3a94c51264f12390233a6609f8df4d4e727ff0d655a5400f170
