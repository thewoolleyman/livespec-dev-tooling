---
proposal: a-failing-test-the-run.md
decision: modify
revised_at: 2026-11-02T19:06:13Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:dev-host-test-gate-load
---

## Decision and Rationale

The maintainer ruled on livespec-dev-tooling-6tgd2z (2026-11-02 18:38:21Z and 18:39:54Z) that a flaky test may be retried in place up to 3 times, 60 s apart, only when the run did not touch it, and that every flake is immediately assigned a root fix. No ratified text states a retry policy for the shared enforcement suite, so implementation item livespec-dev-tooling-crxcy4 was held at the spec-change tier under §'Testing approach'. The rule is a contributor-side test-infrastructure policy, so it is placed as a bullet under non-functional-requirements.md §'Testing approach'. Two Given/When/Then scenarios carry the retried and the not-retried paths. It contradicts no existing statement: a grep for retry, rerun and flak finds no ratified retry rule in this repository's specification.

## Modifications

Independent review (sonnet, 2026-11-02) found two blockers in the proposal as filed; both are resolved here. (c) Several MUST clauses had no scenario: three scenarios are added for the whole-session disable, root-fix filing and the replay legs, and the GitHub ::warning is folded into the first. (d) The touched definition missed unstaged and deleted paths and files exercised outside the import closure: the change set now spans committed, staged, unstaged and untracked changes including deletions, the closure is read from the working tree, and touching now also covers dotted module names and any path, file name with extension or parent directory name that appears as a string literal in the closure. A second review found two further gaps, also resolved: the unparseable-closure trigger is added to the session-disable scenario, and a retry-exhaustion scenario (3 re-runs, session fails, reported as failed) is added.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-02T19:06:12Z
verdict: NO BLOCKERS
proposal_stem: a-failing-test-the-run
content_digest: d96b65bf0c1d53cfa87cd79cbd2729e8ea4fd1fe22898046fb4c2992565ef74b
