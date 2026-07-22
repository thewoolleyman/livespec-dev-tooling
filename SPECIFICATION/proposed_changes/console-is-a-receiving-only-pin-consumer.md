---
topic: console-is-a-receiving-only-pin-consumer
author: claude-opus-4-8
created_at: 2026-07-22T00:00:00Z
---

## Proposal: the Control-Plane console is a receiving-only pin consumer, not a non-pin-consuming member

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Corrects three sites in `SPECIFICATION/contracts.md` that describe the
Control-Plane console (`livespec-console-beads-fabro`, the `console` repo class)
as a *non-pin-consuming member* that "ships none of the three shim workflows",
and sweeps a fourth clause-lockstep drift the reclassification introduces. The
console is now a pin CONSUMER: it ships the two RECEIVING pin-and-bump shims
(`bump-pin-from-dispatch.yml` + `pin-freshness.yml`) and deliberately ships NO
`release-dispatch.yml`, because it produces no consumable release a sibling
could pin against. This is the PROSE half of the epic whose CODE half already
merged (dev-tooling PR #536, `484039d`): `_contract_rows.py` now carries
`_RECEIVING_SHIM_CLASSES = _PIN_WEB_CLASSES | {"console"}` for the two receiving
obligation rows (`workflow-bump-pin-from-dispatch`, `workflow-pin-freshness`),
while `workflow-release-dispatch` stays at `_PIN_WEB_CLASSES` (console excluded).
The amendment establishes a two-halves model — RECEIVING (getting a bump PR when
a source repo releases) versus PRODUCING (announcing this repo's own release) —
yielding three positions: full participant (all three shims), receiving-only
consumer (the console), and non-pin-consuming member (a defined possibility with
NO current fleet member).

### Motivation

Maintainer-authorized under livespec-oq9w Option B / Option (3). The console was
the ONLY cited example of a non-pin-consuming member ("the first such member"),
and it has moved to a different position: it now ships the two receiving shims,
so it is a *receiving-only consumer*, not a member that ships none of the shims.
Leaving the shipped code (PR #536) contradicted by the spec is impl→spec drift;
this proposal re-aligns the contract with the enforced obligation split.

The honesty point the amendment turns on: with the console reclassified, NO
current fleet member occupies the non-pin-consuming position. The enforced
class partition makes this exact: `_RECEIVING_SHIM_CLASSES` equals every class
(so every class ships the two receiving shims), and `_DEV_TOOLING_PIN_CLASSES`
is every class except `enforcement-suite` — so every member that carries a
`livespec-dev-tooling` pin also ships at least the two receiving shims. The
amendment therefore states the non-pin-consuming position as a DEFINED
POSSIBILITY WITH NO CURRENT OCCUPANT rather than naming a member, and removes
the "first such member" falsehood entirely.

Cross-references kept consistent: the console-class comment in
`livespec/.livespec-fleet-manifest.jsonc` (already amended to
"pin-CONSUMING ... ships the RECEIVING and FRESHNESS pin-and-bump shims ... NO
release-dispatch.yml") and the enforced `_contract_rows.py` split. The
amendment introduces no claim the code does not enforce.

### Proposed Changes

Four verbatim replace-targets in `SPECIFICATION/contracts.md` (each exists once
in the live file; re-verify against origin/master before applying). Targets A–C
are the three sites the reclassification directly falsifies; target D sweeps the
clause-lockstep drift that reclassifying the console AS a consumer introduces
into the same section's DRY-discipline sentence, which quantifies over "every
consumer" and so now includes the two-shim console.

=== Replace-target A (REQUIRED — §"Bump-pin policy" bullet, the PRIMARY site) ===

FIND (verbatim):
```
- **Pin-and-bump consumers vs. non-pin-consuming members.** The bullets above bind every pin-and-bump *consumer* — a fleet member that carries the three shim workflows (§"Cross-repo coordination automation surface") and so participates in the automated release/bump web. A fleet member MAY instead be a *non-pin-consuming member*: it carries a `livespec-dev-tooling` pin for its own developer toolchain (asserted by the `dev-tooling-pin` fleet-conformance obligation row) but ships none of the three shims, is sent no bump-pin PR, and has its pin freshness monitored centrally — at *warning* severity — by the `dev-tooling-pin` row's staleness leg rather than auto-bumped. The Control-Plane console (`livespec-console-beads-fabro`, the `console` repo class) is the first such member: it consumes `livespec-dev-tooling` for its `just check` toolchain yet ships no command/skill surface and no coordination shims.
```

REPLACE WITH:
```
- **Participation in the pin-and-bump web has two independent halves — receiving and producing.** The bullets above bind every pin-and-bump *consumer*, but participation is not all-or-nothing: it decomposes into a **receiving** half — getting an auto-opened bump-pin PR when a source repo publishes a release, carried by the two receiving shims (`bump-pin-from-dispatch.yml` + `pin-freshness.yml`, the `workflow-bump-pin-from-dispatch` and `workflow-pin-freshness` fleet-conformance obligation rows) — and a **producing** half — announcing this repo's OWN release so downstream siblings bump against it, carried by the `release-dispatch.yml` shim (the `workflow-release-dispatch` row, §"Cross-repo coordination automation surface"). Three positions result:
  - **Full participant** — ships all three shims, so it both receives and produces. This is the shape of most repo classes; the library itself is one (§"Self-hosting").
  - **Receiving-only consumer** — ships the two receiving shims but NOT `release-dispatch.yml`, because it produces no consumable release a sibling could pin against. It still receives a bump-pin PR for every pin it carries and keeps those pins fresh via its own `pin-freshness.yml`. The Control-Plane console (`livespec-console-beads-fabro`, the `console` repo class) is the first such member: it carries a `livespec` governance pin AND a `livespec-dev-tooling` toolchain pin, receives a bump-pin PR for each via its receiving shims, yet publishes no release, so ships no `release-dispatch.yml`. The obligation split enforces exactly this — the two receiving rows bind every class (the console included), while `workflow-release-dispatch` binds every class EXCEPT the console.
  - **Non-pin-consuming member** — carries a `livespec-dev-tooling` pin for its own developer toolchain (asserted by the `dev-tooling-pin` fleet-conformance obligation row) but ships NONE of the three shims, is sent no bump-pin PR, and has its pin freshness monitored centrally — at *warning* severity — by the `dev-tooling-pin` row's staleness leg rather than auto-bumped. This is a defined possibility with NO current fleet member: every present member that carries a `livespec-dev-tooling` pin also ships at least the two receiving shims (the `dev-tooling-pin` row binds every class except `enforcement-suite`; the two receiving rows bind every class), so the central-monitoring leg guards a shape the fleet does not currently occupy.
```

=== Replace-target B (REQUIRED — §"Consumer compat block — pin-and-bump policy" intro, clause-lockstep sweep) ===

FIND (verbatim):
```
Not every fleet member is a pin-and-bump *consumer*, however: §"Bump-pin policy" carves out *non-pin-consuming* members — fleet members that carry a `livespec-dev-tooling` pin for their own toolchain but ship none of the three shim workflows and so take no part in this release/bump web.
```

REPLACE WITH:
```
Not every fleet member participates identically in this web, however: §"Bump-pin policy" splits participation into a *receiving* half and a *producing* half, so a member MAY be a *receiving-only consumer* that ships the two receiving shims but not `release-dispatch.yml` — the Control-Plane console, which produces no consumable release — or a *non-pin-consuming member* that carries a `livespec-dev-tooling` pin for its own toolchain but ships none of the three shim workflows and takes no part in the release/bump web at all (a defined possibility with no current fleet member).
```

=== Replace-target C (REQUIRED — §"Cross-repo coordination automation surface" intro, the falsified console example) ===

FIND (verbatim):
```
uniformly across every pin-and-bump *consumer* repository (the non-pin-consuming fleet members carved out in §"Bump-pin policy" — e.g. the Control-Plane console — carry none of this surface).
```

REPLACE WITH:
```
uniformly across every pin-and-bump *consumer* repository. Participation is not all-or-nothing (§"Bump-pin policy"): a *receiving-only consumer* such as the Control-Plane console carries the two receiving shims (`bump-pin-from-dispatch.yml` + `pin-freshness.yml`) but not `release-dispatch.yml`, while a *non-pin-consuming member* — a defined possibility with no current fleet member — carries none of this surface.
```

=== Replace-target D (REQUIRED — §"Cross-repo coordination automation surface", DRY-discipline sentence clause-lockstep sweep) ===

Reclassifying the console AS a pin-and-bump *consumer* (target A) makes it a
counterexample to the DRY-discipline sentence in this same section, which
quantifies over "every consumer" and asserts each ships "three thin shim
workflows". The console ships two. Amend the count so it no longer implies
all-or-nothing.

FIND (verbatim):
```
Per the DRY discipline, every consumer's per-repo pin-and-bump coordination footprint is three thin shim workflows that delegate to the reusable workflows defined here; no coordination logic is duplicated across consumers.
```

REPLACE WITH:
```
Per the DRY discipline, a pin-and-bump *consumer*'s per-repo coordination footprint is the thin shim workflows that delegate to the reusable workflows defined here — three for a full participant, two for a receiving-only consumer such as the Control-Plane console that ships no `release-dispatch.yml` (§"Bump-pin policy") — with no coordination logic duplicated across consumers.
```

Heading-coverage co-edit: NOT required. All four targets edit prose (and add a
nested bullet list) within existing sections; no `## ` (H2) heading is added,
removed, or renamed, and `tests/heading-coverage.json` tracks only H2 headings.
So no `../tests/heading-coverage.json` entry is added to `resulting_files[]`.
