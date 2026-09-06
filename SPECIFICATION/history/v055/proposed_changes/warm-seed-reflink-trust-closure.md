---
topic: warm-seed-reflink-trust-closure
author: claude-fable-5-1 (plan ci-runner-cache-tiers session)
created_at: 2026-09-06T03:24:42Z
---

## Proposal: Warm-seed trust closure by reflink: re-base the cache-tier clauses and scenario onto the private-per-volume seed

### Target specification files

- non-functional-requirements.md
- scenarios.md

### Summary

Re-base §"Runner-pool build cache tiers" (Tiers, Trust by construction, Storage placement), §"Runner-pool cache telemetry" (Negative tests) and the scenario "a routed job reads the warm cache and cannot write it" onto the realization that closed the warm uv tier's trust hazard: the warm tree is seeded into each job's work volume at provisioning as a reflink copy on the XFS `ci-workvols` tier, so every inode a job sees is its own and its writes never reach the shared generation. The clauses stop naming a read-only mount that does not exist, place the seeded tree on the tier that holds the work volumes, permit (and for a private seed require) reflink dependence carried by the storage layout's per-role filesystem decision, keep the no-reflink rule for every other cache, and re-state the negative test and the scenario as the shared-inode assertions the suite now makes.

### Motivation

The specification's own "Trust by construction" clause (a job MUST NOT be able to write any shared cache) was unmet from 2026-09-04 to 2026-09-06: the hardlink seed that replaced the per-start byte copy under livespec-lvtu gave every job inodes that WERE the generation's, writable from the pod's idmapped root, and case 1 of the scheduled negative tests reported the violation on every run (livespec-dev-tooling-hmv2bo). On ext4 with hardlinks no owner satisfies the clause (an unmapped owner breaks uv's cache init; research/006 §3). The maintainer took research/006's recommendation (a): the ci-workvols tier was reformatted as XFS with reflink on 2026-09-06 and the seed became a reflink copy. That realization contradicts ratified text in two files — the warm tree is not mounted read-only, it does not live under ci-cache, it depends on reflink, the negative-test clause names a mount that is gone, and the scenario's When/Then steps describe the postStart copy and the mount. An implementation that satisfies the clauses' intent while contradicting their text is a spec drift; this proposal makes the text say what the pool now enforces, keeping the no-reflink rule for every cache that does not need it and the fail-soft rule (no seed, never a byte copy) where the dependence is unmet. An independent review of the first filing found the scenario omission and a factual over-claim ("mounted by nothing but the populator": the provisioner's helper pod and the host-run negative control reach the tree); both are corrected in this filing.

### Proposed Changes

The clause set is re-based onto the realization that closed the warm uv tier's trust hazard on 2026-09-06 (`livespec-dev-tooling-hmv2bo`; livespec plan `ci-runner-pod-lifecycle-reliability` research/006, option (a)). Four clauses in `non-functional-requirements.md` and one scenario body in `scenarios.md` change; no H2 heading changes.

1. **Tiers.** The seeded realization is described as it is built — the tree is seeded into the job's work volume by the storage provisioner while the volume is created, before the volume is bound to any pod — rather than as a read-only mount plus a copy inside the pod (the 2026-08-23 shape, retired under `livespec-lvtu`). The six-simultaneous-starts sentence, the host-served preference, and the later "per-start copy" / "copy mechanism" phrases are NOT touched here; the pending proposal tracked as livespec `livespec-1qpt` owns that re-base (noted on that item).

2. **Trust by construction.** "Mounted read-only" MUST NOT be the stated mechanism, because uv refuses a read-only cache and no job pod mounts the warm tree at all. The clause now states the property the closure enforces: a path a job can reach MUST NOT resolve to a shared inode of a warm tree; a job's private copy MUST consist of its own volume's inodes; the shared tree MUST be reachable from no job pod; only the populator writes it. (The provisioner's helper pod and the host-run negative control do reach the tree; neither is a job pod.) The rest of the clause is unchanged.

3. **Storage placement.** Two corrections. (a) The warm tree has lived on the `ci-workvols` tier beside the work volumes since 2026-09-04, because a seed that costs no data bytes is legal only within one filesystem; the clause said every host-side cache tree MUST live under `ci-cache`. It now says each cache MUST live on one of the label-addressed tiers, with the role named per realization. (b) "A cache MUST NOT depend on copy-on-write or reflink support" is retained for every cache EXCEPT the seeded warm tree, which MAY depend on reflink and MUST when that is what makes the seed private per volume. The dependence MUST be carried by the storage layout's per-role filesystem decision (`ci-runner/k3s/phase2/storage-layout/migrate-tier.sh` `role_fstype`: `ci-workvols` is XFS with reflink), so it remains media-neutral, and an unmet dependence MUST yield no seed rather than a byte copy.

4. **Negative tests (§"Runner-pool cache telemetry").** "cannot write the warm-cache mount" names a mount that no longer exists. The case MUST assert, from inside a routed job, that no inode under the seed has a link outside it and that a new entry is still creatable; and, where the seed is a reflink copy whose source generation is still retained and the job image can read extent flags, that the copy's extents are shared with the generation, so a byte copy is caught too. The three conditions mirror `ci-runner/k3s/phase2/isolation/cache-negative-tests.sh` case 1 exactly (the shared-extent flag clears once the source generation is pruned; the script's caveat).

