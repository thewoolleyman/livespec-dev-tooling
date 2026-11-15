---
proposal: the-flake-retry-closure-retries.md
decision: accept
revised_at: 2026-11-15T00:45:17Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:throughput-plans-coordinator-helper
---

## Decision and Rationale

Accepted as written. legacy-coordinator-agent pre-graded this proposal ACCEPT under the maintainer's delegated revise authority (R301). It makes the Untouched-test retry closure analysis attribute repository paths reached through pytest's request (by name, getattr, alias or a helper parameter), os.path.join/dirname, f-strings, Path.with_name and fixtures imported from another test module, and keeps a literal-only module-level name chain determinate; three scenarios cover the cases. It composes with v228's base sentence, which it leaves untouched. Carrier: livespec-dev-tooling-k3lpwj. Re-cut on the installed livespec build 9106ef675f5f; supersedes livespec-dev-tooling#4735.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T00:44:57Z
verdict: NO BLOCKERS
proposal_stem: the-flake-retry-closure-retries
content_digest: 18bdbb8ee1bfae0e7bd0b98b51c8b1c5dce6aa59172b775827c3418c7c66b744
