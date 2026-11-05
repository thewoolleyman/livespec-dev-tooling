---
proposal: agent-session-guard-refuses-foreground-full-suite-pytest.md
decision: modify
revised_at: 2026-11-05T02:05:03Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:dev-host-test-gate-load
---

## Decision and Rationale

Accepted in delegated mode by seat dev-host-test-gate-load (plan dev-host-test-gate-load, epic livespec-dev-tooling-6vuiwe). legacy-coordinator-agent ruled under R301 on 2026-11-05 that the A6 carrier livespec-dev-tooling-4pchid implements this clause, so 4pchid waits on its ratification. A6 windows 2 and 3 (research notes 007 and 008) measured foreground pytest-xdist runs in agent worktrees at 2.6-6.6 cores on the dev host, a path neither the guard nor gate-start routing covered, and a full suite spelled  ran host_local as 'command outside full-suite set'. The clause closes both: the guard refuses a foreground full-suite pytest on a delegating host and names gate-start, and the runner and guard share one pytest definition covering every spelling. An independent read-only sonnet reviewer found NO BLOCKERS on the exact bytes.

## Modifications

Wording only. The guard bullet adds one sentence: the guard's narrower full-suite reading (no named test file, directory or node id, or -n/--numprocesses) is the guard's alone, and a targeted pytest dispatched through gate-start is still a full-suite gate command under the gate-runner section, which counts every pytest invocation. This removes a terminology clash between the two sections without changing either rule. The 'What is not refused.' list was rephrased so its final 'or' moves to the last of the three appended exemptions. The scenarios use this repository's blank-line-separated Given/When/Then style. No rule was added or dropped.

## Resulting Changes

- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-05T02:03:55Z
verdict: NO BLOCKERS
proposal_stem: agent-session-guard-refuses-foreground-full-suite-pytest
content_digest: fdd7c94e3e34d6fe60e5396c007003c796e4077ad06bc6c191966e4e3b7fdb21
