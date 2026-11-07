---
proposal: branch-protection-alignment-ruleset-held-required-check.md
decision: accept
revised_at: 2026-11-07T14:19:40Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted with three tightenings from the independent review folded in before ratification (rules read pages through every result; an absent classic required_status_checks object is an empty classic contribution, never the outcome-3 skip; strict findings are one per offending source; an organization-level ruleset the repository endpoint does not serve is unreadable). The change conforms the check to livespec NFR §"CI as a merge gate (branch protection)" (incident-only precedence: recovery-principal authorization proven against every overlapping protection rule, ordinary actors including administrators keep their required checks, branch_protection_alignment recognizes the authorized incident shape) and livespec contracts.md §"Expedited incident response policy" (authorization against every overlapping classic protection or ruleset; ordinary protection never disabled). Holding the all-green gate in an active ruleset whose only bypass actors are GitHub Apps keeps ci-green required for every ordinary actor and lets only the App bypass it, which classic protection cannot express because a ruleset bypass never exempts an actor from a classic rule. Decision owner: the coordinator (legacy-coordinator-agent, R301) chose to move ci-green from classic protection into ruleset 26758787 on 2026-11-07; the maintainer approved the ruleset itself. Deferred follow-up, not ratified here: pinning the permitted bypass App id(s) in configuration, so that only the repository's declared recovery App (not any App) passes the ruleset-bypass rule.

## Resulting Changes

- contracts.md
- scenarios.md
- ../tests/heading-coverage.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-07T14:19:00Z
verdict: NO BLOCKERS
proposal_stem: branch-protection-alignment-ruleset-held-required-check
content_digest: 19afaccaf5457d7c41574cee46acc7ab1bed558e16fd2d1a39961d0db14f0beb
