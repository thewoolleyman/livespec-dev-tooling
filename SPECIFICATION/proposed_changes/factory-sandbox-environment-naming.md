---
topic: factory-sandbox-environment-naming
author: claude-opus-5-5
created_at: 2026-10-24T02:21:07Z
---

## Proposal: Factory sandbox environment ids name the consumer and the toolchain, never the placement

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Add an H2 "## Factory sandbox environment naming" to non-functional-requirements.md, placed directly after §"Fabro factory host provisioning". It requires every sandbox environment that a `fabro_server_instances` mapping declares for factory work to carry the id `factory-<toolchain>`, with one id per toolchain, and it forbids the id from encoding placement. It also states the add-beside, move-every-consumer, remove-last rename sequence. Add one scenario exercising it, and the matching heading-coverage rows.

### Motivation

Maintainer direction 2026-10-24, relayed by coordinator gitops-fleet-capacity-monitoring: "Proper naming is important." The gmktec catalog's ids livespec-ci, livespec-ci-rust and livespec-ci-k8s name CI, yet every one of them is a dark-factory work sandbox; CI never selects them. Since livespec-ci moved to the kubernetes provider, the -k8s suffix distinguishes nothing, and an id that encodes placement must be renamed whenever the provider moves. Nothing in this specification governs these ids today, so the implementing item livespec-dev-tooling-s6go5s, which renames them, has no clause to reference.

### Proposed Changes

Insert into SPECIFICATION/non-functional-requirements.md, immediately before `## Fabro factory registry`:

## Factory sandbox environment naming

**Scope.** This section governs the `id` of every sandbox environment that a `fabro_server_instances` mapping in this repository's inventory declares for factory work, meaning an environment a governed repository's committed `dispatcher.factories.<name>.environment` may name. It does not govern a server's seeded default environment, and it does not govern the images, the resources or the provider of an environment, which §"Fabro factory host provisioning" governs.

**The id names the consumer and the toolchain.** Each such environment's `id` MUST be `factory-<toolchain>`, where `<toolchain>` names the toolchain layer of the sandbox image the environment runs, written without its `-agent` suffix: `factory-python` for the `python-agent` layer, and `factory-python-rust` for the `python-rust-agent` layer. The prefix `factory` states that the environment is a dark-factory work sandbox; a continuous-integration environment MUST NOT carry it. Each toolchain MUST have exactly one id, so two declared environments whose images carry the same toolchain layer MUST NOT carry different ids.

**Placement is never in the id.** An `id` MUST NOT encode where or how the sandbox runs (for example `docker`, `k8s` or `kubernetes`), because that is the environment's `provider` field. Moving an environment to another provider therefore changes its `provider` and never its `id`, and no governed repository's committed configuration changes with it.

**A rename adds before it removes.** Renaming an environment's `id` MUST proceed in three steps, and none may start before the previous one is complete. First, the new `id` is added to the catalog beside the old one, with the same image, resources and provider. Second, every governed repository's committed `environment` that named the old `id` is moved to the new one. Third, the old `id` is removed, and only once no governed repository's committed configuration and no non-terminal run on that server names it.

Insert into SPECIFICATION/scenarios.md:

## Scenario: factory sandbox environments are named for their toolchain, and a rename never strands a dispatch

Given a `fabro_server_instances` mapping declaring an environment `livespec-ci-k8s` whose image carries the `python-agent` layer, and governed repositories whose committed petri `environment` names it

When the environment is renamed

Then the catalog MUST list `factory-python` beside `livespec-ci-k8s` before any governed repository's committed `environment` names `factory-python`

And `livespec-ci-k8s` MUST stay in the catalog while any governed repository's committed configuration or any non-terminal run on that server names it

And after `livespec-ci-k8s` is removed, no declared factory environment's `id` encodes its placement

Co-edit tests/heading-coverage.json in the same revise, adding a row for each new heading (`## Factory sandbox environment naming` in non-functional-requirements.md, and the new scenario in scenarios.md). Each row's `test` is `TODO`, with the reason "exercised by the implementing item livespec-dev-tooling-s6go5s".
