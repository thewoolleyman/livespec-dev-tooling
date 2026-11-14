---
topic: a-check-fails-when-a
author: claude-opus-5-5 (kubernetes-sandbox-backend)
created_at: 2026-11-08T14:39:48Z
---

## Proposal: Fabro catalog sandbox images stay in lockstep with the workflow image pins unless a hold is declared

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds a clause to non-functional-requirements.md section "Fabro factory host provisioning". Every sandbox image a Fabro instance's environment catalog names (each fabro_server_instances[] environments[].image and sandbox_providers.*.process_spec.image in the ansible inventory host_vars) MUST carry the same release version as the fleet's workflow image pin for the same image layer, unless a hold naming the work item that holds the divergence is declared beside that catalog entry. A just check member enforces it. The release fan-out MUST NOT rewrite catalog images, because a catalog image change is canary-first through the candidate instance. Adds three scenarios to scenarios.md.

### Motivation

On 2026-11-08 gmktec-factory-placement found, in the v0.305.1 canary, that the orchestrator's implement-work-item workflow pinned python-agent-v1.188.1 while the gmktec fleet instance's kubernetes process_spec image was still python-agent-v1.136.2. The inventory's own comment says the catalog, not the workflow table, decides the image on this engine, so the two must be bumped together. The coordinator's live read at about 13:58Z found all 18 factory pods on v1.136.2: no image release since v1.136.2 had reached a factory pod, and no check noticed. The release fan-out rewrites the workflow pins and deliberately never the catalog, since a catalog image change is canary-first with an environment-parity proof (livespec-dev-tooling-wrlwvk; PR #3794). So the two drift unless something compares them. The coordinator (legacy-coordinator-agent, R301) ruled the enforcing check, livespec-dev-tooling-pedcoq, spec-change tier: a fleet invariant the spec does not yet state. Fleet scope covers every member's catalog and every workflow image pin.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Fabro factory host provisioning", insert the following paragraph immediately after the paragraph that begins "**A plugin binary and every pin on it agree.**":

**Catalog sandbox images stay in lockstep with the workflow image pins.** Every sandbox image a Fabro instance's environment catalog names in this repository's ansible inventory — each `fabro_server_instances[]` entry's `environments[].image` and each `sandbox_providers.<kind>.process_spec.image` — MUST carry the same release version as the fleet's workflow image pin for the same image layer (the `<layer>-v<X.Y.Z>` tag the release fan-out writes into the consumers' workflow image pins), unless the divergence is DECLARED. A declared divergence is a hold recorded beside that catalog entry that names the work item holding it; a staged, canary-first image roll is expressed this way. A `just check` member MUST fail, naming the host_vars file, the Fabro instance, the catalog entry, its image tag and the workflow image pin it differs from, for every undeclared divergence; it MUST fail, naming the entry, for a declared hold that names no work item; and it MUST pass, listing each declared divergence with its holding work item, otherwise. The release fan-out MUST NOT rewrite a catalog image: a catalog image change is canary-first, through the candidate instance and an environment-parity proof against the fleet's current image, and an automatic rewrite would skip that step.

In SPECIFICATION/scenarios.md, add these three scenarios:

## Scenario: an undeclared catalog image divergence from the workflow image pin fails the check

Given a host_vars file whose Fabro instance's `sandbox_providers.kubernetes.process_spec.image` is `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-agent-v1.136.2`

And the fleet's workflow image pin for the `python-agent` layer is `python-agent-v1.188.1`

And no hold is declared beside that catalog entry

When `just check` runs

Then the catalog-lockstep member MUST fail

And its finding MUST name the host_vars file, the Fabro instance, the `kubernetes` provider entry, the tag `python-agent-v1.136.2` and the pin `python-agent-v1.188.1`

## Scenario: a declared hold naming its work item lets a catalog image diverge

Given the same catalog entry at `python-agent-v1.136.2` and the same workflow image pin at `python-agent-v1.188.1`

And a hold declared beside that catalog entry names the work item `livespec-dev-tooling-wrlwvk`

When `just check` runs

Then the catalog-lockstep member MUST pass

And its output MUST list the divergence with `livespec-dev-tooling-wrlwvk`

## Scenario: a declared hold that names no work item fails the check

Given a catalog entry whose image differs from the workflow image pin for its layer

And a hold declared beside that entry that names no work item

When `just check` runs

Then the catalog-lockstep member MUST fail, naming that catalog entry

The revise pass that accepts this proposal MUST add a `tests/heading-coverage.json` entry for each of the three new scenario headings (the `test` MAY be "TODO" with a reason naming livespec-dev-tooling-pedcoq, the carrier that implements the check).
