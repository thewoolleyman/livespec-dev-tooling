---
proposal: the-delegated-gate-client-polls.md
decision: modify
revised_at: 2026-11-12T11:16:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The terminal-state wait is accepted as graded PASS by legacy-coordinator-agent (livespec-dev-tooling#4266): the gate client blocks on a bounded watch instead of a 10-second poll, bounds every kubectl call under the runner's stall window, and renews the progress stamp in-process so a long Job is never ended by the runner (the cause of the #4177 revert). A pre-review doctor pass walked it through `gate-run.sh` and `gate_remote_admission.py` and confirmed `LIVESPEC_GATE_RUN_PROGRESS_STAMP` matches the code, but found the 240-second window unsatisfiable once the stall window is overridden to 240 s or less, a loophole where a lapsed watch window counted as a timed-out request, a re-arm rule that ignored the admission wait's own bound, and a scenario Given naming a venue where gate-run.sh applies no stall bound. The modifications fix each; the independent sonnet review returned NO BLOCKERS on the exact bytes. No design record is contradicted.

## Modifications

Relative to the proposal: (1) the per-window limit's exception covers only a request that failed or hit its request bound before its watch window ended; (2) a watch window is at least 240 seconds, or 60 seconds shorter than the stall window when that is shorter, never shorter than 30 seconds, and a stall window under 90 seconds is not supported for a delegated wait; (3) a timed-out call re-arms within the bound of the wait it is on (the admission bound or the poll budget); (4) a spec-first note names livespec-dev-tooling-ie7fas; (5) the first scenario's Given is a `git push` run through `gate-start` whose pre-push hook delegates its gate, and its window line no longer restates the 240 s figure; (6) the second scenario ends within the admission bound or poll budget of the wait it is on.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-12T11:15:31Z
verdict: NO BLOCKERS
proposal_stem: the-delegated-gate-client-polls
content_digest: df4783c01b437f6fff0a104b969fc6097982f8b7d6bc7d665d3076800afb9564
