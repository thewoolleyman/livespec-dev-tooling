---
proposal: master-green-tolerates-external-red.md
decision: modify
revised_at: 2026-11-16T08:02:14Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (master-green-external-outage plan seat)
---

## Decision and Rationale

The proposal is accepted with modifications: both coordinators graded its first form, and a pre-merge doctor LLM pass walked the drafted text through the real code and found that the first form could not work (a master-health green beside a red ci-green, an episode walk beyond the read budget, a check-suite selection that does not hold, no host for the schedule leg, collisions with the existing reconciler). Four rounds of independent review shaped the resulting text, and the last digest-bound review returned NO BLOCKERS.

## Modifications

Reworked after four independent review rounds. The episode clock carries forward from the nearest preceding non-success run's master-health instead of walking every run (at most three reads); only a run whose ci-green job reads success breaks the sequence, matching core; started_at is the earliest run's completion time (the runs-list completion time standing for the ci-green job's). master-health reads defect when ci-green itself failed with green gating jobs and never green beside a red ci-green; the gate selects by the run_id and head_sha binding, reads every matching check run and the highest id wins; a failed master-health read exits 1 and never takes the skip path. Alert issue carries label master-green-external-red and title prefix 'master-green: ', is deduplicated and closed on green, with a separate 'episode unreadable' issue when the clock cannot be read. The master-health reconciler selects no culprit and opens no new revert while an external red is unexpired, leaving re-run, classification and in-flight reverts to its own section. One shared helper subsumes the existing classifiers; per-job results travel as artifacts named by job and run attempt; a scheduled step re-reads and alerts. Three new scenarios: carry-forward across a cancelled run, never green on a red ci-green, reconciler stand-down; the 403 scenario is retitled. tests/heading-coverage.json and the debt register carry twelve TODO rows owned by livespec-dev-tooling-ravutf, -arfnpo and -auprb3.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-16T08:00:20Z
verdict: NO BLOCKERS
proposal_stem: master-green-tolerates-external-red
content_digest: 2b3258792d50cfd1c299da6b825a5611b0906fbde7f4ad3fb9d55e4b6304c32b
