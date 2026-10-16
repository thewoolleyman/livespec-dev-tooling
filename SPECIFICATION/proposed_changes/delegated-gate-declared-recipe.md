---
topic: delegated-gate-declared-recipe
author: claude-opus-5-5:factory-worker-nodes-gitops
created_at: 2026-10-16T23:57:46Z
---

## Proposal: the delegated gate runs the consumer's declared recipe and reports a missing one red

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Add a bullet to §"Delegated pre-push gate", immediately after **What the delegated gate runs.** It says the gate Job runs the check recipe the consuming repository declares for its gate, never a recipe only this repository declares. When the consumer does not provide that recipe, the Job reports a red verdict that names it, never a green one.

### Motivation

The shared gate Job's pod command in ci-runner/k3s/phase2/gates/gate-job-template.yaml is hardcoded to this repository's own recipes (`just install-worktree-pack`, `just warm-typecheck`, `just hook_gate=1 check`). Any consuming repository without them is red on every green tree. livespec-orchestrator-beads-fabro bd-ib-26deyw had to ship its cluster-Job janitor switched off because of it (freeze-driver ruling R88). The fix is livespec-dev-tooling-saxz. §"Delegated pre-push gate" already says the Job runs 'the same `just check` target set the local fall-through runs', which is the consumer's own. It says nothing about a consumer that lacks the recipe, so saxz's second assertion has no governing clause.

### Proposed Changes

In `SPECIFICATION/contracts.md` §"Delegated pre-push gate", insert the following bullet immediately after the bullet that begins `- **What the delegated gate runs.**`:

- **The consumer's own recipe, and a missing one.** The gate Job MUST run the check recipe that the consuming repository declares for its gate (its `just check` when it declares no other), and MUST NOT run a recipe that only this repository declares. When the consuming repository does not provide its declared recipe, the gate Job MUST report a red verdict whose detail names the missing recipe. It MUST NOT report green, and it MUST NOT fall back to a recipe the consumer did not declare.

## Proposal: scenario: a delegated gate Job for a repository missing its declared recipe reports red naming the recipe

### Target specification files

- SPECIFICATION/scenarios.md

### Summary

Add a scenario stating that behaviour end to end, as the authoring discipline requires for a load-bearing clause.

### Motivation

The defect this governs was observable only as 'red on every green tree' in a consumer, and the scenario makes the missing-recipe verdict the observable trigger.

### Proposed Changes

In `SPECIFICATION/scenarios.md`, append the following scenario after the last existing scenario:

## Scenario: a delegated gate Job for a repository missing its declared recipe reports red naming the recipe

Given a consuming repository that switches delegation on and declares a check recipe for its gate

And the committed tree at the pushing worktree's `HEAD` does not provide that recipe

When the gate client submits the gate Job for that tree

Then the gate Job MUST report a red verdict whose detail names the missing recipe

And the gate Job MUST NOT have run any recipe that only livespec-dev-tooling declares

And the push MUST be refused, never completed
