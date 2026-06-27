---
proposal: console-fleet-member-not-pin-consumer.md
decision: accept
revised_at: 2026-06-27T01:37:49Z
author_human: Test <test@example.com>
author_llm: claude-opus-4-8
---

## Decision and Rationale

Records, in dev-tooling's own pin-and-bump policy, that a fleet member need not be a pin-and-bump consumer. Registering the Control-Plane console (livespec-zs22.7.8) introduces the first non-pin-consuming fleet member: it carries a livespec-dev-tooling pin for its toolchain but ships none of the three shim workflows. The carve-out makes the universal 'every consumer' / 'every sibling repository' claims accurate without weakening them for genuine pin-and-bump consumers; the class enumeration itself stays livespec-core-owned.

## Resulting Changes

- contracts.md
