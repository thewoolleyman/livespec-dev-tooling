---
proposal: self-sourced-pin-reconciliation.md
decision: accept
revised_at: 2026-07-19T08:39:38Z
author_human: thewoolleyman <chad@thewoolleyman.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Accepted after an independent Fable-model adversarial review returned NO BLOCKERS on this exact payload. The first review round found two blockers, both fixed rather than waived: the draft defined a general self-sourced-pin class but wrote an operative clause covering only the fabro image tag, while the repository also carries four self-sourced `uses:` refs into its own reusable workflows (running the walk while fixing this surfaced a fourth beyond the three the review named); and the closing sentence claimed the drift was never caught and widened monotonically, which contradicted the unamended freshness contract and leaned on an acknowledged implementation defect. A third finding, the paragraph-2 perpetuation claim, is addressed by a second replace-target. Two wording corrections the re-review flagged inside ratified text were applied before accepting: a wrong-direction cross-reference and an inverted delay bound; neither changes a requirement. Fidelity verified programmatically: each FIND occurs exactly once, each REPLACE is insertion-only with preserved clauses byte-identical, the two targets do not interfere in either order, and the heading set is unchanged so no tests/heading-coverage.json co-edit is required.

## Resulting Changes

- contracts.md
