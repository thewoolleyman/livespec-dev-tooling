---
proposal: retention-held-session-liveness.md
decision: accept
revised_at: 2026-11-10T11:06:55Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:dev-host-disk-retention
---

## Decision and Rationale

Accepted as written. The dev-host-disk-retention plan (livespec-dev-tooling-qgwxo4) measured on vmi3006760 on 2026-11-10 that the Claude Code main process never carries CLAUDE_CODE_SESSION_ID (0 of 31), so the clause's environment-only liveness keeps a live session only through its optional playwright MCP child (31 of 31). A live session whose child has died, with a directory older than the scratch retention period, would have its scratchpad removed by the daily timer. Every Claude Code process holds an open file descriptor beneath its own session directory, so the amended clause adds the held-directory signal and keeps the environment signal. That only narrows removals within the clause's existing "only when". legacy-coordinator-agent routed the decision to this plan and accepted the interim (a pre-firing tripwire, no guard) until the implementation ships. Placement follows the boundary litmus: host retention is contributor-only infrastructure, so the clause stays in non-functional-requirements.md beside the other retention bullets, and the new keep behaviour carries its own scenario. The independent sonnet review of these exact bytes found no blockers. livespec-dev-tooling-ovnrsv implements the change and owns the scenario's owed test.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-10T11:06:54Z
verdict: NO BLOCKERS
proposal_stem: retention-held-session-liveness
content_digest: d344cd388289eefbf49dffe33da4fa473051c54c05d12817643d0a3af8561e39