5. **Scenario "a routed job reads the warm cache and cannot write it"** (`scenarios.md`; heading unchanged). Its When step named the job container's postStart as what makes the generation available "by copy", and its Then step required a write against "the warm-cache mount" to fail. Re-based: the work volume is provisioned with the uv generation already seeded as a private copy while the postStart points cargo at the host-served cache; a write to a seeded file MUST land in the job's own volume and MUST leave the shared generation unchanged; the job MUST still be able to create an entry beside the seed; the span requirement is unchanged.

```diff
--- a/non-functional-requirements.md
+++ b/non-functional-requirements.md
@@
-realized either as a host-SERVED cache a job reads over the node network (a caching registry proxy or a RAM-resident store), or as a read-only host-side tree that every job pod mounts read-only and copies into its own ephemeral work volume before the first step runs. Because per-job start writes
+realized either as a host-SERVED cache a job reads over the node network (a caching registry proxy or a RAM-resident store), or as a host-side tree that is SEEDED into each job's ephemeral work volume as that volume is provisioned, before the volume is bound to any pod, so that the job's first step already finds it there. Because per-job start writes
@@
-**Trust by construction.** A job MUST NOT be able to write any shared cache: the warm trees are mounted read-only and a job works on its private copy; the compilation cache
+**Trust by construction.** A job MUST NOT be able to write any shared cache: a path a job can reach MUST NOT resolve to a shared inode of a warm tree — a job works on a private copy whose every inode is its own volume's, the shared tree MUST be reachable from no job pod, and only the populator writes it; the compilation cache
@@
-**Storage placement.** Every host-side cache tree MUST live under the pool's label-addressed cache tier (the `ci-cache` role), MUST NOT assume a physical medium, and MUST be movable between media by data copy and relabel exactly as the pool's other storage tiers are. RAM-resident caches (the compilation-cache backend) hold only regenerable data and MUST be restorable by one populator run after a host restart. A cache MUST NOT depend on copy-on-write or reflink support from the host filesystem.
+**Storage placement.** Every host-side cache tree MUST live under one of the pool's label-addressed storage tiers, MUST NOT assume a physical medium, and MUST be movable between media by data copy and relabel exactly as the pool's other storage tiers are: a host-served cache's store MUST live under the cache tier (the `ci-cache` role); a seeded warm tree MUST live on the tier that holds the work volumes it is seeded into (the `ci-workvols` role), because a seed that costs no data bytes is legal only within one filesystem. RAM-resident caches (the compilation-cache backend) hold only regenerable data and MUST be restorable by one populator run after a host restart. A seeded warm tree MAY depend on copy-on-write (reflink) support from the tier's filesystem, and MUST when that is what makes the seed private per volume; the storage layout MUST then decide that tier's filesystem type once, by role, so the dependence is a property of the role and not of any medium. Every other cache MUST NOT depend on copy-on-write or reflink support. Where a seed's filesystem dependence is unmet, the job MUST get no seed (cold) rather than a byte copy.
@@
-**Negative tests.** The pool's isolation suite MUST assert, on its existing timer, that a job cannot write the warm-cache mount, that a compilation-cache write with a job's credentials is refused, and that no writer credential is present in a job pod.
+**Negative tests.** The pool's isolation suite MUST assert, on its existing timer, from inside a routed job, that no inode under the job's warm-cache seed has a link outside that seed, that the job can still create an entry beside the seed, and — where the seed is a reflink copy, the generation it was seeded from is still retained, and the job image can read extent flags — that a seeded file's extents are shared with the generation, so a byte copy is caught too; and that a compilation-cache write with a job's credentials is refused, and that no writer credential is present in a job pod.
--- a/scenarios.md
+++ b/scenarios.md
@@
-When the job container's postStart makes the current generation available to the job (by copy, or by pointing the package manager at the host-served cache)
-
-Then the job's dependency sync MUST resolve from the cache without contacting the package index
-
-And a write attempt against the warm-cache mount from inside the job MUST fail
-
-And a `cache.warm-copy` span with `build.cache.hit` true MUST be emitted for each tier
+When the job's work volume is provisioned with the current uv generation already seeded into it as a private copy, and the job container's postStart points the package manager at the host-served cargo cache
+
+Then the job's dependency sync MUST resolve from the cache without contacting the package index
+
+And a path the job can reach MUST NOT resolve to a shared inode of a warm tree, so a write from inside the job to a seeded file MUST land in the job's own volume and MUST leave the shared generation unchanged
+
+And the job MUST still be able to create a new entry beside the seed
+
+And a `cache.warm-copy` span with `build.cache.hit` true MUST be emitted for each tier
```
