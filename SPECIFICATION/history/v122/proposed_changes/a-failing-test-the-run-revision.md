---
proposal: a-failing-test-the-run.md
decision: modify
revised_at: 2026-11-03T13:16:01Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Re-cut of PR #3177 (commit 20c3ed20), which ratified this proposal as v116 on 2026-11-02 but never merged. Master meanwhile took v116 through v121, so the same content is cut here on current master as v122. The number v122 is agreed with ci-runtime-and-cost, and legacy-coordinator-agent's one-revise-PR-at-a-time rule applies. The decision and its substance are unchanged from the original record. The maintainer ruled on livespec-dev-tooling-6tgd2z (2026-11-02 18:38:21Z and 18:39:54Z) that a flaky test may be retried in place up to 3 times, 60 s apart, only when the run did not touch it, and that every flake is immediately assigned a root fix. The rule is a contributor-side test-infrastructure policy placed under non-functional-requirements.md §'Testing approach', with six scenarios appended to scenarios.md. The six TODO coverage rows are owned by livespec-dev-tooling-crxcy4, and the debt register is regenerated. A fresh independent Sonnet review of the re-cut bytes returned NO BLOCKERS. It confirmed that the delta is byte-identical to #3177's, that nothing on master was dropped, and that nothing contradicts v117 through v121. Decided under the project's delegated revise_decision_mode. #3177 is closed as superseded by this pull request.

## Modifications

Independent review (sonnet, 2026-11-02) found two blockers in the proposal as filed; both are resolved here. (c) Several MUST clauses had no scenario: three scenarios are added for the whole-session disable, root-fix filing and the replay legs, and the GitHub ::warning is folded into the first. (d) The touched definition missed unstaged and deleted paths and files exercised outside the import closure: the change set now spans committed, staged, unstaged and untracked changes including deletions, the closure is read from the working tree, and touching now also covers dotted module names and any path, file name with extension or parent directory name that appears as a string literal in the closure. A second review found two further gaps, also resolved: the unparseable-closure trigger is added to the session-disable scenario, and a retry-exhaustion scenario (3 re-runs, session fails, reported as failed) is added.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-03T13:15:11Z
verdict: NO BLOCKERS
proposal_stem: a-failing-test-the-run
content_digest: ec566ee1fd49b7014a0f7009109f710fb7156491d8df36b2c83902c5c8108138
