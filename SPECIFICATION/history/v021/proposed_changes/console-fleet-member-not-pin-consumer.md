---
topic: console-fleet-member-not-pin-consumer
author: claude-opus-4-8
created_at: 2026-06-27T01:36:58Z
---

## Proposal: Control-Plane fleet member exempt from the pin-and-bump shim web

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Introduce, in the pin-and-bump policy, the distinction between a pin-and-bump CONSUMER (a fleet member that carries the three shim workflows and participates in the automated release/bump web) and a NON-PIN-CONSUMING fleet member (one that carries a livespec-dev-tooling pin for its own toolchain but ships none of the three shims). The latter receives no bump-pin PR; its pin freshness is monitored centrally at warning severity by the dev-tooling-pin fleet-conformance obligation row rather than auto-bumped. The Control-Plane console (livespec-console-beads-fabro, the new `console` repo class) is the first such member.

### Motivation

Registering livespec-console-beads-fabro (livespec-zs22.7.8) adds the first fleet member that is NOT a full pin-and-bump consumer: per its M3 committed state it carries a [tool.uv.sources] livespec-dev-tooling pin (v0.22.0) for its `just check` toolchain but ships only ci.yml — none of the three pin-and-bump shim workflows (bump-pin-from-dispatch / pin-freshness / release-dispatch). The current pin-and-bump policy prose universally binds 'every sibling consumer ... and any future sibling' and asserts uniformity 'across every livespec-governed sibling repository', which the console contradicts. This carve-out makes the policy accurate without weakening it for genuine pin-and-bump consumers.

### Proposed Changes

Amend SPECIFICATION/contracts.md §"Consumer compat block — pin-and-bump policy" and §"Cross-repo coordination automation surface":

1. In the §"Consumer compat block — pin-and-bump policy" intro paragraph, add a sentence establishing that not every fleet member is a pin-and-bump *consumer*: a *non-pin-consuming* member carries a livespec-dev-tooling pin for its own toolchain but ships none of the three shim workflows and takes no part in the release/bump web (forward-referencing §"Bump-pin policy").

2. In §"Bump-pin policy", add a fourth bullet **Pin-and-bump consumers vs. non-pin-consuming members** stating: the preceding bullets bind every pin-and-bump consumer (a fleet member carrying the three shim workflows); a fleet member MAY instead be a non-pin-consuming member that carries a livespec-dev-tooling pin (asserted by the `dev-tooling-pin` fleet-conformance obligation row) but ships no shims, is sent no bump-pin PR, and has its pin freshness monitored centrally at WARNING severity by the `dev-tooling-pin` row's staleness leg rather than auto-bumped. The Control-Plane console (livespec-console-beads-fabro, the `console` repo class) is the first such member.

3. In the §"Cross-repo coordination automation surface" intro, qualify 'uniformly across every livespec-governed sibling repository' to 'uniformly across every pin-and-bump consumer repository', noting the non-pin-consuming members carved out in §"Bump-pin policy" carry none of this surface.

The class enumeration itself remains livespec-core-owned (the manifest + core's non-functional-requirements.md §"Fleet membership contract"); this change only records, in dev-tooling's own pin-and-bump policy, that a fleet member need not be a pin-and-bump consumer.
