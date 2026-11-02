---
topic: interactive-fleet-seat-profile
author: claude-opus-5-5
created_at: 2026-11-02T17:45:55Z
---

## Proposal: Interactive fleet seat profile

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a non-functional section, ## Interactive fleet seat profile, requiring one committed seat profile in this repository that names each interactive fleet seat class's model, effort and context bound, read by every seat launcher on the dev host, with conformance observable in llm-spend; plus one scenario for the launcher behavior.

### Motivation

Interactive fleet seats (coordinator, monitor, plan and loop sessions launched on the dev host) are about 80% of the fleet's Anthropic spend in livespec/llm-spend (anthropic-burn-mitigation, epic bd-ib-b2jzxw, measured 2026-11-02: about $1,564 in 24 h, $1,249 of it local opus-5.5 sessions at medium effort). Every seat is launched today with its model hard-coded in the launch command and no committed effort or context bound, so lowering the cost of a class of seats takes an edit to every launcher and cannot be checked. Work items livespec-dev-tooling-3fxp3u (model and effort profile) and livespec-dev-tooling-jwmsk6 (context bound) carry the change, and both are held out of ready by a mechanical Definition-of-Done finding because no heading of this specification governs it. The section is contributor-only fleet infrastructure (a project governed by livespec inherits nothing from it), so it belongs in non-functional-requirements.md. The profile's values (which model, which effort, which bound) are the maintainer's call and are deliberately not fixed by the specification; the specification fixes only that there is one place to set them and that what runs matches it.

### Proposed Changes

Add to SPECIFICATION/non-functional-requirements.md, after §"LLM-spend telemetry pricing":

## Interactive fleet seat profile

**Scope.** This section governs the interactive fleet seats this repository's tooling launches on the dev host: the long-lived Claude Code sessions that coordinate, monitor, drive a plan or run a loop on the maintainer's behalf, as distinct from factory runs, which §"Fabro factory host provisioning" and the factory's own configuration govern. It fixes where a seat's model, effort and context bound are set and how conformance is observed. It does not fix their values, which are the maintainer's call.

**One committed profile.** This repository MUST carry ONE committed fleet seat profile that names, for each seat class it defines (at least one class for coordinator and monitor seats and one for implementing seats), the model, the reasoning effort and the context bound a seat of that class runs with. The context bound MUST state the auto-compact threshold, and it MUST be set below the model's context ceiling. For a loop or monitor class it MUST also state a bounded lifetime after which the seat writes a ledger-held handoff and is replaced by a fresh session. Changing a value for a class MUST be one edit to the profile.

**Every launcher reads it.** Every committed launcher of an interactive fleet seat on the dev host MUST take the seat's model, effort and context bound from the profile, for the class named at launch, and MUST NOT carry a model, effort or context bound of its own. A launch that names a class the profile does not define MUST be refused before any session starts, naming the class.

**Observable in llm-spend.** The model and effort a seat runs with MUST be the ones its class names in the profile, and they appear as `spend.model` and `spend.effort` on that seat's responses in the `llm-spend` dataset, so conformance MUST be judged there and not from the launch command alone.

Add to SPECIFICATION/scenarios.md, after the scenario on fallback-priced responses:

## Scenario: an interactive seat launched by class runs with the model and effort its profile class names

Given the committed fleet seat profile defines a class `monitor` with model `claude-sonnet-5-5`, effort `medium` and an auto-compact threshold below the model's context ceiling

When the committed seat launcher starts a seat of class `monitor`

Then the session MUST be started with model `claude-sonnet-5-5`, effort `medium` and that auto-compact threshold, taken from the profile

And a launch naming a class the profile does not define MUST be refused before any session starts, naming the class
