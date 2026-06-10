---
proposal: absorb-compat-schema-and-semver-discipline.md
decision: accept
revised_at: 2026-06-10T21:58:02Z
author_human: Test <test@example.com>
author_llm: claude-fable-5
---

## Decision and Rationale

Both proposals land obligations livespec core explicitly delegated to this repository. Proposal 1 absorbs the consumer compat-block schema and bump-pin policy that livespec v103 (decision-record item 3) relocated here and v104 reduced to a pointer at this spec — without this section the family contract is circular, with livespec pointing here and this spec's automation-surface preamble pointing back at livespec. Proposal 2 creates the contracts.md §"Semver discipline" home that livespec/SPECIFICATION/contracts.md §"Shared code sync — livespec-dev-tooling" mandates, relocating the canonical surface enumeration from constraints.md (heading retained as a pointer so the constraints.md H2 set is unchanged), extending it to the [tool.livespec_dev_tooling] consumer-configuration key set, and fixing the three in-file cross-references that cited the old location. The accompanying tests/heading-coverage.json co-edit adds TODO entries for the two contracts.md H2 additions per the repo's revise co-edit discipline.

## Resulting Changes

- contracts.md
- constraints.md
- ../tests/heading-coverage.json
