---
proposal: fleet-arc-runners-git-object-seed.md
decision: accept
revised_at: 2026-11-03T23:52:10Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-cache-optimization
---

## Decision and Rationale

Accept, decided by legacy-coordinator-agent under the delegated decision mode (2026-11-03, as with v126). The decision rests on measured evidence in plan ci-cache-optimization research 004 and 005: the fetch is 56% of Checkout + Post Checkout time on k3s; a forge fetch with the default-branch objects as an alternate takes about 1 s on every node, against 6.5-7.7 s on loaded poweredge, where a redirected local mirror is no faster; and GIT_ALTERNATE_OBJECT_DIRECTORIES transfers 0 KB against 35 MB. The tier is additive. It falls back to a normal fetch, runs cold on runner-only nodes, sits under the kill switch, and needs no Trust by construction carve-out. Adds the governing scenario, its spec-first heading-coverage TODO row (integration tier or above, owned by livespec-dev-tooling-dciyg5), and the regenerated coverage-debt register entry. The independent review raised one non-blocking note for the implementation to settle: whether a work volume holds every repository's seed or only its own job's. livespec-dev-tooling-dciyg5 carries that question.

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
reviewed_at: 2026-11-03T23:50:54Z
verdict: NO BLOCKERS
proposal_stem: fleet-arc-runners-git-object-seed
content_digest: 0fec9ca712b420fc4fd5c510b32b17ad24fe1536281f4afcc9449adac9bb3bee
