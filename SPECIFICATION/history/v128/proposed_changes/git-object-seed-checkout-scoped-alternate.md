---
topic: git-object-seed-checkout-scoped-alternate
author: claude-opus-5-5
created_at: 2026-11-04T08:41:13Z
---

## Proposal: Scope the git object seed's alternate to the checkout repository, never the job environment

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

The git object seed clause of §"Runner-pool build cache tiers" **Tiers** and its scenario currently require the pool to name the seed in the job container's `GIT_ALTERNATE_OBJECT_DIRECTORIES`. That variable reaches every git process the job runs, so a git repository a job creates outside its checkout (as test suites do) silently resolves the seed's objects too and reads the wrong commits. This proposal moves the alternate into the checkout repository's own object store, forbids naming the seed in the job environment, and adds the isolation property as a stated requirement and a scenario step.

### Motivation

Lever 2 of plan ci-cache-optimization went live on 2026-11-04 (combined apply 06:14:52-06:29:21Z) exactly as v127 states it, and broke CI on seeded runners: five tests/livespec_dev_tooling/test_git_object_seed.py tests failed in this repository's check-per-file-coverage job (PR #3364, run 41787616531, job 126433268685), and four orchestrator test_needs_human_stage_cause_and_open_red_gate.py tests read the wrong commit SHA from their own temporary repositories (orchestrator master red at 7d743d1 and 86acde3, seeded runners only). The failure reproduced on the dev host with the variable pointed at a real objects directory and vanished without it. The fleet kill switch was set and PR #3348 was reverted server-side (#3366, 28b206f5). The re-land (livespec-dev-tooling-qyrmwe) needs a mechanism the ratified text forbids, because the text names the job-environment variable; it is spec-change tier until this revision lands. Rollout note, not a requirement of this clause: the re-land MUST ship its hook as a NEW versioned ConfigMap key and MUST NOT edit or remove a key that a live runner pod mounts, because the 28b206f5 revert's converge deleted git-seed-hook.js from under running pods and failed their teardown (orchestrator PR #4359). That ordering is owned by livespec-dev-tooling-4oeffe (versioned hook ConfigMap per content hash), which blocks qyrmwe.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool build cache tiers", in the **Tiers** paragraph, replace the two sentences

> For a job on a node that holds the tree, the pool MUST set `GIT_ALTERNATE_OBJECT_DIRECTORIES` in the job container to the seeded object directory of the job's own repository, from the pool's runner container hook and never from a workflow step. The pool MUST set it only when that directory exists in the job's work volume.

with

> For a job on a node that holds the tree, the pool MUST attach the seeded object directory of the job's own repository as a git alternate of that job's checkout repository only, recorded in the checkout repository's own object store (its `objects/info/alternates`), from the pool's runner container hook and never from a workflow step. The pool MUST attach it only when that directory exists in the job's work volume. The pool MUST NOT name the seed in the job container's environment, in `GIT_ALTERNATE_OBJECT_DIRECTORIES` or in any other variable or configuration git reads outside the checkout repository, because an alternate scoped to the job's environment reaches every git process the job runs. A git repository the job creates outside its checkout MUST resolve only its own objects.

Every other sentence of the git object seed clause is unchanged.

In `SPECIFICATION/scenarios.md` §"Scenario: a routed job's checkout fetches only the objects its git object seed lacks, and falls back to a full fetch when the seed is missing" (the H2 heading is unchanged, so `tests/heading-coverage.json` needs no edit), replace the step

> Then the job container MUST name that repository's seeded object directory in `GIT_ALTERNATE_OBJECT_DIRECTORIES`, set by the pool's runner container hook

with the two steps

> Then the checkout repository's own object store MUST name that repository's seeded object directory as its git alternate, placed by the pool's runner container hook, and the job container's environment MUST NOT name the seed
>
> And a git repository the job creates outside its checkout MUST resolve only its own objects, so a commit it reads by its own ref is the commit it wrote

The remaining steps of the scenario are unchanged.
