---
topic: homelab-worker-enrollment-takes-a
author: claude-opus-5-5
created_at: 2026-11-15T07:15:30Z
---

## Proposal: A homelab worker's measured per-class split is recorded in its host declaration, a zero share is named, and an invalid split is refused before any write

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

The "Derived per-class capacity" bullet already allows a measured split in place of the equal default, but it does not say where a split is recorded or what enrollment does with a zero share or a malformed split. This adds three rules. A split is recorded, with its reason, in the worker host's existing declared-host file, which is the only per-host input enrollment reads. A zero-share class holds no capacity and is named in the enrollment output. A split over one hundred percent, or one naming an unknown class, is refused before any write. Two scenarios state the behaviour.

### Motivation

Plan homelab-k8s-worker-nodes (epic livespec-dev-tooling-ko26ez), re-prioritized 2026-11-15 to balance load across every k3s node. macbook-m4-max-homelab-worker has 12 allocatable cpu and is enrolled in CI, gate and factory, so the equal default gives each class 4000m: 1 churn slot and 1 gate. No factory sandbox lands on the worker, because factory pods do not tolerate its class taint, so the factory third is stranded. At 2026-11-15 07:00Z the worker read 49.5% idle while poweredge-xubuntu and gmktec-xubuntu read 0.1% and 0.2% idle with CI-slice pressure above 30. A recorded split giving factory 0 and CI and gate 6000m each yields 2 churn slots and 1 gate. Raising a queue's arm64 quota without that capacity would promise slots no node has.

legacy-coordinator-agent ruled the split in-spec on 2026-11-15, with the M4's factory share recorded as 0 by measurement, so the 2026-11-07 every-container-node-auto-enrolls Definition of Done reads as satisfied by a recorded split, not skipped. It then held work item livespec-dev-tooling-dwewrc at the spec-change tier, because the bullet does not state how a split is recorded, that a zero share is named, or that an invalid split is refused. This proposal states those three rules. dwewrc is the implementation, filed alongside so it does not sit on an unfiled hold.

The bullet's sibling requirement, enrollment "with no per-host values file, profile, inventory entry or operator step", stays as it is: the split lives in the host declaration the start task already reads, and the new text says so. In-flight survey 2026-11-15: no open spec branch or pull request touches this bullet; spec/homelab-worker-live-load and spec/homelab-factory-sandbox date from 2026-11-07 and were ratified.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Homelab worker nodes", in the **Derived per-class capacity.** bullet, insert the following sentences immediately after the sentence that ends "one third each when it is enrolled in all three classes, one half each for two, and all of it for one.":

```
A measured split MUST be recorded in the worker host's own declaration, the one declared-host file the start task reads for that host (the host the worker's Node names in its host label), and that declaration MUST be the only per-host input enrollment reads; it is the declared host's data, not a per-host values file, profile or inventory entry. A recorded split MUST give each class a whole-percentage share of the worker's allocatable CPU and MUST record its reason beside the shares. Enrollment MUST derive each class's capacity from its recorded share in place of the equal default, with CI capacity still expressed in churn slots by the fleet's sizing rule, and the at-least-one-unit floor applies only to a share greater than zero. A class whose recorded share is zero MUST hold no capacity on that worker, and enrollment MUST name that class, its zero share and the recorded reason in its output, so a zero share reads as measured rather than skipped. Enrollment MUST refuse a recorded split whose shares sum to more than one hundred percent, or that names a class other than CI, gate or factory, naming the declaration and the offending entry, and it MUST refuse it before it writes any node label, capacity or queue quota. A worker whose host declaration records no split MUST keep the equal default.
```

In SPECIFICATION/scenarios.md, add one scenario immediately after "## Scenario: a worker's per-class capacity is derived from its allocatable resources":

```
## Scenario: a worker's recorded measured split replaces the equal default

Given a joined worker enrolled in the CI, gate and factory classes
And its host declaration records a measured split with a reason, giving the factory class a zero share and dividing the rest between CI and gate

When enrollment derives its per-class capacity

Then the CI and gate classes MUST each receive their recorded share of the allocatable CPU, with the CI share expressed in churn slots by the fleet's churn-slot sizing rule

And the factory class MUST hold no capacity on that worker

And the enrollment output MUST name the factory class, its zero share and the recorded reason

And the cohort churn-slot quota MUST be reconciled to the worker's derived churn slots in the same enrollment


## Scenario: an invalid recorded split is refused before any write

Given a joined worker whose host declaration records a split whose shares sum to more than one hundred percent, or that names a class other than CI, gate or factory

When enrollment runs

Then enrollment MUST refuse, naming the declaration and the offending entry

And no node label, extended-resource capacity or queue quota MUST have been written
```

The revise pass that accepts this adds both scenario headings to tests/heading-coverage.json as spec-first TODO rows owned by livespec-dev-tooling-dwewrc, with the tier named, and regenerates the debt register.
