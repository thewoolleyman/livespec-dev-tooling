---
topic: a-runner-only-node-posture
author: claude-opus-5-5
created_at: 2026-11-03T00:01:37Z
---

## Proposal: A runner-only node posture that opens a pool node to CI runners without storage tiers

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a third node CI-facilities posture, `runner-only`, beside `full` and `none` in §"Runner-pool node rebuild recipe". A runner-only node takes CI runner pods at its declared admission capacity, but declares no physical volume, volume group, logical volume or storage tier, so opening it never repartitions its disks. It provisions runner work volumes on an existing mount its profile names, gets the runner container hook, reads the pool's host-served caches over the node network, and starts its jobs with no seeded tree. Add one scenario per load-bearing behaviour.

### Motivation

hp-xubuntu (16 cores) sits closed to CI, said three ways the profile parser cross-checks: CI_NODE_FACILITIES=none, ADMISSION_CAPACITY_C=0 and a node-role/ci=factory:NoSchedule taint. Measured 2026-11-02 at about 23:55Z, hp ran 3 factory sandboxes at 3.6 cores (24%) and 2.5 GiB, while gmktec read 96% CPU, poweredge 98%, and 26 ARC runners sat SchedulingGated by Kueue's churn-slot admission. The maintainer directed that hp carry CI load. The only committed route to open a node is `full` with declared tiers. That makes the bare-metal stage create volumes on hp's disks, which carry no free space (the 160 GiB sandbox swap and the 3.6 TiB sandbox-stores volume holding k3s's data directory). That route is irreversible on a live factory host. Fleet coordinator legacy-coordinator-agent ruled on 2026-11-03, under R301, for a REVERSIBLE posture instead. The ruling also requires the proposal to state how such a node meets §"Runner-pool build cache tiers", whose Scope says a cache needing a network round trip off the host does not satisfy that section. Implementation is tracked by livespec-dev-tooling-zreev4.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Runner-pool node rebuild recipe", insert a new paragraph after **One profile per node.**:

**CI-facilities posture.** A pool node's profile MUST declare exactly one CI-facilities posture, and the profile parser MUST refuse any other value, naming the key and the value it refused. The postures are:

- `full` — the node carries the role-labeled storage tiers of §"Runner-pool build cache tiers" **Storage placement**, a positive admission capacity, and no CI-closing taint.
- `none` — the node is closed to CI. It declares no tier, its admission capacity MUST be 0, and it MUST carry a CI-closing taint, because the capacity stops admission and only the taint stops the scheduler.
- `runner-only` — the node takes CI runner pods without carrying storage tiers. It MUST declare no physical volume, volume group, logical volume or tier. Its admission capacity MUST be a positive integer. It MUST carry no CI-closing taint. It MUST name, in its profile, an existing mounted directory that holds its runner work volumes.

The parser MUST refuse a profile whose capacity or taint contradicts its posture, naming the offending key. The bare-metal storage stage run against a `runner-only` profile MUST plan no mutating command and MUST say so. Moving a node between `none` and `runner-only` MUST be a profile edit plus the node-provisioning apply, and MUST NOT require the bare-metal stage, so the move is reversible by the same edit in reverse. Such a move is a profile change under **Rehearsed before trusted**. Because neither posture's storage stage plans a mutating command, that rehearsal MUST be the node-provisioning apply that takes the node from its prior posture to executing a job in its new one, recorded on the owning ledger item with the procedure revision and the profile it ran with. It MUST NOT require emptying the node's storage. A node's factory posture (`FACTORY_NODE`) is independent of its CI-facilities posture: a `runner-only` node MAY also be a factory node, and its factory sandboxes MUST still schedule on it by the `ci-runner.io/factory` label.

**What a runner-only node's jobs get.** On a `runner-only` node, the volume provisioner MUST provision each runner work volume under the directory the profile names, and MUST NOT provision it under a path the profile does not name. It MUST NOT seed a work volume from a warm tree, because the node carries no `ci-workvols` tier for a seed to live on. A job there therefore starts with no seeded tree (cold), which **Storage placement** already permits where a seed's filesystem dependence is unmet. The node's jobs MUST reach the pool's host-served caches (the dependency proxies and the shared compilation cache) over the node network. The node-provisioning stage MUST install the runner container hook on a `runner-only` node exactly as on a `full` one.

In §"Runner-pool build cache tiers" **Scope**, append after "a cache that requires a network round trip off the host does not satisfy this section.":

For this section, "the host" is the runner pool's cluster. A `runner-only` node (§"Runner-pool node rebuild recipe" **CI-facilities posture**) satisfies this section through the pool's host-served caches, read over the pool's node network, together with a cold start in place of a seeded tree. A cache served from outside the pool's own nodes still does not satisfy this section.

The Kueue admission derivation MUST state the cohort churn-slot quota as the sum of every pool node's declared admission capacity. A change to any node's capacity MUST update the committed quota and its derivation record in the same change.

In SPECIFICATION/scenarios.md, append:

## Scenario: a runner-only profile opens a node to CI without planning a storage change

Given a pool node profile declaring `CI_NODE_FACILITIES=runner-only`, `ADMISSION_CAPACITY_C=8`, no CI-closing taint, no physical volume, volume group, logical volume or tier, and a runner work-volume directory on an existing mount

When the bare-metal storage stage plans against that profile

Then the plan MUST contain no mutating command and MUST say that the posture declares no storage

And the profile parser MUST accept the profile

## Scenario: a runner-only profile that keeps its CI-closing taint is refused

Given a pool node profile declaring `CI_NODE_FACILITIES=runner-only` with `NODE_TAINTS` carrying a `node-role/ci` record

When the profile parser reads it

Then the parser MUST exit non-zero with a message naming `NODE_TAINTS`

## Scenario: a runner-only profile with zero admission capacity is refused

Given a pool node profile declaring `CI_NODE_FACILITIES=runner-only` with `ADMISSION_CAPACITY_C=0`

When the profile parser reads it

Then the parser MUST exit non-zero with a message naming `ADMISSION_CAPACITY_C`

## Scenario: a runner work volume on a runner-only node is provisioned under the profile's directory and starts unseeded

Given a converged `runner-only` node whose profile names a runner work-volume directory

When the volume provisioner provisions a runner work volume on that node

Then the volume MUST be created under that directory

And the volume MUST carry no seeded warm tree and MUST be writable by the runner

## Scenario: the cohort churn-slot quota equals the sum of the nodes' declared capacities

Given the committed pool node profiles

When the Kueue cohort churn-slot quota is read from the committed manifests

Then it MUST equal the sum of every pool node profile's `ADMISSION_CAPACITY_C`
