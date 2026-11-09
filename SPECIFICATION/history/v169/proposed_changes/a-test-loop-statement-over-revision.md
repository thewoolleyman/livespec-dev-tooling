---
proposal: a-test-loop-statement-over.md
decision: modify
revised_at: 2026-11-09T17:07:49Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude:fleet-flaky-tests
---

## Decision and Rationale

Modified under delegated mode (wording only). A for loop over os.environ makes a test file's coverage depend on the host: on livespec-dev-tooling-jd4qle the same tree read 0 missed in the factory sandbox and 1 missed in PR CI run 42535463884. The rule has no exemption, per legacy-coordinator-agent's ruling that an unconditioned coverage pragma is an agent-writable carve-out. It also states the release order that keeps the canonical check from being armed before its consumers adopt the shape (the 46c5dab / f4247110 lesson). Implementation item: livespec-dev-tooling-dpkz32. The independent read-only reviewer (sonnet) found no blockers on the exact bytes.

## Modifications

"single expression statement" became "single simple statement, such as an assignment of a comprehension" in the bullet, and the scenario's "one expression statement" became "one simple statement". The scenario's own rewrite, `_ = [...]`, is an assignment statement. Coverage counts any simple statement under its first line, so the rule's reason holds unchanged. The headings are unchanged.

## Resulting Changes

- non-functional-requirements.md
- contracts.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-09T17:07:12Z
verdict: NO BLOCKERS
proposal_stem: a-test-loop-statement-over
content_digest: f48c2cee9f8aef97a2e10e5491a379692558dff5af00a452233e205e1df09472
