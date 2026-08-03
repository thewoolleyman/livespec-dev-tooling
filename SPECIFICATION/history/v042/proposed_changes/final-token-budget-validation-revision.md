---
proposal: final-token-budget-validation.md
decision: modify
revised_at: 2026-08-03T05:34:17Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: codex-gpt-5
---

## Decision and Rationale

Accept the measured contract correction with one structural modification: revise owns only files within SPECIFICATION, while the heading-coverage registry remains an implementation-side companion in the same pull request.

## Modifications

Removed tests/heading-coverage.json from target_spec_files because revise result paths are spec-target-relative and cannot write outside SPECIFICATION; the required heading-coverage entry remains co-edited in the same branch and PR.

## Resulting Changes

- spec.md
- contracts.md
- scenarios.md
