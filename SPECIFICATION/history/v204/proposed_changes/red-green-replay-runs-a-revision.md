---
proposal: red-green-replay-runs-a.md
decision: modify
revised_at: 2026-11-12T11:16:15Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

The one-run rule is accepted as graded PASS WITH TWO FIXES by legacy-coordinator-agent (livespec-dev-tooling#4259, both fixes already in the proposal): a test-only commit with no Red intent runs its staged test modules once, and in a delegating repository on an eligible host that one run is the gate Job. Pre-review doctor passes walked it through `red_green_replay.py` and `_red_green_replay_suite.py` and found three conflicts with ratified text that the literal proposal would have created: **Scope** sends a test-only commit that also stages shared test support to the FULL suite, so 'once in total' could not hold there; the deciding run that fails proceeds to the Red leg, which reruns the tests, and the deciding run today uses a different invocation and Job size from the suite-green leg; and the proposal's unconditional 'a pytest process MUST NOT start on the committing host' read against **Absent verdict**'s local fallback. A stall-ended deciding run also needed a defined route. The modifications resolve each; the independent sonnet review returned NO BLOCKERS on the exact bytes. No design record is contradicted.

## Modifications

Relative to the proposal: (1) the rule is limited to commits that stage no shared test support (**Scope.**); (2) the deciding run is made as the suite-green leg's run, with that leg's invocation, **Progress bound** and, when delegated, a suite-green-sized Job (**Replay Job size**); (3) on a pass it IS the suite-green run and the staged modules are not run again; on a failure the commit proceeds to the Red leg as before and that run emits no suite-green outcome event; (4) a run ended by the **Progress bound** refuses the commit as that bullet states and does not proceed to the Red leg; (5) when the delegated Job returns no verdict, **Absent verdict** applies unchanged and the local run is then the one run; (6) the trailers and the staged-tests scope are recorded on a pass; (7) a spec-first note names livespec-dev-tooling-fjpqqq; (8) both scenarios' Given now says the commit stages no shared test support.

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
proposal_stem: red-green-replay-runs-a
content_digest: ad51563b610dba65fed189119ba8823d51e780498b98a1339f8e0ec2012298aa
