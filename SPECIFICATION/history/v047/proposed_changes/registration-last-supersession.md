---
topic: registration-last-supersession
author: claude-fable-5-bootstrap-pi-driver-orch
created_at: 2026-08-16T01:02:52Z
---

## Proposal: Rewrite register-first statements to registration-last (birth-procedure supersession)

### Target specification files

- SPECIFICATION/contracts.md

### Summary

livespec core ratified v210 (2026-08-16): the repo birth procedure is now registration-LAST — a fleet-manifest entry lands only after the repository exists, is clonable, and has reached membership-independent readiness, with the reconcile CLI run immediately after registration. Two statements in this repo's contracts.md restate the superseded register-first ordering; both are rewritten. The declared-before-wired mechanic of the reconcile mode is UNCHANGED — this is prose supersession only, with no behavior change to wire_fleet_member and no heading changes.

### Motivation

On 2026-08-15 a fleet-manifest entry registered before its repository existed (livespec-driver-pi) turned fleet-manifest consumption into a clone failure on every dispatch of the reference orchestrator, with a misleading credential-prompt failure shape. The maintainer directed registration-last on 2026-08-16 and livespec core ratified it as v210 in SPECIFICATION/non-functional-requirements.md, Fleet membership contract, moving the invisible-straggler visibility rationale to the Discovery safety net rule. This repo's contracts.md carries the fleet's only remaining ratified restatements of the old ordering (surfaced by the independent adversarial review of the core proposal; tracked here as work-item livespec-dev-tooling-47s0). Leaving them would have two ratified fleet specs stating opposite orderings with nothing recording the supersession.

### Proposed Changes

Two replacement edits in SPECIFICATION/contracts.md, both in the fleet sections; each target exists verbatim and exactly once in the live file. No heading is added, changed, or removed, so no tests/heading-coverage.json co-edit is required.

Edit 1 — §"Sibling discovery", final paragraph. Replace exactly:

```
the register-first repo-birth procedure (scaffold → register in the manifest FIRST → run the reconcile CLI → fleet conformance green) makes the half-wired interval loud instead of silent.
```

with:

```
livespec core's registration-last repo-birth procedure (create the repository → scaffold → membership-independent readiness → register in the manifest LAST → run the reconcile CLI → fleet conformance green) keeps a premature manifest entry from breaking manifest consumers, and the discovery sweep above keeps an unregistered repo loud instead of silent.
```

Edit 2 — §"Fleet surface — central conformance and reconcile", the Reconcile-mode bullet. Replace exactly:

```
Exits `1` when `--repo` is NOT in the manifest (register-first: a repo is wired only after it is a declared member).
```

with:

```
Exits `1` when `--repo` is NOT in the manifest (declared-before-wired: a repo is wired only after it is a declared member; under livespec core's registration-last birth procedure, registration immediately precedes this wiring step).
```

The reconcile mode's behavior is deliberately untouched: exiting 1 for an unregistered --repo remains correct under registration-last, because registration immediately precedes wiring.

Ratification ride-along (same PR, outside resulting_files): .ai/fleet-and-secrets.md carries "Register-first remains the governing shape: a repo is declared in the manifest before reconcile tooling treats it as a fleet member." — rewrite to registration-last while keeping the surviving declared-before-wired half.
