---
proposal: dependencies-allow-vendored-returns-imports.md
decision: accept
revised_at: 2026-11-06T09:00:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:expedited-incident-response-flag
---

## Decision and Rationale

Accepted as filed, in delegated mode (revise_decision_mode: delegated, ratification_review: auto-spawn). Delegated decider: the session carrying work item livespec-dev-tooling-dpbpfx, on the route the coordinator (legacy-coordinator-agent) agreed to on 2026-11-06. Why: a released wheel of this library, installed into a clean environment, fails on import with `ModuleNotFoundError: No module named 'typing_extensions'`, because the vendored `returns` tree imports `typing_extensions` and `anyio` and the old rule forbade declaring any runtime dependency. The old rule existed so that a consumer pays no transitive pin cost; two lower-bounded, ubiquitous packages keep that cost near zero, while the old rule as written made every clean install fail. Vendoring `typing_extensions` instead was rejected because the library's pytest plugin puts `_vendor` on `sys.path` inside the consumer's own pytest process, where a vendored copy would shadow the consumer's version. The only resulting change is the first sentence of the first paragraph of constraints.md §"Dependencies"; the H2 heading set is unchanged. No design record is cited by that section and none is contradicted; the replaced sentence was the only ratified statement of the old rule. An independent read-only sonnet reviewer found NO BLOCKERS on these exact bytes. Its non-blocking notes: the named set (`typing-extensions`, `anyio`) can drift if the vendored tree changes, which a later propose-change would handle. The packaging change (`pyproject.toml`, `uv.lock`) and the test that asserts the rule against the packaging config follow in a separate pull request under the same work item; until it lands the packaging config still follows the old rule.

## Resulting Changes

- constraints.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-06T08:58:51Z
verdict: NO BLOCKERS
proposal_stem: dependencies-allow-vendored-returns-imports
content_digest: 6abbb29ff6f77e426cc85aa7b83bf5b0269b08d399640e32721535387b1f3c2c
