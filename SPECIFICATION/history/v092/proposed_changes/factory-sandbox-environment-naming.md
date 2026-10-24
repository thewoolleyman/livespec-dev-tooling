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

**Scope.** This section governs the `id` of every sandbox environment declared by a `fabro_server_instances` mapping that a `fabro_factory_registry` entry names and whose `service_state` is `running`. It does not govern a canary or candidate instance that no `fabro_factory_registry` entry names, an instance whose `service_state` is `stopped`, or a server's seeded default environment. It also does not govern the images, the resources or the provider of an environment; §"Fabro factory host provisioning" governs those.

**The id names the consumer and the toolchain.** Each such environment's `id` MUST be `factory-<toolchain>`. Here `<toolchain>` names the toolchain layer of the sandbox image the environment runs, written without its `-agent` suffix: `factory-python` for the `python-agent` layer, and `factory-python-rust` for the `python-rust-agent` layer. For an environment that declares no `image`, the image is that of its provider's `process_spec`. Outside a rename in progress, one such mapping MUST NOT declare two environments whose images carry the same toolchain layer. From the first step of a rename until its third step completes, the mapping MAY declare every old `id` being renamed beside the new `id`.

**Placement is never in the id.** An `id` MUST NOT encode where or how the sandbox runs (for example `docker`, `k8s` or `kubernetes`), because that is the environment's `provider` field. Moving an environment to another provider, a rollback between providers included, therefore changes its `provider` and never its `id`. No governed repository's committed configuration changes with it. Because a provider carries one `process_spec`, two toolchains on one provider kind SHOULD take two providers (for example `kubernetes` and `kubernetes-rust`), never a placement suffix on the id.

**What names an id.** A governed repository's committed configuration names an environment `id` through its `dispatcher.factories.<name>.environment`, and the factory registry names one through any entry that supplies an `environment`, should the registry carry one. A workflow's `[run.environment] id` and its `[environments.<id>]` tables are not consumers of a catalog environment, because the Petri engine never selects a workflow's environment tables. Renaming them is hygiene and is not a precondition of any step below.

**A rename adds before it removes.** Renaming an environment's `id` MUST proceed in three steps, and a step MUST NOT start before the previous one is complete.

1. The new `id` is added to the mapping's `environments` and to the instance's catalog, beside each old `id`, with the same image, resources and provider. When two old ids already declare the same toolchain layer, image, resources and provider, both are renamed to the one new `id`.
2. Every consumer that names an old `id` (as defined above) is moved to the new one.
3. Each old `id` is removed from the mapping's `environments` and deleted from the instance's catalog through `DELETE /api/v1/environments/{id}`, by the role or by a recorded operator step. Before each deletion, the role or the operator MUST confirm that no consumer names that `id`, and that no non-terminal run on that instance runs in it, by reading every non-terminal run that `fabro ps --server <instance>` lists, together with its environment. A declaration removed from the mapping while the catalog still holds that `id` MUST be reported as drift.

Insert into SPECIFICATION/scenarios.md:

## Scenario: factory sandbox environments are named for their toolchain, and a rename never strands a dispatch

Given a running, registry-named `fabro_server_instances` mapping declaring an environment `livespec-ci-k8s` whose image carries the `python-agent` layer, and governed repositories whose committed petri `environment` names it

When the environment is renamed

Then the catalog MUST list `factory-python` beside `livespec-ci-k8s` before any governed repository's committed `environment` names `factory-python`

And `factory-python` MUST carry the same image, resources and provider as `livespec-ci-k8s`

And `livespec-ci-k8s` MUST stay in the catalog while any governed repository's committed `environment` or any non-terminal run on that instance names it

And after the removal, the catalog MUST NOT list `livespec-ci-k8s`, and its only `python-agent` environment MUST be `factory-python`

Co-edit tests/heading-coverage.json in the same revise. Add a row for each new heading: `## Factory sandbox environment naming` in non-functional-requirements.md, and the new scenario in scenarios.md. Each row's `test` is `TODO`, with the reason "exercised by the implementing item livespec-dev-tooling-s6go5s".
