---
topic: fleet-conformance-and-manifest-discovery
author: claude-fable-5
created_at: 2026-06-12T09:20:00Z
---

## Proposal: fleet-conformance-and-manifest-discovery

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Realign this library's local spec with the livespec family contract
accepted as livespec v108 (`livespec/SPECIFICATION/
non-functional-requirements.md` §"Fleet membership contract"):
§"Sibling discovery" moves from topic-search-as-sole-source-of-truth
to manifest-driven membership (livespec core's `fleet-manifest.jsonc`,
fetched from livespec master at run time) with the `livespec-sibling`
topic demoted to a discovery safety net; `reusable-release-dispatch.yml`
gains a documented BLOCKING fleet-conformance preflight; and the new
fleet surface (`livespec_dev_tooling/fleet/`: the shared obligation
table in `contract.py`, the `fleet_conformance` assert CLI, and the
operator-invoked `wire_fleet_member` reconcile CLI) is documented as
part of the library inventory.

### Motivation

The family contract (livespec v108) states: "Both the release fan-out
and the fleet-conformance check MUST read the manifest — fetched from
livespec master at run time — with the GitHub `livespec-sibling` topic
demoted to a discovery safety net." This library's §"Sibling discovery"
still declares topic search the SOLE source of truth and forbids any
static registry. The two no longer agree; the family contract is
hierarchically authoritative, and the implementation (landed with this
proposal's sibling code change) now realizes it. Note the original
section's motivation is preserved, not violated: the member registry
lives in livespec CORE (fleet-level facts are core-owned), so adding a
new sibling still requires NO edits to this library's source — and the
register-first repo-birth procedure makes a half-wired new repo red
fleet CI rather than an invisible straggler.

### Proposed Changes

1. **§"Sibling discovery" rewrite.** The fleet member set is defined
   by livespec core's committed `fleet-manifest.jsonc` (repo root),
   fetched from livespec master at run time by both the release
   fan-out and the fleet-conformance check. The `livespec-sibling`
   topic remains REQUIRED on every member repo, but as a discovery
   safety net: the conformance sweep flags any owner repo matching
   `livespec-*` naming or carrying the topic that is NOT in the
   manifest. The "static registry file in this library is FORBIDDEN"
   rule is narrowed to its surviving intent: the member list MUST NOT
   live in this library (it lives in livespec core).

2. **§"reusable-release-dispatch.yml" behavior addendum.** Document
   the `fleet-preflight` job: the central fleet-conformance check runs
   against livespec-dev-tooling master BEFORE any `sibling-released`
   dispatch goes out, and the dispatch matrix `needs` it (fail-fast).
   Document the no-circular-gating guarantee: every conformance
   finding is fixable without a dev-tooling release or this fan-out
   running.

3. **Fleet surface inventory.** Document `livespec_dev_tooling/fleet/`
   as a non-canonical (central, not per-repo) surface: the shared
   obligation table (`contract.py`, one definition for both modes),
   `python -m livespec_dev_tooling.fleet.fleet_conformance` (assert
   mode; env lever `LIVESPEC_RUN_FLEET_CONFORMANCE`, wired into this
   repo's `just check` aggregate, its CI job, the scheduled
   `fleet-conformance.yml`, and the fan-out preflight), and
   `python -m livespec_dev_tooling.fleet.wire_fleet_member`
   (operator-invoked idempotent reconcile under `with-livespec-env.sh`;
   secrets flow env→stdin only).
