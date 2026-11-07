---
topic: the-fabro-sandbox-image-publishes
author: claude-opus-5-5
created_at: 2026-11-07T17:05:05Z
---

## Proposal: Factory sandboxes on a homelab worker

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

A homelab worker runs factory sandboxes through its own Fabro server instance and a native python-agent image, and the sandbox image publishes that layer natively for arm64 under suffixed tags while every amd64 tag stays as it was.

### Motivation

Plan homelab-k8s-worker-nodes owes one representative factory sandbox task on macbook-m4-max-homelab-worker, and the spec states nothing about how a worker takes one. Measured 2026-11-07: every published python-agent tag is amd64-only, while the ACP adapters and bubblewrap a dispatch's implement, fix and review nodes need live only in that layer, so the arm64 python image cannot run a factory task. Routing is also settled by reading the code: the Dispatcher has no per-dispatch environment selection, so an environment is a property of the factory entry. Each worker therefore takes its own instance keeping the toolchain id, which §"Factory sandbox environment naming" already describes (the id names the toolchain, the provider says where the sandbox runs), with no exception to that section. A separate instance measures 18-39 MB idle on gmktec-xubuntu. The classifier placed work item livespec-dev-tooling-a3brdf at spec-change tier with this topic.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Homelab worker nodes", append this bullet after **Reviewed cluster changes.**:

- **Factory sandboxes on a worker.** A worker that takes factory dispatches MUST do so through one Fabro server instance of its own, declared as data like every other instance, and reached by a `fabro_factory_registry` entry and a repository's committed `dispatcher.factories` entry. That instance's catalog environment MUST keep the id §"Factory sandbox environment naming" requires. Its provider's plugin configuration MUST select the worker by its host label and architecture, MUST tolerate the worker class taint, and MUST take no topology spread, so its sandboxes run only on that worker. An instance that is not a worker's MUST NOT tolerate that taint, so no other factory's sandbox lands on a worker. The provider's image MUST be a `python-agent` layer built natively for the worker's architecture. The sandbox image workflow MUST build that layer on a native arm64 runner FROM the arm64 `python` digest the same run built, and MUST publish it under `-arm64` suffixed tags only: it MUST NOT merge `python-agent` tags into a multi-platform index, and each asset the layer fetches MUST be selected by the target architecture and verified against that architecture's committed digest, leaving the amd64 assets and digests unchanged.

In SPECIFICATION/scenarios.md, add these two scenarios after `## Scenario: factory sandbox environments are named for their toolchain, and a rename never strands a dispatch`:

## Scenario: a homelab worker's factory sandbox runs only on that worker

Given a host declares a Fabro instance for `macbook-m4-max-homelab-worker`, whose plugin configuration selects `homelab-worker.livespec.dev/host=macbook-m4-max` and `kubernetes.io/arch=arm64` and tolerates `homelab-worker.livespec.dev/class=worker:NoSchedule`

When the role renders that instance and every other instance on the host

Then the worker's instance MUST declare the catalog environment `factory-python`, on a provider whose image is a `python-agent` tag suffixed `-arm64`

And its rendered plugin configuration MUST carry that node selector and toleration and no topology spread

And no other instance's rendered plugin configuration MUST tolerate the worker class taint

## Scenario: publishing the native arm64 agent layer leaves every amd64 python-agent tag as it was

Given the sandbox image workflow on a master push touching the image tree

When its arm64 job and its multi-platform job run

Then the arm64 job MUST publish `python-agent-sha-<short>-arm64` FROM the arm64 `python` digest that run built

And the multi-platform job MUST NOT merge any `python-agent` tag

And the agent layer built for amd64 MUST fetch the same sccache and herdr asset names and verify the same digests as before this change

In tests/heading-coverage.json, add one entry per new scenario heading with `test` set to `TODO`, a non-empty reason naming the pull request that maps it, and `work_item` set to `livespec-dev-tooling-a3brdf`. No `## ` heading is removed. §"Factory sandbox environment naming" is unchanged.
