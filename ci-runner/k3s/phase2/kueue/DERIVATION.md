# Deriving the per-repository Kueue quotas from the admission formula

This file is `livespec-s43svm.15`'s deliverable: it maps the fleet's
EXISTING, UNCHANGED admission/fair-share formula onto the ARC and Kueue
mechanisms, and shows the arithmetic that produces the committed
`cluster-queue-<repo>.yaml` files beside it. The formula itself is not
redesigned here — its authority is
`SPECIFICATION/non-functional-requirements.md` section "Adaptive JIT
runner admission budget", and the sentence being modeled is:

> Each repository's logical ceiling MUST be BOUNDED to a small multiple
> of that repository's fair share of host-wide capacity — large enough
> that a repository can borrow unused capacity beyond its guaranteed
> share, and never so large that a backlog is materialized as pending
> admission objects the host's control plane must keep reconciling:
> queued work beyond a bounded multiple of the admission cap MUST wait
> at the forge, where it costs the host nothing, rather than exist as
> pending objects on the host. The multiple, and any floor that keeps a
> small-share repository from draining a lone matrix one job at a time,
> are pool facts recorded with the pool's admission derivation, never
> here. Maintainer-directed 2026-09-06. The physical host-wide cap
> remains exactly 482 active runners; no configuration or recovery path
> may derive or admit 964 runners. Repositories MAY fairly borrow unused
> capacity, and the desired admission for each repository MUST be
> `min(queued jobs, doubled repository logical ceiling, fair share of
> remaining host-wide capacity)`.

(Quoted as ratified on 2026-09-06 by the proposed change
`scale-set-ceiling-bounded-to-fair-share`; until then the first sentence
required the ceiling to be doubled to support two concurrent matrix
pipelines. The formula's term name `doubled repository logical ceiling`
is retained so the mapping table below stays valid; the term is defined
by the bounded sentence.)

`README.md` gives the narrative mapping. This file is the numeric one:
where each term lives, what the inputs are, and how to recompute the
quotas when the host's capacity number changes.

## The four terms and where each one lives

The formula is a `min()` of three terms plus a physical invariant. Each
lands on a different mechanism, and — this is the correction this pass
makes — they are FOUR DIFFERENT NUMBERS, not one number written in
several places.

| Formula term | Mechanism | Where it is configured |
|---|---|---|
| `queued jobs` | ARC scale-set listener | nothing to configure — the listener scales to the count of jobs GitHub has assigned to that scale set |
| `doubled repository logical ceiling` | ARC `AutoscalingRunnerSet.maxRunners` — since 2026-09-06 BOUNDED to `max(2 x nominalQuota, 6)`, see "Bounding maxRunners to the quota (2026-09-06)" | `../arc/values-<repo>.yaml` |
| `fair share of remaining host-wide capacity` | Kueue `ClusterQueue` `nominalQuota` floors within one cohort, plus cohort borrowing of anything unused | `cluster-queue-<repo>.yaml` (this directory) |
| physical cap never exceeded, never doubled | the `ci-runner.io/churn-slot` extended resource's node capacity, enforced by the Kubernetes scheduler | `../node-extended-resource/patch-node-churn-capacity.sh` |

Only the first term is dynamic. The other three are static configuration
that bounds it.

### The `queued jobs` term needs no configuration

An ARC `AutoscalingRunnerSet`'s listener watches GitHub's message queue
for its own scale set and creates exactly one ephemeral runner pod per
assigned job, up to `maxRunners`. That is already `min(queued jobs,
maxRunners)`; the fleet does not implement it.

### `doubled repository logical ceiling` is `maxRunners`, and it is NOT the Kueue quota

`maxRunners` is a hard per-repository ceiling that ARC enforces on its
own, independently of Kueue. From 2026-08-19 to 2026-09-06 it was read as
"how many runner pods would this repository ever want at once" — a
property of the REPOSITORY's workflows (its matrix width, doubled for two
concurrent pipelines), not of the host. Since 2026-09-06 it is DERIVED from
the repository's quota, `max(2 x nominalQuota, 6)`, for the reason recorded
below; it remains a ceiling ARC enforces on its own.

**This retires an earlier claim in `README.md` ("Two enforcement points,
one number") that `maxRunners` and the ClusterQueue's `nominalQuota`
MUST carry the same number.** They are different terms of the same
`min()`, so forcing them equal collapses the formula: if `maxRunners`
equals the fair share, a repository can never use idle capacity another
repository is not using, and the borrowing clause ("Repositories MAY
fairly borrow unused capacity") becomes unreachable. The two numbers are
correctly UNEQUAL, and the correct relation is `nominalQuota_i <=
maxRunners_i` — a floor no larger than the ceiling. That relation is
what the sibling values files and these manifests now assert.

**And since 2026-09-06 the ceiling is BOUNDED from above as well:**
`nominalQuota_i <= maxRunners_i = max(2 x nominalQuota_i, 6)`. The lower
bound keeps borrowing reachable; the upper bound keeps a backlog from
materializing as gated pods the control plane must keep rewriting. The
measurement that forced it, and the rule, are in "
Bounding maxRunners to the quota (2026-09-06)" below. A `maxRunners` set to the doubled matrix width — the
reading this section carried from 2026-08-19 to 2026-09-06 — is now a
DEFECT, not the formula's intent.

### `fair share of remaining host-wide capacity` is the Kueue cohort

Every repository's `ClusterQueue` joins the single cohort
`fleet-ci-runner-pool` over the single `ResourceFlavor`
`churn-slot-flavor` (`resource-flavor.yaml`). Within a cohort:

- `nominalQuota_i` is repository `i`'s GUARANTEED floor. It can always
  admit up to this much regardless of what its peers are doing.
- Anything a repository does not use is BORROWABLE by its cohort-mates,
  automatically. Confirmed live on the pinned Kueue v0.19.1 install
  (`../VALIDATION_CHECKLIST.md` item 5, 2026-08-16): a
  `nominalQuota: 1` queue admitted three concurrent Jobs by borrowing
  two units from a cohort-mate, with ZERO Kueue `Configuration` changes.
  There is no fair-sharing "enable" switch at this version.
- Total borrowing across the cohort is bounded by the SUM of the
  cohort's nominal quotas. This is why the sum matters, and why raising
  node capacity without also raising the quotas is a no-op — a mistake
  already made and corrected once on this fleet (journaled on
  `livespec-s43svm.15`, 2026-08-19).

So the fair-share term is realized as: guaranteed floors that sum to the
host capacity, plus unrestricted opportunistic borrowing above them.

#### `fairSharing.weight` is deliberately left at 1, and is currently inert

Every committed `ClusterQueue` carries `fairSharing.weight: 1`. The
demand weighting lives in `nominalQuota`, not here, for two reasons.

First, Kueue's fair-sharing weight only influences PREEMPTION decisions
— which borrower gets evicted when a cohort-mate wants its quota back.
Every ClusterQueue in this cohort sets `preemption.reclaimWithinCohort:
Never`, `preemption.borrowWithinCohort.policy: Never`, and
`preemption.withinClusterQueue: Never`, so nothing is ever preempted and
the weight has no effect on any decision this cluster makes. Setting it
to `w_i` would look like it was doing something while doing nothing —
worse than leaving it neutral.

Second, `nominalQuota` is auditable in a way a weight is not: the quotas
are integers that must sum to exactly the node capacity, so a drifted
quota is caught by adding eight numbers, whereas a drifted weight is
only visible in emergent behavior.

The consequence, stated plainly so it is not discovered later as a
surprise: **above its guaranteed floor, a repository competes for the
remaining capacity first-come-first-served, not by weight.** The
weighting is a floor guarantee, not a throughput share under saturation.
Preemption is off deliberately — evicting a half-finished CI job to
rebalance a queue wastes the very iowait budget this whole design is
protecting.

**This is now a standing, non-negotiable directive: NEVER EVICT A HEALTHY
RUNNING JOB to rebalance the cohort** (maintainer-declared 2026-08-30, during
the increase-ci-runners raise, livespec epic livespec-zec4mz). Every
`ClusterQueue` in `fleet-ci-runner-pool` MUST keep
`preemption.reclaimWithinCohort: Never`, `preemption.borrowWithinCohort.policy:
Never`, and `preemption.withinClusterQueue: Never`. Fair-sharing under
contention is bought with more capacity (raise `C`) and with the guaranteed
floors above, never by killing work already in flight. Do not flip
`reclaimWithinCohort` to `Any` or `LowerPriority` as a starvation remedy — the
remedy is capacity, which is exactly what the C = 16 → 64 raise did.

### The physical cap is the scheduler, not Kueue

Kueue's own "Admitted" condition is NECESSARY BUT NOT SUFFICIENT for a
pod to run. Proven live (`../VALIDATION_CHECKLIST.md` item 7,
2026-08-16): with six Jobs against a four-unit capacity, Kueue reported
`Admitted: True` for all six while exactly four pods reached `Running`
and two stayed `Pending`. The `ci-runner.io/churn-slot` extended
resource's finite node capacity, enforced by the Kubernetes scheduler
itself, is the real and final gate. No arithmetic error in the quota
apportionment below can breach it — the worst a bad quota sum can do is
under-use the host or leave borrowing capped too low, never over-admit.

That is the structural reason the specification's "no configuration or
recovery path may derive or admit 964 runners" invariant holds here: the
number of simultaneously-running runner pods is bounded by a single
integer on a single node object, not by agreement among eight
independently-edited manifests.

## Historical inputs (superseded)

**The podman-era demand weights `w_i`.** The historical derivations below
used the `ci-runner-supervisor` apportionment of the full 482-slot physical
budget across the fleet by observed demand. Those values, read from the live
host (`systemctl cat ci-runner-supervisor`, 2026-08-16, and journaled on
`livespec-s43svm.15`), were the inputs to those earlier derivations:

| Repository | `w_i` |
|---|---|
| `livespec` | 75 |
| `livespec-driver-codex` | 67 |
| `livespec-driver-claude` | 66 |
| `livespec-orchestrator-git-jsonl` | 66 |
| `livespec-overseer` | 65 |
| `livespec-runtime` | 64 |
| `livespec-dev-tooling` | 63 |
| `livespec-console-beads-fabro` | 16 |
| **sum `W`** | **482** |

They sum to exactly 482, the physical cap, because that is what they
were: an apportionment OF that cap. They remain only as a historical record
of earlier capacity decisions and must not be used as inputs to current
manifests. The current inputs are the measured job-hours in
"Measured job-hours re-derivation at C = 44 (2026-10-22)" below. In either
derivation, a demand weight is not a repository's logical ceiling: the latter
feeds `maxRunners`, while the former feeds `nominalQuota`.

**The capacity `C`.** The `ci-runner.io/churn-slot` capacity currently
registered on the node. It is `32` — first set to `64` on 2026-08-30 by the
increase-ci-runners raise (livespec epic livespec-zec4mz), lowered to the
INTERIM `32` on 2026-09-02 while the RAID's data plane was the ceiling,
RESTORED to `64` on 2026-09-06 once both NVMe drives carried the churn, and
stepped back to `32` the same day when the soak at 64 showed the CPU, not
storage, saturating at 35–46 running jobs; see "The step back to C = 32 on the
tiered host (2026-09-06)" below. It was `16` from 2026-08-19 until the first
raise.

## The apportionment rule

    nominalQuota_i = max(1, largest_remainder_apportionment(C, w_i))

Largest-remainder (Hamilton) apportionment, spelled out:

1. Compute each repository's exact share `e_i = C * w_i / W` as an exact
   rational, never a float.
2. Give each repository `floor(e_i)`.
3. Distribute the `C - sum(floor(e_i))` leftover units one each to the
   repositories with the largest fractional remainders `e_i -
   floor(e_i)`, in descending remainder order.
4. Tie-break, in order: larger remainder, then larger `w_i`, then
   repository name ascending. (Deterministic, so two people recomputing
   this get the same answer.)
5. Raise any zero to 1 — no repository is given a floor of zero, or it
   can only ever run by borrowing, and a repository whose cohort-mates
   are saturated would starve indefinitely.

Step 5 can push the sum above `C`. If it does, deduct the excess one
unit at a time from the repositories with the LARGEST quotas (ties
broken by smaller `w_i`, then name descending), never taking any
repository below 1. This is part of the rule, not an optional
post-processing choice: the committed quotas must still sum to `C`.

**The invariant to check after any recomputation:** the quotas sum to
exactly `C`, the registered node capacity. Nothing enforces this
mechanically — see "Is a generator worth building?" below.

**The invariant has no exception.** The `max(1, ...)` floor can lift a
repository whose apportionment rounds to zero, which adds a unit the
apportionment did not allocate. The excess-deduction step immediately above
then restores the sum to `C`. Earlier historical prose described retaining a
`C + k` total; it conflicted with the explicit rule and is not a permissible
result for a new derivation.

## The derivation at C = 16

Exact shares `e_i = 16 * w_i / 482`:

| Repository | `w_i` | `e_i` | `floor` | remainder | leftover unit | `nominalQuota` |
|---|---|---|---|---|---|---|
| `livespec` | 75 | 2.4896 | 2 | 0.4896 | +1 (2nd largest) | **3** |
| `livespec-driver-codex` | 67 | 2.2241 | 2 | 0.2241 | | **2** |
| `livespec-driver-claude` | 66 | 2.1909 | 2 | 0.1909 | | **2** |
| `livespec-orchestrator-git-jsonl` | 66 | 2.1909 | 2 | 0.1909 | | **2** |
| `livespec-overseer` | 65 | 2.1577 | 2 | 0.1577 | | **2** |
| `livespec-runtime` | 64 | 2.1245 | 2 | 0.1245 | | **2** |
| `livespec-dev-tooling` | 63 | 2.0913 | 2 | 0.0913 | | **2** |
| `livespec-console-beads-fabro` | 16 | 0.5311 | 0 | 0.5311 | +1 (largest) | **1** |
| **sum** | **482** | **16** | **14** | | **+2** | **16** |

The floors sum to 14, leaving 2 units to distribute; the two largest
remainders are `livespec-console-beads-fabro` (0.5311) and `livespec`
(0.4896), so each gets one. The result sums to exactly `C = 16`. Step
5's `max(1, ...)` is satisfied without adjustment —
`livespec-console-beads-fabro` reached 1 through the remainder step, not
through the floor.

The small repository landing on 1 by remainder rather than by share is
worth noticing rather than glossing: at `C = 16` its exact share is half
a slot, so ANY integer it gets is a rounding artifact. It is not being
favoured; the apportionment simply has nowhere smaller to put it, and
cohort borrowing means a floor of 1 does not cap it at 1.

### Two properties worth recording

**At `C = 482` the rule reproduces the podman apportionment exactly.**
`e_i = 482 * w_i / 482 = w_i` is already an integer for every
repository, so every quota equals its weight and the leftover step never
runs. The derivation is therefore continuous with the pool it replaces:
at the design-envelope capacity it IS the podman apportionment, and at
lower capacities it is that apportionment scaled down proportionally.

**At `C = 8` the rule reproduces the ad-hoc stopgap exactly.** Running
the same arithmetic at `C = 8` gives every repository a floor of 1
(`livespec-console-beads-fabro` picks up the single leftover unit, on
remainder 0.2656 against `livespec`'s 0.2448), summing to 8. That is
precisely the flat `nominalQuota: 1` configuration a maintainer chose by
hand on 2026-08-19 to stop CI starvation. The formula agreeing with an
independently-made operational judgement at one bracket end, and with
the measured podman apportionment at the other, is the closest thing to
external corroboration available for a rule with no way to be unit
tested against ground truth.

## Recomputation on the ninth repository (2026-08-20)

`livespec-driver-pi` joined the cohort on 2026-08-20, after
`livespec-s43svm.16`'s ordered eight-repo cutover had closed at "8 of
8". It did not exist as a fleet member when the table above was
computed, so this is the first recomputation driven by a change in the
REPOSITORY SET rather than in `C`.

**Its demand weight is `13`, and it is the first weight in this table
that is a real measurement.** Every other `w_i` is a podman-era
apportionment number inherited as a proxy — see "Observation: ARC
`maxRunners` still carries the podman-era numbers" below, and
`../arc/values-livespec-driver-codex.yaml`, which states plainly that
"nobody has measured its actual matrix width". `livespec-driver-pi`'s 13
was counted from run `32420185191` on
`thewoolleyman/livespec-driver-pi#64`, which dispatched exactly 13 jobs.
It sits far below the siblings' 63–67 band because that repo's `ci.yml`
deliberately collapses its ~69 check targets into batch jobs
(`check-python-batch`, `check-metadata-batch`) instead of running one
job per check slug. It is not an under-count.

Adding it takes the fleet weight sum to `W = 482 + 13 = 495`. Exact
shares `e_i = 16 * w_i / 495`:

| Repository | `w_i` | `e_i` | `floor` | remainder | leftover unit | `nominalQuota` |
|---|---|---|---|---|---|---|
| `livespec` | 75 | 2.4242 | 2 | 0.4242 | +1 (2nd largest) | **3** |
| `livespec-driver-codex` | 67 | 2.1657 | 2 | 0.1657 | | **2** |
| `livespec-driver-claude` | 66 | 2.1333 | 2 | 0.1333 | | **2** |
| `livespec-orchestrator-git-jsonl` | 66 | 2.1333 | 2 | 0.1333 | | **2** |
| `livespec-overseer` | 65 | 2.1010 | 2 | 0.1010 | | **2** |
| `livespec-runtime` | 64 | 2.0687 | 2 | 0.0687 | | **2** |
| `livespec-dev-tooling` | 63 | 2.0364 | 2 | 0.0364 | | **2** |
| `livespec-console-beads-fabro` | 16 | 0.5172 | 0 | 0.5172 | +1 (largest) | **1** |
| `livespec-driver-pi` | 13 | 0.4202 | 0 | 0.4202 | | **1** (by `max(1, …)`) |
| **sum** | **495** | **16** | **14** | | **+2** | **17** |

**Every pre-existing repository's quota is UNCHANGED.** That is worth
stating explicitly, because the naive expectation is that adding a
claimant dilutes everyone. It does not here: the seven mid-band repos
were already at floor 2 and stay there, and the two leftover units still
go to `livespec-console-beads-fabro` (0.5172) and `livespec` (0.4242).
`livespec-driver-pi` misses the second leftover unit by 0.0040 — the
closest call in this table by an order of magnitude — and so is
apportioned **zero**.

**Historical record; superseded rule.** The 2026-08-20 configuration retained
the floor lift, so its committed quotas summed to 17 against `C = 16`. That
was the contradictory `C + k` reading later found in this document. The rule
now resolves it mechanically: after the floor lift, deduct the excess from
the largest quota under the tie-break described above. A fresh C = 16
derivation must therefore sum to 16; it must not recreate this historical
over-reservation or raise capacity merely to accommodate it.

**Note for the next repository.** A tenth repo can still produce another
sub-one exact share at a low `C`, but that is no longer a sum-invariant
exception: the floor-and-deduction steps preserve both its one-slot floor and
the exact cohort total.

## The derivation at C = 64 (2026-08-30)

The `increase-ci-runners` plan (livespec epic `livespec-zec4mz`,
maintainer-approved 2026-08-30) raised the node capacity from 16 to **64** —
a 4x overcommit set DELIBERATELY AHEAD OF DATA. The reasoning is journaled on
that epic and in the livespec plan `plan/increase-ci-runners/research/`; the
short version: CPU and memory have ~20x idle headroom (measured 5% CPU / 3%
mem on the 72-core/197-GiB box), so the only resource 64 ephemeral runner pods
can plausibly saturate is DISK IO — which is exactly the un-measured
throughput ceiling the RAID work (`poweredge-raid-array-maintenance`, epic
`livespec-g52yrb`) needs numbers for. Saturation here is a WANTED outcome: it
converts "no disk data" into "disk data." 64 is well under the 110-pod kubelet
ceiling — a comparison that turned out to be the WRONG one, because a full
pool puts about `2C + helpers + system` pods on the node, not `C`; see "The
pod-capacity constraint" below.

Same demand weights `w_i`, `W = 495`. Exact shares `e_i = 64 * w_i / 495`:

| Repository | `w_i` | `e_i` | `floor` | remainder | leftover unit | `nominalQuota` |
|---|---|---|---|---|---|---|
| `livespec` | 75 | 9.6970 | 9 | 0.6970 | +1 (1st largest) | **10** |
| `livespec-driver-codex` | 67 | 8.6626 | 8 | 0.6626 | +1 (3rd largest) | **9** |
| `livespec-driver-claude` | 66 | 8.5333 | 8 | 0.5333 | +1 (4th, tie by name) | **9** |
| `livespec-orchestrator-git-jsonl` | 66 | 8.5333 | 8 | 0.5333 | | **8** |
| `livespec-overseer` | 65 | 8.4040 | 8 | 0.4040 | | **8** |
| `livespec-runtime` | 64 | 8.2747 | 8 | 0.2747 | | **8** |
| `livespec-dev-tooling` | 63 | 8.1455 | 8 | 0.1455 | | **8** |
| `livespec-console-beads-fabro` | 16 | 2.0687 | 2 | 0.0687 | | **2** |
| `livespec-driver-pi` | 13 | 1.6808 | 1 | 0.6808 | +1 (2nd largest) | **2** |
| **sum** | **495** | **64** | **60** | | **+4** | **64** |

The floors sum to 60, leaving 4 units. The four largest remainders are
`livespec` (0.6970), `livespec-driver-pi` (0.6808), `livespec-driver-codex`
(0.6626), and then a tie at 0.5333 between `livespec-driver-claude` and
`livespec-orchestrator-git-jsonl` — broken by the rule's final tie-break
(equal remainder, equal `w_i` of 66, then repository name ascending), which
awards the fourth unit to `livespec-driver-claude`. The result sums to
**exactly C = 64**.

**The C = 16 `max(1, ...)` exception is GONE at C = 64.** Every repository's
exact share now exceeds 1 (the smallest, `livespec-driver-pi`, is 1.6808), so
step 5 never lifts a rounded-to-zero share and the committed quotas sum to
exactly `C` with no forced over-reservation. The sum invariant holds cleanly
again.

**Reclaim/preemption is UNCHANGED and stays `Never`.** The raise buys
fair-sharing headroom with capacity, not by eviction — see the standing
"NEVER EVICT A HEALTHY RUNNING JOB" directive under "`fairSharing.weight` is
deliberately left at 1". A `reclaimWithinCohort: Any` flip was explicitly
considered and REJECTED for this change.

### The pod-capacity constraint: kubelet `max-pods` >= 2C + helper pods + system pods (2026-09-01)

`C` counts churn slots, and each churn slot is consumed by a RUNNER pod —
but a running job holds TWO pods on the node (the runner pod and its
`-workflow` pod; see `README.md` "The workflow pod is not the runner pod"),
and provisioning each runner's work PVC spawns a transient
`helper-pod-create-pvc-*` pod in `kube-system`. So the pod count a full pool
puts on the node is not `C` but roughly `2C + (helper pods in flight) +
(system pods)`, and the kubelet's `max-pods` (k3s default **110**) has to
hold it. At C = 64 that is about 128 + ~20 + ~15 ≈ 165 > 110. When it does
not fit the failure is a deadlock, not a queue: the helper pods that would
provision the NEXT job's PVC cannot schedule behind the cap, so no runner
pod can bind its volume, so nothing completes and frees a slot. It was one
leg of the 2026-09-01 runner-pod lifecycle stall (livespec plan
`ci-runner-pod-lifecycle-reliability`, epic `livespec-ifwnqj`, research/001
and /002; carrier `livespec-a6lxuv`).

Decided 2026-09-01 (maintainer): raise `max-pods` to **200** rather than
lower C. Set as `kubelet-arg: ["max-pods=200"]` in
`/etc/rancher/k3s/config.yaml` on `poweredge-xubuntu`; effective after the
k3s restart of 16:06Z (`status.allocatable.pods` 110 → 200). 200 is bounded
above by the node's pod CIDR `10.42.0.0/24` (~250 usable addresses), so it
needs no CIDR change; a C above ~90 would. The constraint is a HOST term
beside the churn-slot derivation, not part of the apportionment: whenever C
moves, re-check `2C + ~35 <= max-pods <= podCIDR size`.

The same incident's kernel-side term — `fs.inotify.max_user_instances`,
default 128, ~2 per containerd shim plus ~21 for kubelet/cadvisor, exhausted
at roughly 50 containers' worth of shims — was raised to 8192 on the host
(`/etc/sysctl.d/99-ci-runner-inotify.conf`). The inotify budget now has a
node-local install mechanism — the `node_sysctl` Ansible role (it replaced
`../node-inotify-budget/install-inotify-sysctl.sh`, `livespec-dev-tooling-9btv`)
writes that drop-in from the shipped `99-ci-runner-inotify.conf` and applies it,
so a new or rebuilt pool member inherits it and `systemd-sysctl` re-applies it at
every boot (no reapply timer is needed, unlike `../node-extended-resource/`,
because a `/etc/sysctl.d/` file is natively boot-durable). `max-pods` is durable
by its own mechanism: it lives in `/etc/rancher/k3s/config.yaml` on the host,
which k3s reads on every start, so a reboot or k3s restart preserves it; a full
host REBUILD re-runs `../provision-k3s.sh`, which does not yet re-write that
kubelet-arg, so re-applying `max-pods` after a from-scratch rebuild is the one
piece still owed (tracked on `livespec-a6lxuv`).

## The derivation at C = 32 (2026-09-02, INTERIM until the NVMe tiering lands)

Maintainer decision 2026-09-02 (livespec plan `ci-runner-pod-lifecycle-reliability`,
epic `livespec-ifwnqj`; `C` remains `livespec-zec4mz`'s number): LOWER `C` from 64
to **32** until `livespec-e2vcqf` tiers containerd's root and the runner scratch
volumes onto the dedicated NVMe. Why: with the k3s datastore on tmpfs the control
plane held at 39 concurrent runners (0 `Slow SQL`, Kueue lease kept), but the
DATA plane did not — at roughly 40 concurrent jobs' worth of create + teardown
churn, containerd on the RAID timed out (22,161 `DeadlineExceeded` in one
20-minute window, of which 3,715 `StopPodSandbox` and 3,689 `StopContainer`
failures, kubelet retrying teardown in a loop), starving the local-path
provisioner's helper-pod creates and even manifest-only image pulls of an
already-cached image; eleven jobs across two fan-outs failed the ARC hook. 32
sits below the measured failure point. This is a THROTTLE, not a measurement:
the 64-runner soak the C = 64 raise exists for is deferred to after e2vcqf, and
the number goes back to 64 then (recompute per "Recomputing at another C").

Same demand weights `w_i`, `W = 495`. Exact shares `e_i = 32 * w_i / 495`:

| Repository | `w_i` | `e_i` | `floor` | remainder | leftover unit | `nominalQuota` |
|---|---|---|---|---|---|---|
| `livespec` | 75 | 4.8485 | 4 | 0.8485 | +1 (1st largest) | **5** |
| `livespec-driver-codex` | 67 | 4.3313 | 4 | 0.3313 | +1 (3rd largest) | **5** |
| `livespec-driver-claude` | 66 | 4.2667 | 4 | 0.2667 | | **4** |
| `livespec-orchestrator-git-jsonl` | 66 | 4.2667 | 4 | 0.2667 | | **4** |
| `livespec-overseer` | 65 | 4.2020 | 4 | 0.2020 | | **4** |
| `livespec-runtime` | 64 | 4.1374 | 4 | 0.1374 | | **4** |
| `livespec-dev-tooling` | 63 | 4.0727 | 4 | 0.0727 | | **4** |
| `livespec-console-beads-fabro` | 16 | 1.0343 | 1 | 0.0343 | | **1** |
| `livespec-driver-pi` | 13 | 0.8404 | 0 | 0.8404 | +1 (2nd largest) | **1** |
| **sum** | **495** | **32** | **29** | | **+3** | **32** |

The floors sum to 29, leaving 3 units, awarded to the three largest remainders:
`livespec` (0.8485), `livespec-driver-pi` (0.8404) and `livespec-driver-codex`
(0.3313). `livespec-driver-pi`'s exact share is below 1 for the first time since
C = 16, but its unit comes from the leftover distribution, NOT from step 5's
`max(1, ...)` floor, so there is no forced over-reservation: the quotas sum to
**exactly C = 32**. Lowering order per "Recomputing at another C": the quotas
FIRST (`kubectl apply` the nine manifests), THEN the node capacity
(`install-reapply-unit.sh 32`, which also rewrites the reapply unit's boot and
timer argument). Running pods are untouched; admissions above the new quota
wait. `maxRunners` was unchanged by that step — it was still each repository's
logical ceiling, not the quota (bounded to the quota on 2026-09-06; see
"The step back to C = 32 on the tiered host (2026-09-06)" and "
Bounding maxRunners to the quota (2026-09-06)"). The pod-capacity constraint is comfortably met: `2 x 32 + helpers +
system` is far below `max-pods = 200`.

## Recomputation on the tenth repository (2026-09-04)

`livespec-orchestrator-beads-fabro` joined the cohort on 2026-09-04
(livespec plan `ci-runner-pod-lifecycle-reliability`, epic
`livespec-ifwnqj`, Carrier G1, work-item `livespec-ifwnqj.1`). Its
`ci.yml` had been plain `runs-on: ubuntu-latest` by a recorded caution
about the fleet's operator-triggered live golden-master tier; the
maintainer settled in session that the exposure is the same as every
other member's, so it routes to the pool like the other nine. This is the
second recomputation driven by a change in the REPOSITORY SET.

**Its demand weight is `21`, and it is the second weight in this table
that is a real measurement.** Counted from master CI run `33893048859`
on `thewoolleyman/livespec-orchestrator-beads-fabro` (2026-09-04), which
dispatched exactly 21 jobs: 17 check jobs plus `setup`,
`detect-py-changes`, `export-telemetry` and `ci-green`, which stay hosted
(the same convention as every other member's `ci.yml`). Like
`livespec-driver-pi`'s 13 it sits far below the podman-era 63–67 band
because that repo's `ci.yml` batches its check targets (`check-python-batch`,
`check-metadata-batch`) rather than running one job per check slug. It is
not an under-count.

Adding it takes the fleet weight sum to `W = 495 + 21 = 516`. At the
INTERIM `C = 32` (see "The derivation at C = 32" above), exact shares
`e_i = 32 * w_i / 516`:

| Repository | `w_i` | `e_i` | `floor` | remainder | leftover unit | `nominalQuota` |
|---|---|---|---|---|---|---|
| `livespec` | 75 | 4.6512 | 4 | 0.6512 | +1 (5th largest) | **5** |
| `livespec-driver-codex` | 67 | 4.1550 | 4 | 0.1550 |  | **4** |
| `livespec-driver-claude` | 66 | 4.0930 | 4 | 0.0930 |  | **4** |
| `livespec-orchestrator-git-jsonl` | 66 | 4.0930 | 4 | 0.0930 |  | **4** |
| `livespec-overseer` | 65 | 4.0310 | 4 | 0.0310 |  | **4** |
| `livespec-runtime` | 64 | 3.9690 | 3 | 0.9690 | +1 (2nd largest) | **4** |
| `livespec-dev-tooling` | 63 | 3.9070 | 3 | 0.9070 | +1 (3rd largest) | **4** |
| `livespec-console-beads-fabro` | 16 | 0.9922 | 0 | 0.9922 | +1 (1st largest) | **1** |
| `livespec-driver-pi` | 13 | 0.8062 | 0 | 0.8062 | +1 (4th largest) | **1** |
| `livespec-orchestrator-beads-fabro` | 21 | 1.3023 | 1 | 0.3023 |  | **1** |
| **sum** | **516** | **32** | **27** | | **+5** | **32** |

The floors sum to 27, leaving 5 units, awarded to the five largest
remainders in order: `livespec-console-beads-fabro`, `livespec-runtime`,
`livespec-dev-tooling`, `livespec-driver-pi` and `livespec`. **Exactly one
pre-existing quota moves**: `livespec-driver-codex` loses the leftover
unit it held at nine repositories (its remainder falls from 0.3313 to
0.1550, below the new cut line) and goes from 5 to 4; every other
pre-existing quota is unchanged. The newcomer's share is 1.3023, so its
quota of 1 is its floor by the apportionment itself, not by step 5's
`max(1, ...)`, and the ten quotas sum to **exactly C = 32** with no forced
excess. Order of application: the quotas can be applied in any order here
because the sum is unchanged (no capacity move), so the boot converge's
single `kubectl apply` of every manifest is the whole change.

When `C` returns to 64 (after the NVMe tiering), recompute the ten-row
table per "Recomputing at another C"; at `C = 64` this repository's exact
share is 2.6047.

## The derivation at C = 64 restored (2026-09-06)

Maintainer decision 2026-09-06 (livespec plan `poweredge-raid-array-maintenance`,
epic `livespec-g52yrb`; child `livespec-e2vcqf` carried the restore): with the
containerd store on one NVMe (VG `nvmea`) and the runner work volumes on a
second NVMe (VG `nvmeb`, XFS with reflink), the RAID data plane that forced the
2026-09-02 interim no longer sits under the churn, so `C` returns to **64** as
the interim's own text promised. Under the interim's last three days the array
sat near idle under every load sample while the NVMe carried the pool. The
64-runner soak that the 2026-08-30 raise exists for now finally runs at 64 on the
tiered host; the maintainer's question of a further step to 96 is deferred until
that soak has data (and 96 would first need kubelet `max-pods` raised above
`2 x 96 + helpers + system`, see "The pod-capacity constraint").

This is the first C = 64 table at TEN repositories: `W = 516` (the 495 of the
2026-08-30 table plus `livespec-orchestrator-beads-fabro`'s measured 21). Exact
shares `e_i = 64 * w_i / 516`:

| Repository | `w_i` | `e_i` | `floor` | remainder | leftover unit | `nominalQuota` |
|---|---|---|---|---|---|---|
| `livespec` | 75 | 9.3023 | 9 | 0.3023 | | **9** |
| `livespec-driver-codex` | 67 | 8.3101 | 8 | 0.3101 | | **8** |
| `livespec-driver-claude` | 66 | 8.1860 | 8 | 0.1860 | | **8** |
| `livespec-orchestrator-git-jsonl` | 66 | 8.1860 | 8 | 0.1860 | | **8** |
| `livespec-overseer` | 65 | 8.0620 | 8 | 0.0620 | | **8** |
| `livespec-runtime` | 64 | 7.9380 | 7 | 0.9380 | +1 (2nd largest) | **8** |
| `livespec-dev-tooling` | 63 | 7.8140 | 7 | 0.8140 | +1 (3rd largest) | **8** |
| `livespec-console-beads-fabro` | 16 | 1.9845 | 1 | 0.9845 | +1 (1st largest) | **2** |
| `livespec-driver-pi` | 13 | 1.6124 | 1 | 0.6124 | +1 (4th largest) | **2** |
| `livespec-orchestrator-beads-fabro` | 21 | 2.6047 | 2 | 0.6047 | +1 (5th largest) | **3** |
| **sum** | **516** | **64** | **59** | | **+5** | **64** |

The floors sum to 59, leaving 5 units, awarded to the five largest remainders in
order: `livespec-console-beads-fabro`, `livespec-runtime`, `livespec-dev-tooling`,
`livespec-driver-pi` and `livespec-orchestrator-beads-fabro`. Compared with the
nine-repository C = 64 table of 2026-08-30, the tenth member's 21 units of weight
cost `livespec` one slot (10 to 9) and `livespec-driver-codex` and
`livespec-driver-claude` one each (9 to 8), while `livespec-orchestrator-beads-fabro`
takes 3; every other row is unchanged. Every exact share exceeds 1, so step 5's
`max(1, ...)` never fires and the ten quotas sum to **exactly C = 64**.

Raising order per "Recomputing at another C": the node capacity FIRST
(`install-reapply-unit.sh 64`, which rewrites the reapply unit's boot and timer
argument and patches the node at once), THEN the quotas (the converge unit's
single `kubectl apply` of every manifest from the re-installed artifact tree). The
pod-capacity constraint holds: `2 x 64 + helpers + system` is below
`max-pods = 200`, as it was from 2026-08-30 to 2026-09-02.

## The step back to C = 32 on the tiered host (2026-09-06)

Maintainer decision 2026-09-06, about two hours after the restore to 64
(livespec plan `poweredge-raid-array-maintenance`, epic `livespec-g52yrb`;
child `livespec-e2vcqf` carries the soak read). The 64-runner soak the restore
existed for delivered its answer in its second hour, and the answer is the
CPU, not storage: the host runs 35–46 jobs concurrently before the 72 threads
saturate, and every admitted slot past that point only stacks pods in
`ContainerCreating`. Measured on `poweredge-xubuntu` between 05:37Z and
05:52Z with every ten-repository queue busy:

- `mpstat` 91–98 % busy with an idle floor of 2–7 %; 1-minute load 185–225;
  `/proc/pressure/cpu` `some avg10` at 30 % (a task waited for a core 30 % of
  the time); `procs_running` up to 307.
- Kueue reported 64 admitted and 29 pending while only 35–46
  `EphemeralRunner`s were `Running`; 39 runner pods sat in
  `ContainerCreating` or `Pending`, and 33 more were `SchedulingGated`.
- Four `Slow SQL` lines in the k3s journal, all in this window, against zero
  in the first hour and zero for the whole of the C = 32 interim on tmpfs kine.
- p95 job duration 193 s (p50 64 s) against 101 s (p50 35 s) for the C = 32
  baseline of 2026-09-05, with the queue wait for a runner at p95 17 minutes;
  0 job failures in 631, so this was slowness, not breakage.
- Storage stayed a bystander: `ci-workvols` NVMe at 2–4 ms `w_await`,
  `ci-containerd` NVMe at 1–2 ms, the array idle, iowait 0.01 %, 155 GiB free.
- On the host side `btop` aborted (SIGABRT, apport record) and seven
  interactive login-session scopes failed with `resources` — systemd could
  not attach a freshly forked shell before it exited under the scheduling
  latency. Symptoms of the same saturation, not CI faults.

That fails both limbs of the rule in "The permanent C is still an open
question": p95 job duration was no longer growing about linearly with
concurrency, and the control plane had begun to show it. Throughput cannot
rise past the CPU, so lowering the cap to the measured running count costs
nothing on the throughput axis and removes the control-plane churn.

**32 is re-instated, not re-derived.** The ten-repository C = 32 table is the
one already recorded under "Recomputation on the tenth repository
(2026-09-04)" — `livespec` 5; `livespec-driver-codex`,
`livespec-driver-claude`, `livespec-orchestrator-git-jsonl`,
`livespec-overseer`, `livespec-runtime`, `livespec-dev-tooling` 4;
`livespec-console-beads-fabro`, `livespec-driver-pi`,
`livespec-orchestrator-beads-fabro` 1 — summing to exactly 32. Its reason has
changed (CPU saturation on the tiered host, where on 2026-09-02 it was the
RAID's data plane), its numbers have not.

Lowering order per "Recomputing at another C": the quotas FIRST (`kubectl
apply` of the ten manifests, then `install-converge-unit.sh` so the boot
converge carries the same values), THEN the node capacity
(`install-reapply-unit.sh 32`, which rewrites the reapply unit's boot and timer
argument and patches the node at once). Running pods are untouched;
admissions above the new quota wait.

**The next step is 40, and it is measured before it is applied.** 40 matches
the running count the CPU was seen to serve. The soak monitor left on the
host (`/tmp/soak-monitor.log`, one line per minute: runners, running, load,
`procs_running`, pods, `mpstat` busy, both NVMe `w_await` and queue depth,
`Slow SQL` per five minutes, failed units) and the GitHub job-timing read
(p50/p95 duration, queue wait, concurrency at start, per self-hosted job)
give the C = 32 baseline on the tiered host; 40 is proposed only when that
baseline shows the CPU with headroom at 32 and is recomputed per "Recomputing
at another C" (exact shares `e_i = 40 * w_i / 516`) when it is.

## The derivation at C = 44 — the two-node pool (2026-09-11)

Plan `k3s-on-gmktec-for-vps-usage`, epic `livespec-sab5gn`, carrier **R5**,
resolving `livespec-dev-tooling-xa6o`. This is the **first two-node
derivation**: every table above apportions a SINGLE node's capacity, because
until now the pool was one node (`poweredge-xubuntu`). R5 opens the second pool
node, `gmktec-xubuntu`, for general CI churn, so the cohort quota is now
apportioned over the capacity of BOTH nodes.

**The key structural change: churn-slot capacity is now PER-NODE, not uniform.**
`ci-runner.io/churn-slot` is a node-status extended resource — each node
advertises its own capacity — while the Kueue cohort quota is a single
CLUSTER-WIDE number the ten `nominalQuota`s sum to. As long as the pool was one
node those two coincided: the cohort quota summed to that node's capacity. With
two nodes they no longer coincide, and the cohort quota must sum to the TOTAL
capacity ACROSS the nodes:

- `poweredge-xubuntu` stays at **32** — its CPU-throughput ceiling, unchanged
  and unrelated to this item (see "The step back to C = 32 on the tiered host
  (2026-09-06)"); its 72 threads saturate at 35–46 running jobs.
- `gmktec-xubuntu` is **12**. This is a DERIVED FIRST VALUE, not a settled
  number, and it is recorded to be confirmed by the same soak method the
  poweredge number earned. It comes from the node's 16 cores / 32 threads at
  poweredge's measured ~1.65-threads-per-running-job ratio (≈ a 14-job
  ceiling), MINUS reserve for the node's 3-gate budget (15 cpu, the gates
  ClusterQueue on this node — see "The gates quota on gmktec-xubuntu
  (2026-09-08)") and the resident `local-homelab-llama-server` in its 64 GiB
  iGPU carveout. Plan `research/001` §3.5 recommended exactly 12; it is carried
  here as that recommendation, to be re-measured before it is raised.

So the pool's total churn-slot capacity is **C = poweredge 32 + gmktec 12 = 44**,
and the ten `nominalQuota`s sum to 44 — the whole pool across both nodes.

**Why uniform capacity would be wrong for asymmetric nodes.** The churn-slot
capacity is what BINDS PLACEMENT: the Kubernetes scheduler will not place a
churn-slot-requesting pod on a node whose advertised `ci-runner.io/churn-slot`
allocatable is exhausted (VALIDATION_CHECKLIST item 7; "The physical cap is the
scheduler, not Kueue"). If both nodes advertised the SAME number — say both 44,
or both some uniform C — the scheduler could pile all admitted jobs onto
`poweredge` well past its ~40 running-job ceiling, because poweredge would be
advertising far more slots than it can actually serve. Per-node caps (32 and 12)
are exactly what stop that: each node admits only what it can run, and the
cluster-wide cohort quota (44) bounds the fleet total. A single uniform C cannot
express two nodes with different real ceilings.

The apportionment uses the SAME Hamilton (largest-remainder) rule and the SAME
weights as every table above (`W = 516`); only `C` changes, 32 → 44. Exact
shares `e_i = 44 * w_i / 516`:

| repo | w | e = 44·w/516 | floor | remainder | leftover | quota |
|---|---:|---:|---:|---:|:--:|---:|
| livespec | 75 | 6.3953 | 6 | 0.3953 | — | 6 |
| livespec-driver-codex | 67 | 5.7132 | 5 | 0.7132 | +1 (2nd) | 6 |
| livespec-driver-claude | 66 | 5.6279 | 5 | 0.6279 | +1 (3rd) | 6 |
| livespec-orchestrator-git-jsonl | 66 | 5.6279 | 5 | 0.6279 | +1 (4th, tie w/ driver-claude broken by name) | 6 |
| livespec-overseer | 65 | 5.5426 | 5 | 0.5426 | +1 (5th) | 6 |
| livespec-runtime | 64 | 5.4574 | 5 | 0.4574 | — | 5 |
| livespec-dev-tooling | 63 | 5.3721 | 5 | 0.3721 | — | 5 |
| livespec-orchestrator-beads-fabro | 21 | 1.7907 | 1 | 0.7907 | +1 (1st) | 2 |
| livespec-console-beads-fabro | 16 | 1.3643 | 1 | 0.3643 | — | 1 |
| livespec-driver-pi | 13 | 1.1085 | 1 | 0.1085 | — | 1 |
| **sum** | **516** | **44.000** | **39** | | **+5** | **44** |

The floors sum to 39, leaving 5 leftover units, awarded to the five largest
remainders: `livespec-orchestrator-beads-fabro` (0.7907),
`livespec-driver-codex` (0.7132), `livespec-driver-claude` (0.6279),
`livespec-orchestrator-git-jsonl` (0.6279, the tie broken by name), and
`livespec-overseer` (0.5426). `livespec` sits at its floor of 6 (its remainder
0.3953 does not reach the fifth leftover), so the raised capacity flows to the
mid-band repositories rather than to the largest. Every exact share exceeds 1,
so step 5's `max(1, …)` never fires and the ten quotas sum to exactly 44 with no
forced excess.

`maxRunners` is re-derived as `max(2 × quota, 6)` per "Bounding maxRunners to
the quota (2026-09-06)": `livespec`, `-driver-codex`, `-driver-claude`,
`-orchestrator-git-jsonl`, `-overseer` → 12; `-runtime`, `-dev-tooling` → 10;
`-orchestrator-beads-fabro`, `-console-beads-fabro`, `-driver-pi` → 6. The ten
ceilings sum to 98, so a fleet-wide backlog holds at most 98 − 44 = 54 gated
objects and the rest waits at the forge.

**The per-node mechanism that sets gmktec's 12 safely.** Opening the node is
three coupled changes landed together (R5): this quota re-derivation; the
removal of gmktec's `node-role/ci=pending:NoSchedule` taint (its profile's
`NODE_TAINTS`); and a PER-NODE self-patch mechanism so the agent stamps its own
`status.capacity` with 12 rather than the server's cluster-wide patch stamping
every node with 32. That patch —
`../node-extended-resource/patch-node-churn-capacity.sh` — used to resolve its
targets with `kubectl get nodes -l k3s-role=arc-runner-host`, a LIST, and patch
every matched node with one uniform capacity; it now patches a SINGLE NAMED node
(this node, from the profile's `NODE_NAME`) with this node's
`ADMISSION_CAPACITY_C`. That is what lets the agent use the scoped
`get`/`patch`-on-`nodes/status`-for-one-named-node credential the
`../node-status-credential/` directory mints (a LIST verb is not restrictable by
`resourceNames`, so the old uniform patch could never have used it — see that
directory's README), and it stops the server's timer from stamping gmktec with
32.

**The convergence order is now the playbook's role order.** The steps below
name the node-local scripts R5 was written against; those installers are
retired (`livespec-dev-tooling-9btv`), and `just ansible-apply
ansible/ci-pool.yml` from the control node performs all four, in the play's
role order: `node_status_credential` (step 2), then `node_extended_resource` on
both roles (steps 1 and 3 together), then `node_taints` (step 4, reconciling the
live taint to the profile). That order keeps the two constraints below: the
agent's credential exists before its reapply timer first fires, and the node is
opened for scheduling last. The list is kept as the record of why.

**The convergence order (as written for the R5 PR).** The three
parts land in one PR but they must be APPLIED in an order, because the wrong one
leaves gmktec either over-admitting or fighting itself:

1. **Re-install the SERVER's reapply unit** from its profile
   (`install-reapply-unit.sh ci-runner/k3s/phase0-bare-metal/profiles/poweredge-xubuntu.env`)
   so the server's timer switches from the old cluster-wide LIST patch to the
   per-node by-name patch and STOPS stamping gmktec with 32. Until this runs, the
   server keeps re-writing gmktec's capacity every five minutes.
2. **Mint and seed gmktec's node-status credential**
   (`node-status-credential/provision-node-status-credential.sh` on the server,
   then `secret-reinjection/seed-node-status-kubeconfig.sh` onto gmktec) so the
   agent timer has a credential before its first fire.
3. **Install and verify the agent's reapply timer**
   (`install-reapply-unit.sh ci-runner/k3s/phase0-bare-metal/profiles/gmktec-xubuntu.env`
   ON gmktec) and confirm gmktec's `status.allocatable.ci-runner.io/churn-slot`
   reads **12**.
4. **THEN untaint gmktec.** Opening the node for scheduling is the LAST step, once
   it actually advertises 12.

**The empty `NODE_TAINTS` is not self-applying on the already-joined node.** k3s
applies `--node-taint` at node REGISTRATION only, so emptying `NODE_TAINTS` in the
profile removes the taint only for a FRESH join. `gmktec-xubuntu` is already
joined and already carries `node-role/ci=pending:NoSchedule`, so step 4 above is a
one-time `kubectl taint nodes gmktec-xubuntu node-role/ci-` at converge; the
profile change alone does not remove it from the live node. (The docs that say the
taint is "removed" mean removed from the profile — the live removal is this
explicit converge step.)

## Measured job-hours re-derivation at C = 44 (2026-10-22)

This is the dated derivation for the committed manifests. It supersedes the
podman-era weights in the historical tables above; those tables remain as a
record of earlier capacity decisions, not as inputs to the current manifests.
The measured input is the operator-host capture in
`plan/archive/gitops-fleet-capacity-monitoring/research/003-ci-pool-job-hours-7d-2026-10-22.md`:
one `cache.job-summary` Honeycomb span per k3s-pool CI job, grouped by `repo`,
from 2026-10-15T01:14:57Z to 2026-10-22T01:14:57Z. Job-hours are
`SUM(duration_ms) / 3,600,000`.

Hamilton uses the unrounded duration totals as weights: `W =
1,006,298,751.78 ms` over the ten queue-routed repositories. The displayed
job-hours and shares are rounded only for readability. With `C = 44`, the
floor allocations total 38, leaving six Hamilton units for the six largest
remainders: dev-tooling, driver-claude, driver-pi, console-beads-fabro,
driver-codex, and livespec.

| Repository | Job-hours | Exact share | Floor | Hamilton quota | Final `nominalQuota` | `maxRunners` |
|---|---:|---:|---:|---:|---:|---:|
| `livespec-orchestrator-beads-fabro` | 193.56 | 30.4674 | 30 | 30 | **29** | **58** |
| `livespec-dev-tooling` | 37.83 | 5.9545 | 5 | 6 | **6** | **12** |
| `livespec` | 10.45 | 1.6450 | 1 | 2 | **2** | **6** |
| `livespec-overseer` | 10.02 | 1.5776 | 1 | 1 | **1** | **6** |
| `livespec-orchestrator-git-jsonl` | 6.93 | 1.0914 | 1 | 1 | **1** | **6** |
| `livespec-driver-claude` | 5.58 | 0.8778 | 0 | 1 | **1** | **6** |
| `livespec-driver-pi` | 5.34 | 0.8398 | 0 | 1 | **1** | **6** |
| `livespec-console-beads-fabro` | 4.30 | 0.6765 | 0 | 1 | **1** | **6** |
| `livespec-driver-codex` | 4.27 | 0.6723 | 0 | 1 | **1** | **6** |
| `livespec-runtime` | 1.26 | 0.1977 | 0 | 0 | **1** | **6** |
| **sum** | **279.53** | **44.0000** | **38** | **44** | **44** | **118** |

The `max(1, ...)` step raises runtime from Hamilton's zero to one, temporarily
making the quotas total 45. The existing rule's excess-deduction substep then
deducts one from `livespec-orchestrator-beads-fabro` (30 → 29), the largest
quota, rather than preserve an over-reserved `C + 1` cohort. This keeps the
guaranteed floors exactly equal to the 44 registered churn slots and resolves
the earlier contradictory prose in favor of the stated apportionment rule.

`maxRunners` is `max(2 x nominalQuota, 6)` for every row. The orchestrator's
rule value is now 58, above its former recorded value of 12, so its
2026-10-19 exception is deleted: retaining it would be both unnecessary and
incorrectly below the rule. The Recorded exceptions to the rule table remains
absent because 58 is not below 12. The ten ceilings total 118; at a full
44-runner admission, at most 74 runner objects are gated in the cluster.

## The rebalance at C = 44 — hp-xubuntu opened runner-only (2026-11-03)

Work-item `livespec-dev-tooling-zreev4`, plan `kubernetes-sandbox-backend`
(epic `bd-ib-nmuyjc`, livespec-orchestrator-beads-fabro tenant); fleet
coordinator ruling of 2026-11-03. `hp-xubuntu` had joined the pool closed to CI
(`CI_NODE_FACILITIES=none`, capacity 0). It was opened under the new
`runner-only` posture with **8** churn slots, and those 8 slots were MOVED from
`poweredge-xubuntu` rather than added:

| node | before | after |
|---|---:|---:|
| `poweredge-xubuntu` | 32 | **24** |
| `gmktec-xubuntu` | 12 | 12 |
| `hp-xubuntu` | 0 | **8** |
| **cohort total C** | **44** | **44** |

**Why move slots rather than add them.** Measured read-only at about 23:55Z on
2026-11-02: `kubectl top node` read poweredge at about 98 % CPU (load about 191
on 72 cores) and gmktec at 96 %, while hp ran 3 factory sandboxes at 3.6 of its
16 cores (24 %) and 2.5 GiB (9 %). On a node pinned at 98 % CPU the CPU-bound
phases of its jobs are zero-sum, so 8 fewer concurrent jobs there cost little
throughput, and the same 8 jobs on idle hp get cores of their own. Runner pods
request no cpu or memory, only `ci-runner.io/churn-slot: 1`, so hp's request
budget (82 % held by its 3 sandboxes) does not bound them; its churn-slot
capacity does.

**Why the total stays 44.** The JIT startup batch of
`SPECIFICATION/non-functional-requirements.md` §"Adaptive JIT runner admission
budget" may spend at most 450 of GitHub's 900 REST points per minute, about 45
mint pairs, and nothing in the pool caps a cold start except the registered
capacity. `tests/consumer/test_jit_admission_scenarios.py` therefore holds the
profiles' summed capacity at or below 45. Adding hp's 8 on top (C = 52) would
let one cold start mint about 520 points; so C stays at 44.

**What does not change.** The ten `nominalQuota`s and every scale set's
`maxRunners` are exactly the "Measured job-hours re-derivation at C = 44
(2026-10-22)" values: Kueue's cohort quota is cluster-wide and the total did not
move. Only per-node PLACEMENT moves, and the scheduler enforces it: each node
advertises its own capacity (`node_extended_resource` stamps the profile's
`ADMISSION_CAPACITY_C`), so poweredge now takes at most 24 runner pods and hp at
most 8. `tests/spec/test_jit_admission_budget.py` asserts the three profiles sum
to 44 and to the cohort's quotas.

**8 is a STARTING value** for hp. Raise it, taking the same number off another
node while the startup budget caps the total, while p95 job duration on hp
grows about linearly and hp's memory holds; lower it if jobs on hp stretch or
memory pressure appears. Neither 24 nor 8 has earned a soak yet.

**Convergence order** is the R5 one: `node_status_credential`, then
`node_extended_resource` stamps hp's 8 and poweredge's 24, then `node_taints`
removes hp's `node-role/ci=factory:NoSchedule`, so hp is opened for scheduling
last. Lowering poweredge to 24 while it runs more than 24 runner pods evicts
nothing: the scheduler only stops placing new ones there until it drains below.

**Reverting** is the same two profile edits back: hp to `CI_NODE_FACILITIES=none`,
capacity 0 and the factory taint, and poweredge to 32.

## Per-node churn slots derived from cores (2026-11-04)

Work-item `livespec-dev-tooling-qt3q`, plan `kubernetes-sandbox-backend`
(epic `bd-ib-nmuyjc`, livespec-orchestrator-beads-fabro tenant), at the request
of `legacy-coordinator-agent` (P12). This section replaces the hand-picked 24 / 8
split of the 2026-11-03 rebalance with a rule.

**What went wrong at 8.** At 06:24Z on 2026-11-04 `hp-xubuntu` (16 cores,
14500m allocatable CPU, 8 churn slots) ran 6 runner pods plus their 6 workflow
pods at PSI60 40.7 and 0 % idle, while `poweredge-xubuntu` sat 33 % idle and
`gmktec-xubuntu` 54 % idle (measured by session `ci-runtime-and-cost`). The
churn slot counts JOBS. It does not weigh them by CPU, and the workflow pod that
does a job's work requests nothing, so nothing in scheduling saw that hp's
jobs were sharing a third as many cores per slot as the other nodes.

**The rule.** Each node's `ADMISSION_CAPACITY_C` is proportional to its CPU
count at ONE cores-per-slot ratio for the pool. Pool CPUs are poweredge 72 +
gmktec 32 + hp 16 = 120, and the total stays 44 (see below), so the ratio is
about 2.73 CPUs per slot:

| node | CPUs | CPUs / 2.73 | before | after |
|---|---:|---:|---:|---:|
| `poweredge-xubuntu` | 72 | 26.4 | 24 | **27** |
| `gmktec-xubuntu` | 32 | 11.7 | 12 | 12 |
| `hp-xubuntu` | 16 | 5.9 | 8 | **5** |
| **cohort total C** | **120** | | **44** | **44** |

hp rounds DOWN because its 16 cores also carry its 5-CPU gate lane ("The hp
numbers: 5 cpu and 8 Gi" below) and whatever factory sandboxes are still
draining there; poweredge takes the remainder, which keeps the sum at 44.
Recompute the same way when a node's core count or its co-tenants change.

**Why the total stays 44.** Unchanged from the rebalance section above: the
450-point JIT startup budget caps the summed capacity at 45, and the ten
`nominalQuota`s and every `maxRunners` stay at the "Measured job-hours
re-derivation at C = 44 (2026-10-22)" values. Only per-node placement moves.

**Why not a CPU request on the workflow pod.** The workflow pod's node is not
a scheduling decision. The fleet's container hook (`../container-hook/`, bundle
2.336.0, upstream v0.7.0 plus the externals patch) runs without
`ACTIONS_RUNNER_USE_KUBE_SCHEDULER`, so it copies the runner pod's node into
the workflow pod's `spec.nodeName`, which bypasses the scheduler, and the pod
shares the runner's ReadWriteOnce local-path work volume besides. A CPU request
there therefore cannot move a job to an idle node. On a node whose requests
are already full the kubelet rejects the pod at admission (`OutOfcpu`) and the
CI job fails; with the kube scheduler switched on, the hook's required node
affinity leaves it Pending until the hook's prepare timeout fails the job.
Either way, contention would turn into red jobs rather than moved ones. The
runner pod IS the placement decision, and the churn slot is what bounds it.

**Reverting** is the two profile lines back (hp 8, poweredge 24) and the same
apply: `just ansible-apply ansible/ci-pool.yml --tags node_extended_resource`.
Lowering hp while it runs more than 5 runner pods evicts nothing; the scheduler
only stops placing new ones there.

## Interim: poweredge capped at 18 (2026-11-04)

Ordered by `legacy-coordinator-agent` under R301 as a reversible stop-the-line,
until `livespec-dev-tooling-6e5pyj` derives churn slots and per-job test
parallelism together. At 13:39Z `poweredge-xubuntu` read PSI60 75.9 with 37
arc-runners pods, while `gmktec-xubuntu` read PSI60 0.4 (71 % idle) and
`hp-xubuntu` PSI60 9.2 (68 % idle). Runner pods request no CPU, so the scheduler
kept filling poweredge's free slots.

| node | cores-derived | interim |
|---|---:|---:|
| `poweredge-xubuntu` | 27 | **18** |
| `gmktec-xubuntu` | 12 | **18** |
| `hp-xubuntu` | 5 | **8** |
| **cohort total C** | **44** | **44** |

The total stays 44, because "Admission capacity sums to the cohort quota"
requires the profiles to sum to the ten ClusterQueue quotas. Cutting poweredge
alone would let Kueue admit runner pods no node can hold. The 9 slots moved to
the two idle nodes. Test parallelism stays at 3 per job.

**Revert** to 27 / 12 / 5, with the same `node_extended_resource` apply, if
gmktec or hp exceeds PSI60 about 30 under load, or if Kueue-gated runners pile up
while poweredge PSI60 is under about 25.

### Second interim step: hp back to 5, gmktec 21 (2026-11-04 ~15:45Z)

Ordered by `legacy-coordinator-agent` under R301/R493 on `ci-runtime-and-cost`'s
15:36Z read. `hp-xubuntu` ran at 15.64 of 16 cores with 5 runners. Their workflow
pods used 6.17, 2.68, 2.66 and 1.96 cores each, even at 3 test workers per job,
because `just check` runs its non-pytest targets beside the pytest lane. So 8
slots oversubscribe its 14.5 allocatable CPU. hp returns to its cores-derived
5. The 3 slots go to `gmktec-xubuntu`, the idlest node all afternoon (PSI60
0.1-0.4, 45-71 % idle). `poweredge-xubuntu` keeps 18 so the `ci-runner-scheduler`
canary (`livespec-dev-tooling-mtvxde`) can show its placement.

| node | first interim | second interim |
|---|---:|---:|
| `poweredge-xubuntu` | 18 | 18 |
| `gmktec-xubuntu` | 18 | **21** |
| `hp-xubuntu` | 8 | **5** |
| **cohort total C** | **44** | **44** |

**Revert** to 18 / 18 / 8 if gmktec's idle falls below about 5 % AND its
BestEffort CI-slice `cpu.pressure` avg60 goes above about 30. That is the
saturation signal ruled on 2026-11-04 and recorded on
`livespec-dev-tooling-6e5pyj`; host PSI is not the signal. Watch too that
gmktec's factory sandboxes keep their headroom, since gmktec carries the petri
factory.

### Third interim step: gmktec back to 18, poweredge 21 (2026-11-04 ~17:15Z)

Ordered by `legacy-coordinator-agent` (factory yield on gmktec is P1). At 17:09Z
`gmktec-xubuntu` read 4.3 % idle (5-second sample), load 48 on 32 threads,
BestEffort CI-slice `cpu.pressure` avg60 23.8 (avg10 11.0, full avg60 11.2), with 5
factory sandboxes (one 70 % CFS-throttled) and 5 CI runners, while
`poweredge-xubuntu` sat about 42 % idle. gmktec's 21 slots let CI take CPU its
factory sandboxes need. Three slots move back to poweredge.

| node | second interim | third interim |
|---|---:|---:|
| `poweredge-xubuntu` | 18 | **21** |
| `gmktec-xubuntu` | 21 | **18** |
| `hp-xubuntu` | 5 | 5 |
| **cohort total C** | **44** | **44** |


### Back to the cores-derived split: gmktec 12, poweredge 27 (2026-11-07 ~21:00Z)

Ordered by `legacy-coordinator-agent` as immediate relief, ahead of the joint
derivation (`livespec-dev-tooling-6e5pyj`). Measured 20:55-20:58Z, with factory runs
and CI both live: `gmktec-xubuntu` 0.13 idle, CI slice `cpu.pressure` avg60 46.31,
node CPU PSI60 53.78, 23 runner and workflow pods beside 5 factory sandboxes;
`poweredge-xubuntu` 25.13 idle, node PSI60 3.90, 16 such pods beside 9 sandboxes;
`hp-xubuntu` 66.56 idle, PSI60 0.43. gmktec's 18 was a hand value against a
cores-derived 12. The ratio this restores is the rule above, about 2.73 CPUs per slot.

| node | third interim | this step |
|---|---:|---:|
| `poweredge-xubuntu` | 21 | **27** |
| `gmktec-xubuntu` | 18 | **12** |
| `hp-xubuntu` | 5 | 5 |
| **cohort total C** | **44** | **44** |

This is a placement move at `LIVESPEC_TEST_PARALLELISM` 3, not the joint derivation:
it does not yet establish that slots times workers plus sandbox and gate requests fit
each node's budget. At 6 workers per job, 27 slots on poweredge already read PSI60
55.1 on 2026-11-04. REVERT: restore 18 and 21 and re-apply the role.


### gmktec to 4, cohort to 36 (2026-11-07)

Stop-the-line, routed by `legacy-coordinator-agent`; the fairness call is
`ci-runtime-and-cost`'s, which decided it. Measured ~21:40-21:45Z: dev-tooling's coverage
jobs ran 21, 38, 56, 81 and 116 minutes against about 7 clean, and `gmktec-xubuntu` read
0.04 % idle, load 110 on 32 cores, CI-slice pressure about 49. Its Burstable pods requested
27.0 CPUs (factory 4 pods 12.0, gates 3 pods 15.0), leaving about 5 for CI. Under the
throughput rule a slot past saturation adds no throughput, so the node's capacity comes
down to 4. The other nodes have no room to take the 8 slots, so the cohort drops 44 -> 36,
and all 8 come from `livespec-orchestrator-beads-fabro-cq` (25 -> 17), which held exactly 17
admitted and 0 borrowed at the decision. Its scale-set ceiling follows the rule,
max(2 x 17, 6) = 34. Node capacity and quotas change in ONE apply, so the quota-sum test
and the cluster never see them out of step.

| node | before | after |
|---|---:|---:|
| `poweredge-xubuntu` | 27 | 27 |
| `gmktec-xubuntu` | 12 | **4** |
| `hp-xubuntu` | 5 | 5 |
| **cohort total C** | **44** | **36** |

This is a step inside `livespec-dev-tooling-6e5pyj`, not its joint derivation: poweredge's
own subtraction waits on the gate-placement read. ACCEPTANCE READ: the orchestrator
check-per-file-coverage median after the apply against before, and dev-tooling's against the
figures above. REVERT: restore 12, 25 and 50 and re-apply both roles together.

## The master-push slice for livespec-dev-tooling (2026-11-03)

Work-item `livespec-dev-tooling-lzkzwb`, plan `ci-runtime-and-cost` (epic
`livespec-dev-tooling-ib3oe3`); ruled by legacy-coordinator-agent on
2026-11-03 (delegated tier), donor re-ruled the same morning. The cohort gains
an ELEVENTH member, `livespec-dev-tooling-master-cq`, and it is the first that
is not a whole repository: it is one repository's master-push events, routed to
their own scale set (`../arc/values-livespec-dev-tooling-master.yaml`, scale set
`livespec-dev-master-k3s`).

**The measurement.** Read-only over the 24 h to about 11:50Z on 2026-11-03
(`plan/ci-runtime-and-cost/research/003-master-push-ci-queue-time-2026-11-03.md`,
which carries the reproduction script): dev-tooling master-push CI jobs waited
**p90 50.7 min** (max 109.7) to start, against **p90 19.3 min** for its
pull_request jobs. Every dev-tooling master run in the release storms
(23:30–03:15Z and 08:13–10:00Z) waited 28–110 min, and overseer master runs
waited 82–116 min. A starved master is not only slow: the orchestrator
Dispatcher's master-CI preflight refuses every dev-tooling dispatch while
master CI stays pending, so master latency gates the whole factory for this
repository (items `ftgiu4` and `dnokt2` were refused).

**Why a WorkloadPriorityClass cannot fix it.** Both events name ONE `runs-on`
target, so GitHub holds ONE assignment queue for them and ARC one 12-runner
ceiling. ARC creates a runner pod BEFORE GitHub assigns it a job; the pod
carries only repo, scale-set, `patch-id` and `runner-spec-hash` labels, so
nothing at pod creation knows which event the pod will serve. A priority could
only reorder pods already inside one ClusterQueue, which are still behind the
same GitHub queue and the same ceiling. The only place the two events can be
told apart is `runs-on`, which is why the routing contract
(`SPECIFICATION/constraints.md` §"CI matrix shape", proposed change
`master-push-ci-routing`) gains `CI_RUNNER_LABELS_MASTER`.

**The slice.**

| object | value |
|---|---|
| scale set | `livespec-dev-master-k3s`, `githubConfigUrl` the same repository, pod label `kueue.x-k8s.io/queue-name: livespec-dev-tooling-master-lq` |
| `maxRunners` | max(2 × 3, 6) = **6** ("Bounding maxRunners to the quota (2026-09-06)") |
| ClusterQueue | `livespec-dev-tooling-master-cq`, cohort `fleet-ci-runner-pool` |
| `nominalQuota` (churn-slot) | **3** |
| `lendingLimit` (churn-slot) | **0** |
| preemption | `reclaimWithinCohort: Never`, `borrowWithinCohort.policy: Never`, `withinClusterQueue: Never` (stated explicitly) |
| `fairSharing.weight` | 1, as every sibling |

The ruled name was `livespec-dev-tooling-master-k3s`, which is 31 characters
and breaks `../README.md` "`runnerScaleSetName` MUST stay <=30 characters". By
that rule's mechanical truncation the repo-name portion becomes the longest
hyphen-bounded prefix that fits the 19 characters left after `-master-k3s`,
`livespec-dev`. The LocalQueue and ClusterQueue keep the full name.

**The donor, and the re-ruling.** The first ruling took the 3 slots from
dev-tooling's own 6 (6 → 3) and gave the master set `maxRunners` 9. It was
withdrawn: under "Bounding maxRunners to the quota (2026-09-06)" a quota of 3
sets dev-tooling's ceiling to max(2 × 3, 6) = 6, halving its pull-request
ceiling from 12 to 6. That ceiling is the binding term today: the
`kubernetes-sandbox-backend` measurement of 11:10–11:15Z on 2026-11-03 showed
the GitHub-side wait is the ARC ceiling, not Kueue admission, so halving it
would have moved the queue from master onto PRs rather than removed it. The
re-ruled donor is `livespec-orchestrator-beads-fabro`, which at 11:10Z was
running 13 of its 58 runners:

| ClusterQueue | `nominalQuota` before | after | scale set `maxRunners` before | after |
|---|---:|---:|---:|---:|
| `livespec-orchestrator-beads-fabro-cq` | 29 | **26** | 58 | **52** |
| `livespec-dev-tooling-cq` | 6 | 6 | 12 | 12 |
| `livespec-dev-tooling-master-cq` | — | **3** | — | **6** |
| every other member (8 queues) | 9 | 9 | 48 | 48 |
| **cohort sum** | **44** | **44** | **118** | **118** |

The eleven quotas still sum to exactly C = 44, so "The rebalance at C = 44"
and the per-node capacities are untouched. The eleven ceilings still total
118 (the orchestrator's −6 is the new set's +6), so at a full 44-runner
admission at most 74 runner objects are gated in the cluster, as before. The orchestrator's
rule value 52 remains above its long-deleted 12-runner exception. The
Recorded exceptions to the rule table remains absent because 52 is not below
12.

**Why `lendingLimit: 0`.** Every other member lends its whole unused floor,
which is Kueue's default and what makes "Repositories MAY fairly borrow unused
capacity" real. The master slice must not, because reclaim is Never in this
cohort (the standing "NEVER EVICT A HEALTHY RUNNING JOB" directive above): a
lent master slot would be borrowed by a pull-request backlog and would come
back only when that borrower's job finished — the very wait the slice exists to
remove. With `lendingLimit: 0` Kueue reserves `nominalQuota − lendingLimit` = 3
slots for the slice's exclusive use, so the lendable pool the other ten draw
on is 41, not 44. The price is up to 3 of 44 slots (7 %) idle while no master
run is queued. The slice may still BORROW above its 3 from idle peers, up to
its 6-runner ceiling. `lendingLimit` is beta and enabled by default at the
pinned Kueue v0.19.1 (v1beta2 ClusterQueue CRD in
`core/upstream-manifests-v0.19.1.yaml`).

**Why preemption stays Never.** Preemption would get master its slots faster
by evicting PR jobs mid-run, which the directive above forbids outright. The
reservation buys the same property — a master job starts as soon as a reserved
slot is free — without killing work in flight.

**The watch item.** The donor gives up 3 guaranteed slots and 6 ceiling. For
24 h after the change, measure `livespec-orchestrator-beads-fabro`
pull_request p90 job wait (research 003's script, pointed at that repository)
and tell the coordinator if it worsens materially before `bd-ib-xufdwx` lands.

**The order** (Ordering — confirm the reader before you write):

1. Converge the ClusterQueue and LocalQueue, then the scale set (and the
   donor's lowered quota and ceiling) — `reconstruct/converge-ci-stack.sh`
   applies every `cluster-queue-*.yaml` in step 5 and every scale set in its
   `SCALE_SETS` map in step 7.
2. Confirm the `livespec-dev-master-k3s` listener has REGISTERED with GitHub
   (the listener pod is Running and the scale set appears under the
   repository's runner scale sets), and that `kubectl get clusterqueue`
   shows the new queue with quota 3 and the eleven quotas summing to 44.
3. Only then set `CI_RUNNER_LABELS_MASTER` to `["livespec-dev-master-k3s"]`
   through `../../set-ci-runner-labels.sh`'s guarded path. Until it is set the
   `ci.yml` expression falls through to `CI_RUNNER_LABELS` and the new scale
   set idles at zero runners; setting it first would route master pushes to a
   target with no listener, and they would queue forever.

Reverting is deleting `CI_RUNNER_LABELS_MASTER` (pushes return to
`CI_RUNNER_LABELS` at once), then the reverse of the manifest change.

## The fabro fork scale set (2026-11-05)

Work item `bd-ib-dqxcsh`, part (a) (livespec-orchestrator-beads-fabro tenant),
routed by `legacy-coordinator-agent`. The cohort gains a TWELFTH member,
`fabro-cq`, for `thewoolleyman/fabro`: the fleet's Rust fork of Fabro, and the
first routed repository that is not a livespec repository (no beads tenant, no
spec). Its format, clippy and nextest jobs (later a release-binary build) move
here off the dev host. The fork's jobs declare a `container:` image
(buildpack-deps:noble + musl-tools) and run as root in the workflow pod; no
Docker daemon is offered, which was accepted.

| object | value |
|---|---|
| scale set | `fabro-k3s` (`../arc/values-fabro.yaml`), the name promised to the fork's owner; 9 characters |
| `githubConfigUrl` / secret | `https://github.com/thewoolleyman/fabro` / `arc-github-app-installation`, the one shared installation |
| LocalQueue / ClusterQueue | `fabro-lq` / `fabro-cq` (`cluster-queue-fabro.yaml`), cohort `fleet-ci-runner-pool` |
| `nominalQuota` (churn-slot) | **1**, donated by `livespec-orchestrator-beads-fabro-cq` |
| `lendingLimit` | not set: lends its whole unused floor, as every member but the master slice |
| preemption | the API defaults, all `Never`, as every per-repo queue |
| `minRunners` / `maxRunners` | 0 / **2**, a recorded exception (below) |
| work volume request | **112Gi**, not enforced (below) |
| placement | `nodeSelector: kubernetes.io/hostname: poweredge-xubuntu` |
| cpu / memory requests | none, as every scale set |

**Prerequisite, measured.** The `thewoolleyman-ci-runners` App installation did
NOT cover `thewoolleyman/fabro` at about 06:5xZ on 2026-11-05; the maintainer is
adding it. Converge only after it does (order below).

### Why a donation, and why 1

The fork has never run on this pool, so it has no `cache.job-summary`
job-hours for the measured Hamilton derivation of 2026-10-22 to apportion. It
joins the way the master-push slice did: a ruled donation that keeps the
cohort at exactly C = 44. C cannot grow to make room: the 450-point JIT startup
budget caps the summed node capacity at 45 (`tests/consumer/test_jit_admission_scenarios.py`).

The coordinator asked whether the fork could borrow only, at `nominalQuota` 0.
The apportionment rule above says no: step 5 gives no repository a floor of
zero, because with reclaim `Never` a borrow-only queue under a saturated cohort
waits for a borrower's job to end and can lose that slot again to any queue
still under its own floor. A floor of 1 means a fork job waits at most for one
borrower's job to finish. More than 1 would reserve capacity a three-job fork
cannot use behind a ceiling of 2.

**The donor is `livespec-orchestrator-beads-fabro`**, for the reasons the master
slice re-ruling recorded: it holds the largest quota (the queue the excess-deduction
step takes from), and its ceiling did not bind (13 of 58 runners at 11:10Z on
2026-11-03). `livespec-dev-tooling` is not a donor, because a quota of 5 would
cut its ceiling from 12 to 10, and that ceiling WAS the binding term in the
same measurement.

| ClusterQueue | `nominalQuota` before | after | scale set `maxRunners` before | after |
|---|---:|---:|---:|---:|
| `livespec-orchestrator-beads-fabro-cq` | 26 | **25** | 52 | **50** |
| `fabro-cq` | — | **1** | — | **2** |
| every other member (10 queues) | 18 | 18 | 66 | 66 |
| **cohort sum** | **44** | **44** | **118** | **118** |

The twelve quotas still sum to C = 44, so the per-node capacities are
untouched, and the ceilings still total 118, so at a full 44-runner admission at
most 74 runner objects are gated in the cluster, as before. The orchestrator's
24-hour watch item from the master slice applies again, for one slot and two
ceiling.

### Why `maxRunners` is 2, not the routed 1 and not the rule's 6

The routing asked for a maximum of 1. One is not reachable under the
specification. `SPECIFICATION/non-functional-requirements.md` §"Adaptive JIT
runner admission budget" requires each ceiling to be "large enough that a
repository can borrow unused capacity beyond its guaranteed share", and
`tests/consumer/test_jit_fleet_capacity_scenarios.py` holds that clause. With the
floor at 1, a ceiling of 1 can never borrow. The only way to keep 1 is
`nominalQuota` 0, which step 5 forbids, or a ratified change to that clause.
2 is the smallest ceiling both rules allow.

The rule value is `max(2 x 1, 6)` = 6, and 6 is refused for disk, not CPU. The
floor of 6 exists so a small-quota repository does not drain a 13–21-job matrix
one job at a time. The fork's matrix is three jobs, and each needs a work volume
of about 100 GiB (below). Six concurrent volumes would be about 670 GiB of the
1.5 TiB `ci-workvols` tier every runner on poweredge shares, and `local-path`
would not refuse the seventh byte. 2 keeps the rule's multiple and waives only
its floor. See "Recorded exceptions to the rule" below for the row and its
acceptance check.

### The work volume: 112Gi requested, nothing enforced

The fork's owner measured on the dev host on 2026-11-05: a cold workspace
clippy + nextest DEBUG build wrote about 92 GiB of target output, and the
release target is 6.1 GiB. One job that builds both writes 98.1 GiB. The
per-volume seeds are capped by committed budgets: uv at or under 1.0 GB and
action archives at or under 0.27 GB (`../warm-cache/warm-cache-cronjob.yaml`),
plus the runner externals at about 0.6 GB. The checkout is ASSUMED at about
1 GB, because it was not measured. That totals about 101 GB. With 10 % headroom
the request is **112Gi**.

The number is a statement, not a bound. `local-path` is a mkdir-only
provisioner with no size enforcement and no capacity tracking, so the scheduler
never compares the request with a node's free space. What bounds the volume is
the free space of the `ci-workvols` tier on the node the runner lands on,
shared by every runner volume there, and the volume's deletion with its runner
pod. The dev-host figure was taken with cargo's default `incremental = true`.
The pool's job container gets `incremental = false` from the hook template's
postStart, so the pool figure should be smaller. That is unmeasured.

**Placement.** The runner pod is pinned to `poweredge-xubuntu`, the first scale
set to carry a pin. The workflow pod follows it: the fleet hook copies the
runner's node into `spec.nodeName`, and the `WaitForFirstConsumer` volume binds
there. The tier sizes come from the committed profiles' `LOGICAL_VOLUMES`:

| node | where its runner volumes live | size | why (not) |
|---|---|---:|---|
| `poweredge-xubuntu` | `ci-workvols`, XFS on NVMe (`nvmeb`) | 1.5 TiB | the most room; 72 CPUs and 377 GiB RAM for the link step |
| `gmktec-xubuntu` | `ci-workvols`, XFS (`nvmea`) | 525 GiB | shared by 18 slots; it carries the petri factory, whose yield is P1 |
| `hp-xubuntu` | `/srv/sandbox-storage/runner-workvols`, ext4 | (3.6 TiB volume) | the same filesystem holds k3s's data directory, so filling it takes k3s down there; 30 GB RAM |

The cost of the pin: while poweredge's churn slots are all taken, an admitted
fabro runner pod waits Pending for one there, holding its Kueue admission. At
`maxRunners` 2 that is two pods at most. Measurement owed before routing: the
free space of poweredge's `ci-workvols` mount (`/var/lib/rancher/k3s/storage`),
read on the node at converge time. The 1.5 TiB is the volume's size, not its
free space.

### CPU and memory: the churn slot alone, as for every lane

No cpu or memory request goes on the runner pod or the workflow pod. "Per-node
churn slots derived from cores (2026-11-04)" above records why a request on the
workflow pod cannot work here. The hook copies the runner's node into
`spec.nodeName` and so bypasses the scheduler, which means contention would
show up as `OutOfcpu` job failures, not as moved jobs. The workflow pod is also
built from the SHARED `../arc/hook-pod-template.yaml`, which this lane must not
change. The churn slot is the admission control. The per-job CPU bound is the
shared template's `CARGO_BUILD_JOBS=3` and `NEXTEST_TEST_THREADS=3`. That is the
same bound the console's Rust lane runs under, so a fabro job weighs about what
one churn slot is sized for (about 2.73 CPUs per slot). The fork's workflow must
not set `CARGO_BUILD_JOBS` itself, because a step-level value wins over the pod
env.

**Not measured:** no fabro job has run on any pool node, so there is no figure
for its CPU, its peak memory (rustc at `-j3` plus the link step), or its
wall-clock time on the pool. No request is proposed, so no number is invented
for one. The measurement that confirms the choice is the first cold run's
workflow pod, read from the host collector's `kubeletstats` in Honeycomb:
`k8s.pod.memory.working_set` and `k8s.pod.cpu.usage` for the
`fabro-k3s-*-workflow` pod, the job's duration, and `du` of its target
directory. Poweredge's 377 GiB is the reason a peak of several GiB is not a
risk there. On hp it would have been.

### sccache: the hook's read path, and the populator's write path

**Reading needs no change.** The hook template's postStart writes the
`rustc-wrapper` stanza to `/.cargo/config.toml` when the node-local binary
(`/opt/ci-runner/bin/sccache`) and `sccache-redis` answer. It points at
`ci-sccache` as the unauthenticated READ_ONLY user, and cargo reads that
config from the checkout's ancestors whatever the job image is. The fork's
`container:` image carries `/bin/sh`, which the postStart needs.

**No write mode for this lane, by the specification.** §"Runner-pool build
cache tiers" **Trust by construction**: a job MUST NOT be able to write any
shared cache, and the populator is the one writer.

**The populator becomes fabro's writer AUTOMATICALLY, and that is the open
risk.** `../warm-cache/converge-warm-cache.sh` derives the routed-repository
list from every `githubConfigUrl` under `../arc/values-*.yaml`. So this values
file adds `thewoolleyman/fabro` to the next warm-cache converge. The populator
then does four things for it. It clones the fork. It runs `cargo fetch
--locked` through the crates proxy. While Kueue's admitted-workload count is at
or under 16, it builds the default branch as the sccache writer:
`build --workspace --all-targets --all-features`,
`test --workspace --all-features --no-run`,
`check --workspace --all-targets --all-features` and `build --release --workspace`,
at `/__w/fabro/fabro` on the CronJob pod's own root filesystem on the
cache-carrier node. That pod has a 6-CPU and 8Gi limit and a 3600 s
`activeDeadlineSeconds`. Its target output is the ~98 GiB above, written to the
container layer. Finally it adds the fork's pinned `uses:` actions to the
action-archive seed. `https://github.com/thewoolleyman/fabro` sorts before
every `livespec-*` URL, so the fork's writer build runs FIRST in the cargo loop.
A fork build that outlives the deadline kills the pod before the console's
writer build and the action-archive refresh run. Any failed step (an
`--all-features` set that does not build, a toolchain the image lacks, an
OOM at 8Gi) leaves the marker unset, so the build is retried on every idle
tick. None of this is measured. It must be decided before the converge. One
choice accepts it and measures the first populate run. The other keeps the
fork out of the populator's writer build until that build is sized. The
populator has no per-repository opt-out today.

Also measure, after the first writer build, whether fabro jobs actually HIT. The
hook template's own header says sccache hashes every `CARGO_*` environment
variable into the key. The template has set `CARGO_BUILD_JOBS=3` in every job
container since 2026-11-04, and the populator's writer environment sets none.

### The order (Ordering — confirm the reader before you write)

1. The App installation's selection covers `thewoolleyman/fabro`, and the
   fork's fork-pull-request approval tier reads `all_external_contributors`.
2. poweredge's `ci-workvols` free space is read on the node, and the populator
   question above is decided.
3. Converge: `reconstruct/converge-ci-stack.sh` applies `cluster-queue-fabro.yaml`
   and the donor's lowered quota in step 5, and `fabro-k3s` and the donor's
   lowered ceiling in step 7.
4. Confirm the `fabro-k3s` listener has REGISTERED with GitHub, and that
   `kubectl get clusterqueue` shows `fabro-cq` at 1 with the twelve cohort
   quotas summing to 44.
5. Only then let the fork's workflows name `fabro-k3s`. Before that, a job
   naming it queues forever at GitHub with no listener to take it.

Reverting is the fork's `runs-on` back to its previous runner, then the
reverse of this manifest change (orchestrator 25 → 26 and 50 → 52, and
`helm uninstall fabro-k3s -n arc-runners` plus `kubectl delete -f
cluster-queue-fabro.yaml`, because the converge applies files and never prunes
a release or queue that has lost its file).

## Bounding maxRunners to the quota (2026-09-06)

Maintainer decision 2026-09-06 (livespec plan `poweredge-raid-array-maintenance`,
epic `livespec-g52yrb`; capacity owner epic `livespec-ifwnqj`), about two hours
after the step back to C = 32. Until this section every scale set's `maxRunners`
was read as the formula's `doubled repository logical ceiling` — the repository's
own matrix width doubled, or the podman-era weight standing in for it — and the
ten values summed to 574 against a quota sum of 32.

**What that costs.** An ARC listener creates one `EphemeralRunner` per queued
job up to `maxRunners`, and each becomes a runner pod at once. Kueue gates the
pod until a churn slot inside the repository's quota is free. A gated pod does
no work, but it is not free: it is an `EphemeralRunner`, a pod, a Kueue
`Workload` and a stream of events, and the ARC controller and Kueue rewrite all
of them every reconcile for as long as it waits. Every rewrite goes through
kine's single writer. The first fleet-wide backlog on the tiered host at C = 32
(2026-09-06 07:38Z–07:50Z) measured it: 119 pending Kueue workloads, 122 runner
objects with no phase, 25–30 running, and 11 `Slow SQL` lines in ten minutes
with kine inserts of pods, events, ephemeralrunners and workloads taking
1.2–1.7 s on the tmpfs datastore — worse than the 64-slot burst two hours
earlier, because the write volume scales with the DEPTH OF THE BACKLOG, not with
the admitted count. The cap cannot fix that; only the number of objects the
backlog is allowed to become can.

**The rule.** For every scale set:

```text
maxRunners_i = max(2 x nominalQuota_i, 6)
```

- The `2 x` preserves cohort borrowing: a repository whose peers are idle can
  still scale to twice its guaranteed floor, which is the case the earlier
  "Two enforcement points, two DIFFERENT numbers" correction protected.
- The floor of 6 keeps a small-quota repository (`nominalQuota` 1 at C = 32)
  from draining a lone 13–21-job matrix one or two jobs at a time on an
  otherwise idle host; six waves is a bounded cost, thirteen is not.
- The bound on gated objects at a fleet-wide backlog is the sum of the
  ceilings minus what is running: `76 − 32 = 44` at C = 32, against 122
  measured and 542 possible before.

At C = 32 the ten values are:

| Repository | `nominalQuota` | `maxRunners` before | `maxRunners` now |
|---|---|---|---|
| `livespec` | 5 | 64 | **10** |
| `livespec-driver-codex` | 4 | 67 | **8** |
| `livespec-driver-claude` | 4 | 66 | **8** |
| `livespec-orchestrator-git-jsonl` | 4 | 66 | **8** |
| `livespec-overseer` | 4 | 65 | **8** |
| `livespec-runtime` | 4 | 64 | **8** |
| `livespec-dev-tooling` | 4 | 63 | **8** |
| `livespec-orchestrator-beads-fabro` | 1 | 42 | **6** |
| `livespec-console-beads-fabro` | 1 | 64 | **6** |
| `livespec-driver-pi` | 1 | 13 | **6** |
| **sum** | **32** | **574** | **76** |

**What does not change.** The running count is set by the quotas and the
node capacity exactly as before, so throughput is untouched. A queued job that
cannot run yet stays on GitHub's side as a queued job, which costs the cluster
nothing, instead of becoming a gated pod. The one cost is start latency: when
a slot frees, a runner is created on demand rather than un-gated, a few
seconds per job against the minutes of queue wait a backlog already imposes.

**Recompute with the quotas.** `maxRunners` now tracks `nominalQuota`, so a
capacity change re-derives both; "Recomputing at another C" carries the step.
The specification clause this bounds — livespec-dev-tooling
`SPECIFICATION/non-functional-requirements.md`'s "doubled repository logical
ceiling" — is amended by the proposed change
`scale-set-ceiling-bounded-to-fair-share` filed the same day.

### Recorded exceptions to the rule

A scale set MAY carry a `maxRunners` other than `max(2 x nominalQuota, 6)`
only as a recorded exception: a row in the table below, with the measurement
that justifies it and the acceptance check that will confirm or revert it. An
exception is a fact about one repository. It is not a new multiple, and the
rule still derives every other scale set. It may move a ceiling above the rule
or below it, but never down to the quota: the specification's ceiling clause
requires room to borrow beyond the guaranteed share, so `maxRunners >
nominalQuota` holds for every row. `tests/spec/test_jit_admission_budget.py`
holds each ceiling to the rule or to its row here, and
`tests/consumer/test_jit_fleet_capacity_scenarios.py` carries the same table.
The first exception, `livespec-orchestrator-beads-fabro` at 12 (2026-10-19),
was deleted on 2026-10-22, when the rule itself exceeded it.

| Repository | `nominalQuota` | Rule value | `maxRunners` | Recorded |
|---|---|---|---|---|
| `fabro` | 1 | 6 | **2** | 2026-11-05 |

**`fabro`, 6 to 2 (2026-11-05).** The rule's 2x multiple is kept and its floor
of 6 is waived. The floor protects a small-quota repository with a 13–21-job
matrix, and the fork's matrix is three jobs. Each fork job needs about a
100 GiB work volume that `local-path` does not bound, so six concurrent jobs
would put about 670 GiB on the `ci-workvols` tier every poweredge runner
shares. The evidence, the measurement and the arithmetic are in "The fabro fork
scale set (2026-11-05)" above. The acceptance check is the first cold fabro run
on the pool. It passes when that job's work volume peaks under its 112Gi
request, poweredge's `ci-workvols` keeps the free space it had before the run,
and kine's `Slow SQL` rate does not rise. If the pool's target output proves
small (well under about 40 GiB per job), the disk reason no longer holds: drop
this row and take the rule value 6. If a fork push regularly waits on its own
ceiling while poweredge has free slots and free tier space, raise it here with
that measurement.

## The gates quota on gmktec-xubuntu and hp-xubuntu (2026-11-03)

**This section derives a quota that is NOT part of the apportionment above,
and the ten repositories' churn-slot sum is unchanged by it.** It covers
`cluster-queue-gates.yaml` — the gmktec `gates-flavor` and hp
`gates-hp-flavor` ResourceFlavors, the `gates-cq` ClusterQueue, the
`gate-priority` WorkloadPriorityClass and the `gates-lq` LocalQueue that give
GATE Jobs (the `just check` aggregate, offloaded to the fleet's gate-capable
pool nodes) somewhere to be admitted. The gmktec lane was filed under the
livespec plan `k3s-on-gmktec-for-vps-usage`, epic `livespec-sab5gn`, R4 slice
3; the hp lane is livespec-dev-tooling-ytk6bp.

### It is quota'd on cpu/memory, not on `ci-runner.io/churn-slot`

A gate is not a CI runner and must not spend a CI runner's admission budget.
Quota'ing gates on the extended resource would mean each admitted gate is one
fewer runner admitted fleet-wide — drawing down the very budget the gmktec
plan exists to relieve. So `gates-cq` covers plain `cpu` and `memory` over its
own flavor, exactly as `cluster-queue-phase1-proof.yaml` does, and it is
therefore excluded from the apportionment table: it cannot consume a churn
slot, and the ten `nominalQuota` values still sum to exactly `C`.

For the same reason it sets no `cohortName`. A cohort exists so members lend
and borrow unused quota; every member of `fleet-ci-runner-pool` is denominated
in `ci-runner.io/churn-slot` over `churn-slot-flavor`, which `gates-cq` neither
covers nor sits on. Membership could only ever be inert.

### It does not preempt, and `gate-priority` is not a preemption lever

The plan's research/000 proposed a `WorkloadPriorityClass` so that a gate
"preempts a queued runner". That is not available and is not being taken. The
section "`fairSharing.weight` is deliberately left at 1, and is currently
inert" above records the standing maintainer declaration of 2026-08-30 — never
evict a healthy running job to rebalance the cohort — which fixes
`preemption.reclaimWithinCohort`, `preemption.borrowWithinCohort.policy` and
`preemption.withinClusterQueue` at `Never` for the pool. Reversing it is not
this slice's to do.

`gates-cq` restates those same three values explicitly (they are also the
pinned Kueue v0.19.1 API defaults) rather than relying on the defaults, because
this is the queue a future reader reaches for when they want a gate to jump a
line, and the answer should be visible in the object.

A DEDICATED QUOTA buys what preemption was asked for. The property wanted was
"a gate does not wait behind the CI backlog"; separate capacity on a separate
node delivers it without evicting anything. `gate-priority` (value 1000) then
orders gates AMONG THEMSELVES — which of four queued gates takes the slot that
frees — and orders nothing against a runner.

### The gmktec numbers: 15 cpu and 24 Gi

**Envelope.** The plan's research/001 section 3 item 5 found about **50 GiB**
available to pods on gmktec-xubuntu without evicting the local LLM model from
its 64 GiB firmware iGPU carveout (a carveout the node's profile,
`../../phase0-bare-metal/profiles/gmktec-xubuntu.env`, records as off-limits to
everything in this tree).

**Gate shape.** A `just check` aggregate is estimated at roughly **5 cpu /
6 Gi**.

**Concurrency target.** **3** concurrent gates — enough that a gate and a
re-run do not serialize, small enough to leave most of the envelope for the
node's system pods and anything else the plan later places here.

So:

| term | arithmetic | value |
|---|---|---|
| cpu | 3 gates x 5 cpu | **15** |
| memory, if it tracked the estimate | 3 gates x 6 Gi | 18 Gi |
| memory, as set | 18 Gi + one gate's headroom | **24 Gi** |

The memory number is deliberately NOT `3 x 6`. Setting it at the estimate
would make memory the binding term the moment one gate's peak RSS exceeds
6 Gi, and nobody has measured a gate's peak RSS on this node. At 24 Gi **cpu
binds first at exactly three gates**, which is the intended behaviour, and an
over-running gate degrades throughput instead of blocking admission outright.
24 Gi is about half the ~50 GiB envelope, leaving roughly 26 GiB for the
node's system pods and future non-gate workload.

**THIS IS A FIRST ESTIMATE TO CONFIRM BY SOAK, NOT A MEASUREMENT.** Both the
5 cpu / 6 Gi gate shape and the concurrency target of 3 are estimates; only the
~50 GiB envelope is measured. What a soak must settle: a gate's actual peak cpu
and RSS, whether three concurrent gates are what the node can absorb without
the iowait signature the PowerEdge taught this fleet to watch for, and whether
`cpu` remains the right binding term. Revise both numbers here when it does,
and record the measurement rather than replacing one estimate with another.

### The hp numbers: 5 cpu and 8 Gi

**Envelope.** hp-xubuntu advertises 14500m CPU and 27.2 GiB allocatable. It is
runner-only with eight churn slots and no taint, but three existing factory
sandboxes can still account for 12 CPU / 22890 MiB while they drain. The host
now declares `FACTORY_NODE=false`, so no new factory placement can refill that
contention.

**Concurrency target.** One gate. A gate requests 5 CPU and 6 GiB; the hp
lane sets 5 CPU / 8 GiB so CPU admits exactly one and memory leaves two GiB of
headroom. That gate fits once the drain leaves at most two of the existing
4-CPU sandboxes. A second gate would not fit within the node's allocatable CPU
beside that bounded residual load, so no second hp quota is declared.

**Warm UV.** hp carries no `ci-workvols` tier, so the generic warm-UV DaemonSet
cannot use its `/var/lib/rancher/k3s/storage/.warm` hostPath. The hp-specific
UV-only DaemonSet instead writes
`/srv/sandbox-storage/runner-workvols/.warm`, the sibling of the runner-only
profile's `RUNNER_WORKVOL_DIR`. The local-path provisioner consequently seeds
an hp-admitted gate's generic ephemeral PVC from a verified generation, rather
than running it cold; the cache-tier singleton remains pinned elsewhere.

**This is a first estimate to confirm by soak.** The host-captured acceptance
window for livespec-dev-tooling-ytk6bp measures normal fleet activity for at
least two hours and requires no gate admission wait over 15 minutes. It decides
whether one hp lane is sufficient and records any later quota revision.

### The PowerEdge lane and the flavor order (2026-11-07)

**What was wrong.** `gates-cq` admitted at most four gates: three on gmktec,
tried first, and one on hp. On 2026-11-07 at 21:09Z gmktec-xubuntu was 0% idle
with CI-slice CPU pressure avg60 52, which is saturation by the 2026-11-04
ruling recorded in `.ai/ci-node-capacity-reads.md`. poweredge-xubuntu was
18.6% idle, with that pressure at 0.06 and 31 of 72 CPU requested, and it had
no gate flavor. Twelve gate Jobs were queued, the oldest Suspended for 19
minutes. A hand commit or push waits silently on its Job, because lefthook
holds hook output until the hook ends, so queue wait plus run time crossed
gate-start's 900 s stall window, and the killed client's Job stayed queued
while the retry added another.

**Why admission did not see it.** Topology-aware admission (next section)
subtracts the REQUESTS of pods Kueue does not manage. CI runner pods request no
CPU, only `ci-runner.io/churn-slot`, so a node that runners saturate still
reads as free, and a gate's 5-CPU request then takes CPU from them by CFS
weight. Nothing in admission reads real CPU use on any node.

**What changed.**

- The hp lane rises to 10 cpu / 16 Gi, two gates, and is tried FIRST. Its
  factory sandboxes have drained under `FACTORY_NODE=false`. At 21:38-21:40Z it
  used 7.5-11.7 of its 16 cores.
- A new `gates-poweredge-flavor` lane of 10 cpu / 16 Gi, two gates, tried
  second. The node is the cache-tier carrier, so a gate's ephemeral PVC is
  reflink-seeded from the warm-UV generation there, and the gates mirror and
  PyPI proxy are local. It was 18.6% idle with CI-slice pressure 0.06 at
  21:09Z, but 0.4% idle with pressure 23 at 21:38Z. That is near the saturation
  rule, so the lane starts at two gates, not three.
- gmktec's lane is unchanged at three gates, but it is tried LAST. It read 0.2%
  idle with CI-slice pressure 50 at 21:38Z. Flavor order is placement
  preference, because Kueue admits on the first flavor whose node has room.
- The gates test requires one gates flavor per `ci_pool` inventory host, so a
  node that joins the pool later cannot be left out of the gate queue by
  omission. It asserts the lanes' shape, not their sizes, as
  `SPECIFICATION/contracts.md` §"Tests never pin committed configuration
  values" requires.

**What this does not fix.** The order is static and rests on one read, and
between 21:09Z and 21:38Z the PowerEdge moved from 18.6% to 0.4% idle. Admission
that follows real CPU use is tracked as livespec-dev-tooling-gvo7fa.

**First estimates to confirm by soak.** Ruled by legacy-coordinator-agent under
R301 at 21:15Z, recorded on `livespec-dev-tooling-6tgd2z`. That ruling
supersedes the 2026-09 line that kept gates off the PowerEdge, whose premise
had inverted.

### Fastest-first flavor order (2026-11-09)

**What was wrong.** The 2026-11-07 order (above) tried hp-xubuntu first, from a
single read in which hp had spare cores. By 2026-11-09 hp was the slowest
gate node: ci-runtime-and-cost measured gate jobs there at 3.2 to 6.4 times
their gmktec-xubuntu wall time, with hp 0.14% idle and CI-slice CPU pressure
avg60 33. Because hp was first, it received most gates, and their 10 cpu of
requests took CPU from hp's own CI slots by CFS weight.

**What changed.** Only the order of `gates-cq`'s fleet flavors. It is now
fastest-first: `gates-flavor` (gmktec-xubuntu), then `gates-poweredge-flavor`,
then `gates-hp-flavor` last. Every lane keeps its 2026-11-07 size. An enrolled
container-worker flavor still comes ahead of all three, because
`converge-worker-queues.sh` rebuilds the list as worker flavors followed by the
committed order. Ruled by legacy-coordinator-agent at 11:5xZ, priority 3,
explicitly as a value-only change and not livespec-dev-tooling-gvo7fa's
load-following design. The fallback, had it not been applied by 13:00Z, was
for ci-runtime-and-cost to cut hp's CI slots.

**Revert.** Restore the order `gates-hp-flavor`, `gates-poweredge-flavor`,
`gates-flavor` in `cluster-queue-gates.yaml`, apply that file on the k3s
server, then rerun `./converge-worker-queues.sh` so the worker flavor returns
to first place.

**What this does not fix.** The order is still static. gmktec read saturated
on 2026-11-07, so this trades one measured read for another. Admission that
follows real CPU use is still livespec-dev-tooling-gvo7fa. The after-read (one
gate's wall time, and hp's best-effort pressure) is recorded on the plan epic
livespec-dev-tooling-6vuiwe.

### Topology-aware admission on the gates flavors (2026-11-04, livespec-dev-tooling-cikd6m)

**What was wrong.** Quota is not capacity. On 2026-11-04 at 01:35Z,
gmktec-xubuntu had 32 allocatable CPU and 30 requested. Six factory `petri-*`
sandbox pods requested 4 CPU each, 24 CPU in all. Kueue does not manage those
pods, so they did not count against `gates-cq`. Kueue admitted
`job-gate-livespec-dev-tooling-4pk86-7eff7` in 0 s against the 15-CPU
`gates-flavor` quota. Its pod then sat Pending ("Insufficient cpu") for 30
minutes until Kueue evicted it with `PodsReadyTimeout` and requeued it. It was
finally admitted on hp 43 minutes after creation. A static quota cut cannot
fix this, because the factory's footprint on gmktec moves: 6 sandboxes at
01:35Z, 4 at 02:07Z. legacy-coordinator-agent ruled the static cut out under
R301.

**What changed.** A `gates-hostname` Topology with the single level
`kubernetes.io/hostname`, and `topologyName: gates-hostname` on both
`gates-flavor` and `gates-hp-flavor`. Kueue v0.19.1's Topology-Aware
Scheduling (TAS) is beta and on by default. It admits a gate on a flavor only
when that flavor's node has FREE capacity for it:

- the node's allocatable,
- minus the container requests of every pod Kueue does not manage (the
  factory sandboxes, DaemonSets, system pods),
- minus admitted TAS usage.

That is the scheduler's own view of the node, read live, so nothing here is
static. The 15 / 5 nominal quotas stay as UPPER bounds on concurrent gates
per node.

- **Implicit.** When every flavor of a ClusterQueue has a topology, v0.19.1
  applies TAS to unannotated PodSets (`isTASImplied` in
  `pkg/scheduler/flavorassigner/tas_flavorassigner.go`). The gate Job template
  therefore carries no TAS annotation, and no consumer pin had to move. A
  THIRD flavor added to `gates-cq` without a topology would silently turn TAS
  off for unannotated gates, so give any new gates flavor the same
  `topologyName`.
- **Spill.** A gate that cannot be placed on gmktec falls through to hp, under
  v0.19.1's `PreserveFlavorScanProgress`, which is on by default.
- **Trade-off, accepted under R301.** The factory now takes gmktec's CPU first,
  and a gate that does not fit waits in Kueue or spills to hp. It no longer
  waits as an admitted pod that cannot start. The `bd-ib-plon2p` placement
  reconciler (kubernetes-sandbox-backend) keeps one gate lane open on a TAS
  node by reserving min(unused gates quota on that node, CAP). CAP is that
  reconciler's committed setting and defaults to 5 CPU, one gate. It switches
  to the capped reserve when it sees `.spec.topologyName` set on the node's
  gates flavor.

**Proof before apply.** This ran on a throwaway kind cluster: two 18-CPU
workers, and Kueue installed from `core/` in this directory. Gate-shaped,
unannotated Jobs were used, with plain Pods standing in for the factory. The
record is on livespec-dev-tooling-cikd6m, 2026-11-04 02:25-02:31Z.

- A gate was HELD, with no pod, while both nodes lacked 5 free CPU, even though
  `gates-flavor` had 10 CPU of unused quota.
- A gate SPILLED to the hp stand-in while the gmktec stand-in was full.
- A held gate was admitted on gmktec once it freed.
- An in-place apply onto the pre-TAS flavors, with an admitted gate present,
  was accepted, and the gate kept running.

**Revert recipe. `topologyName` is IMMUTABLE once set.** An in-place apply of
a manifest without it is refused: `topologyName is immutable when
topologyName is set`. Rehearsed on the throwaway cluster:

1. Wait for a window with NO admitted gate Workloads. Check that
   `kubectl get clusterqueue gates-cq -o jsonpath='{.status.admittedWorkloads}'`
   reads 0. Queued, unadmitted gates are fine: they requeue against the
   recreated queue.
2. `kubectl delete clusterqueue gates-cq`, then
   `kubectl delete resourceflavor gates-flavor gates-hp-flavor`, then
   `kubectl delete topology gates-hostname`.
3. Revert this commit in git and converge as usual. Step 5 of
   `../reconstruct/converge-ci-stack.sh` re-applies the pre-TAS file. On the
   throwaway cluster the queue was Active again in about 6 s, and a gate
   admitted.

Steps 1-2 are deletions of live objects. Run them only as part of that
reverted converge, through the committed apply path, never as a standalone
hand edit.

## Recomputing at another C

The derivation is parameterized so a capacity change is mechanical:

1. Read the new capacity `C`. Since "The derivation at C = 44 — the two-node
   pool (2026-09-11)" the pool is multi-node and churn-slot capacity is
   PER-NODE, so `C` is the SUM of every pool node's `ADMISSION_CAPACITY_C`
   (its own profile's value, which is what
   `../node-extended-resource/patch-node-churn-capacity.sh` stamps on that one
   node) — today poweredge 32 + gmktec 12 = 44. On a single-node pool this is
   just that node's capacity, which is why every table before C = 44 reads `C`
   as one number.
2. Recompute the table above with the same `w_i` — they do not change
   with capacity; they are a demand profile, not a capacity split.
3. Rewrite each `cluster-queue-<repo>.yaml`'s `nominalQuota` and verify the ten
   values sum to exactly `C` — the CLUSTER-WIDE cohort quota, which equals the
   TOTAL across nodes, not any single node's per-node capacity.
4. Rewrite each `../arc/values-<repo>.yaml`'s `maxRunners` to
   `max(2 x nominalQuota, 6)` (see "
Bounding maxRunners to the quota (2026-09-06)"), so the ceilings track the quotas.
5. Apply, and confirm `kubectl get clusterqueue` reports the new sum and
   `kubectl get autoscalingrunnerset -n arc-runners` the new ceilings.

Order matters when raising capacity: patch the node capacity FIRST, then
the quotas. Raising node capacity alone is a no-op, because cohort
borrowing is bounded by the summed nominal quota rather than by node
capacity. Lowering runs the other way — lower the quotas first, then the
node capacity, so the cohort never has quota outstanding against
capacity that no longer exists.

## What this derivation does NOT address: queueing that is not capacity

**Jobs sitting queued is not, by itself, evidence that `C` is too low.** There
is a distinct failure mode that presents identically and that no quota value
can fix — `livespec-s43svm.30`, root-caused live on 2026-08-19.

A runner pod can be `Running` and `ready=true` to Kubernetes while permanently
unable to accept work, because GitHub invalidated its registration
server-side. It never exits; its log loops `Registration <uuid> was not
found`. ARC counts it as a live runner, computes `decision=1` against
`currentRunnerCount=1`, and therefore suppresses the very scale-up that would
replace it. A dead runner holds the slot that would have fixed it.

Every signal in this document reads healthy through that state: pods
`Running`, node capacity showing headroom, Kueue reporting zero gated and zero
pending workloads, quotas summing correctly to `C`. Two separate sessions
diagnosed it as runner-pool saturation before it was root-caused. Raising `C`
does not clear it — the 8 to 16 raise on the night of 2026-08-19 did not, and
the full 482-slot envelope would not either.

So before reading queueing as a capacity signal, check for that signature.
Sizing and wedging are different problems with opposite fixes, and this file
only speaks to the first. `livespec-s43svm.30` owns the detection and recovery
work; nothing in it changes any number here.

## The permanent C is still an open question

**Nothing in this derivation chooses `C`.** The formula apportions
whatever capacity it is given; picking the capacity is a HOST CAPACITY
decision, made by a maintainer and journaled on the `livespec-s43svm`
epic, not something the arithmetic can decide.

What is known, as of 2026-08-19:

- **`C = 8` proven.** Ran as the fleet's configuration through a soak
  with no capacity-related symptoms.
- **`C = 16` proven.** A 45-minute soak over 22 samples against a real
  16-to-88-pod backlog from all eight repositories: the cap was never
  breached, zero container-init hangs, iowait oscillated 0-20% and
  crested only during container-start waves, load reached 48 of 72
  cores. Journaled on `livespec-s43svm.15`, 2026-08-19.
- **`C = 64` set 2026-08-30, NOT soak-proven.** The increase-ci-runners
  raise (livespec epic `livespec-zec4mz`) set `C = 64` DELIBERATELY AHEAD OF
  DATA, to relieve fleet CI starvation now and to force the disk-throughput
  measurement `livespec-g52yrb` lacks. Unlike 8 and 16, it has had no soak:
  its safety is a hypothesis the raise is built to TEST, not an established
  fact. It MUST be instrumented under real load (`iostat -x 5` %util/await on
  the CI-backing device, recorded onto `livespec-g52yrb`), with a rollback
  ladder (step down to 32, then 24, recording the number at which
  disk-pressure symptoms appear — that number is this disk's pre-RAID-10
  churn ceiling).
- **`C = 482` is the design-envelope steady-state target**, inherited
  from the podman pool's measured physical ceiling and recorded in
  `patch-node-churn-capacity.sh`'s own header. It is a target, not a
  proven value — nothing has run the k3s pool anywhere near it.

Be precise about what "proven" means for those two values. The soaks
establish the SAFETY of running at that capacity: the cap was never
breached, and no iowait or container-init symptom appeared. They do NOT
establish that the queueing observed before each raise was
capacity-bound, and in light of `livespec-s43svm.30` (above) some of it
demonstrably was not. Raising `C` was safe and it increased throughput;
that is not the same as it having been the fix for every stall attributed
to it at the time.

- **`C = 64` on the TIERED host, first read 2026-09-06 (livespec epic
  `livespec-g52yrb`, child `livespec-e2vcqf`).** With both write-hot tiers on
  dedicated NVMe drives the storage ceiling that forced the 2026-09-02 interim
  is gone and a NEW ceiling is visible: **CPU**. Measured in the first hour at
  C = 64: at 33 runners `mpstat` read 84 % busy (60 % user, 24 % system),
  idle floor 6–8 % in 5-second windows, 1-minute load 96 with 134 runnable
  threads on 72; the maintainer observed a load peak near 120. Storage under
  the same bursts: `ci-workvols` NVMe 38k writes/s at 1.2 ms `w_await`
  (66 % util), containerd NVMe 10.6 ms at queue depth 18 (7 % util), the
  array idle, iowait 0.05 %, 0 `Slow SQL`. The compute is the jobs' own
  compilers (`rustc`, `cc1`, `clippy`) plus `k3s-server` at ~1.2 cores
  (1.7 % of the box, spread over ~20 threads — no hot spot). The runner-pod
  lifecycle scan fired its `pvc-pending` class at the 51-runner burst (work
  PVCs pending 165–182 s; the provisioner's helper pods compete for the same
  saturated CPU) and cleared. Nothing failed. Three consequences:
  1. **96 is OUT**, not deferred: there is no CPU for it, and it would also
     breach the pod-capacity constraint at `max-pods = 200`.
  2. **The cap is throughput-derived, not utilization-derived** (maintainer
     principle, 2026-09-06). Running more runners than cores is correct while
     jobs have non-CPU phases (clone, fetch, container start); CPU-bound
     phases are zero-sum, so past saturation each extra runner lengthens every
     job without adding throughput and risks timeouts. The number to watch
     is p95 job duration against concurrency and control-plane
     responsiveness, never "% busy". 64 sits in the oversubscribed-but-flowing
     regime; the soak decides whether it stays.
  3. **The control plane needs no CPU-priority change.** `k3s.service` has
     no `CPUWeight`, `Nice 0`, no quota — but at the cgroup root the pod slice
     and `system.slice` are peers at weight 100, so under contention the host
     side is entitled to half the machine and k3s wants 1.7 %. Load 96
     produced 0 `Slow SQL` and no lease trouble. CFS weights and
     `--kube-reserved` are shares that never idle a core (only a cpuset pin
     would, and none is proposed); runner pods request no CPU, so reserved
     CPU would change nothing about scheduling either. `metrics-server` is
     NOT an observability dependency (Honeycomb reads `kubeletstats` and
     `k8s_cluster` directly) but stays, its cost being a rounding error.
  The lever that remains is not more cores: it is cache hit rate — `sccache`
  for the Rust/C compile CPU, the warm `uv` cache for Python — which turns
  repeated compute into reads; the host's ~143 GiB of free memory is useful
  for exactly that, and for nothing else on the CPU side.

So the answer is bracketed between 16 (soak-proven safe) and 482 (targeted),
with a large interval between — and as of 2026-09-06 the live value is back
at **64 on the tiered host**, where its first hour showed the ceiling is now
CPU rather than storage (see the tiered-host `C = 64` entry above), so 482 is
a podman-era number this node's cores cannot reach. The podman pool has been stopped
since 2026-08-13, so the side-by-side joint-budget constraint that
`README.md` documents no longer binds; the remaining reason for caution
is simply that the k3s container-churn profile at high concurrency has
not been measured — which the C = 64 raise now exists to measure. Probing
further upward is a capacity decision for the epic.

## Is a generator worth building?

**No — decided here, and this discharges `../VALIDATION_CHECKLIST.md`
item 6.**

The fleet has eight repositories and one capacity number. With the
derivation parameterized as above, regenerating every quota is a table
recomputation and eight one-line edits, done a handful of times in the
whole life of this pool. A generator script would add a source file, a
test, a place for the committed manifests and the generator's output to
disagree, and a second thing to keep working — against a manual step
that takes minutes and is verified by adding eight integers.

This is the fleet's standing "prefer conventions over new artifacts"
answer, applied: a documented derivation plus committed files IS the
mechanism. Reconsider if either input changes character — many more
repositories, or a `C` that changes often enough that hand-editing
becomes a recurring chore rather than an occasional one.

One narrower piece of tooling WOULD be earned before a full generator:
a check that the committed `nominalQuota` values sum to the capacity
`patch-node-churn-capacity.sh` last applied. That is the one invariant a
human can silently break, and it is a summation, not a code generator.
It is not built here — it needs a committed home for the current `C`,
which the provisioning scripts do not have yet.

## Observation: ARC `maxRunners` still carries the podman-era numbers

Read-only observation from the live cluster, 2026-08-19. Every scale
set's `maxRunners` is that repository's podman-era apportionment value
`w_i` (63 through 67, with `livespec-console-beads-fabro` at 16), except
`livespec-local-ci-k3s`, which is 36.

Two things follow, neither of them changed by this pass:

**The values are the demand weights, not doubled logical ceilings.** Per
the formula, `maxRunners` should be the repository's own matrix width
doubled — a property of the repository's workflows. Nobody has measured
those widths; `w_i` was inherited as a proxy. This is harmless today
because at `C = 16` no repository can reach even a tenth of its
`maxRunners`, so the term never binds. It becomes real only if `C` rises
far enough for a repository to actually hit 63-67 concurrent runners.
Re-deriving `maxRunners` from measured matrix widths is follow-up work
for whoever raises `C` substantially, not work this item can do without
measurements that do not exist.

**`livespec-local-ci-k3s`'s 36 is inconsistent with even that proxy.**
It comes from the stale `--slots 18` reading the 2026-08-16 `README.md`
correction already identified as wrong; the live apportionment for
`livespec` is 75. It is left unchanged deliberately: correcting it means
a Helm upgrade that restarts the busiest repository's listener, for a
value that cannot bind at `C = 16`, during a window when fleet CI
throughput is the active concern. It should be corrected alongside the
`maxRunners` re-derivation above, when a capacity raise makes it
matter.

Neither observation blocks this derivation: `nominalQuota_i <=
maxRunners_i` holds comfortably for all eight repositories at every
capacity considered here.

**Resolved 2026-09-06, the other way round.** The re-derivation this
observation deferred never happened as a matrix-width measurement; instead
the first fleet-wide backlog on the tiered host showed that a `maxRunners`
far above the quota is itself the defect (122 gated runner objects, 11 Slow
SQL in ten minutes at C = 32), and every scale set was BOUNDED to
`max(2 x nominalQuota, 6)`. See "
Bounding maxRunners to the quota (2026-09-06)". The podman-era numbers are gone from every values file.

## Rebalance within 36: gmktec 8, poweredge 23 (2026-11-08)

Step 3 of livespec-dev-tooling-6e5pyj. ci-runtime-and-cost made this fairness call on 2026-11-08 at 02:0xZ, and the coordinator authorized it under R301.

Thirty minutes after step 2, the load had moved rather than eased. Each node was read by idle %, the BestEffort CI slice's cpu.pressure and the usage_usec split, not by host PSI alone:

| Node | Idle | CI slice pressure (avg60) | CPU split | Reading |
| --- | --- | --- | --- | --- |
| poweredge-xubuntu | 0.3 % | 32.1 | BestEffort CI 42, Burstable factory 27, system 2, on 72 cores | SATURATED by the 2026-11-04 rule (idle under 5 and CI pressure over 30) |
| gmktec-xubuntu | 48.7 % | 1.8 | CI 4, factory 11, on 32 cores | about 15 cores free |

Four churn slots move from poweredge to gmktec, and the total stays the same: poweredge 27 -> 23, gmktec 4 -> 8, hp 5, total 36.

- Because the total is unchanged, no ClusterQueue quota and no `maxRunners` value changes, and the quota sum still balances.
- CI measured about 1.6 CPU per slot on poweredge (42 / 27), so the move takes about 6 CPUs off poweredge and puts about 6 onto gmktec's free cores.

Risk: at its 21:4xZ peak, gmktec's factory used 20 Burstable CPUs, and 8 slots would put gmktec near 32. Because CI is BestEffort, it slows there rather than starving the factory.

Step-back: read both nodes about 30 minutes after the apply, and again under a factory peak. If gmktec reads saturated by the same rule, go to gmktec 6 and poweredge 25.

Revert: gmktec 4 and poweredge 27, with a node_extended_resource apply.

Still open under 6e5pyj: deriving poweredge's real CI budget, about 43 CPUs or about 17 slots, which would lower the total.

## poweredge to its CI budget: 17 slots, cohort 30 (2026-11-08)

Step 4 of livespec-dev-tooling-6e5pyj. ci-runtime-and-cost made this call on 2026-11-08 at about 05:4xZ, applying the decision rule it set before the read.

The 05:33Z split read on poweredge-xubuntu was taken with 22 of 23 churn slots in use, 14 churn pods pending, and the factory at 17 of its cap of 18:

- idle was 0.16 % over 10 s
- the CI (BestEffort) slice's cpu.pressure avg60 was 37.1
- the factory (Burstable) slice's avg60 was 2.4
- CPU use was CI 29.8, factory 39.4 and system 2.6 CPUs, on 72 cores
- the factory pods were throttled in only 2.7-5.3 % of periods

That is real CI saturation (idle under 5 and CI pressure over 30), not sandbox throttle stall. So poweredge moves to its derived CI budget of about 43 CPUs, about 17 slots: 23 -> 17. The 6 freed slots leave the cohort, which drops from 36 to 30. They are NOT shifted to gmktec (8, 4 % idle at 02:56Z) or hp (5).

Quota split, summing to 30:

| Queue | Change | maxRunners |
| --- | --- | --- |
| livespec-orchestrator-beads-fabro-cq | 17 -> 12 | max(2 x 12, 6) = 24 |
| livespec-cq | 2 -> 1 | max(2, 6) = 6, unchanged |

- **Kept unchanged:**
  - livespec-dev-tooling-cq stays at 6, because it already shows the queue-wait cost.
  - livespec-dev-tooling-master-cq stays at 3, because it is the reserved, non-lendable master lane.
  - The 1-slot queues stay at 1, because they cannot go lower.
- **The two cuts:**
  - livespec's jobs are short (7-day max 13 min), so 1 slot serves it.
  - The orchestrator is the largest consumer, and 12 keeps it about twice dev-tooling.

IT IS A 60-MINUTE THROUGHPUT TRIAL, not a pressure fix. A coordinator ruling (ci-node-capacity-reads.md, "Utilization is not the target; throughput is") holds that host PSI is never a cap trigger by itself.

- **Trial window:** from apply-complete (the moment poweredge's allocatable churn-slot reads 17) to 60 minutes after it.
- **Baseline:** the 60 minutes before the apply, at 23 slots.
- **What ci-runtime-and-cost measures**, from GitHub job records:
  - k3s-routed jobs completed per hour, per queue and fleet-wide
  - p95 job duration, per queue and fleet-wide
  - the orchestrator coverage median
  - dev-tooling queue wait

At +60 minutes it rules KEEP or REVERT. A node read at about +45 minutes (idle %, CI-slice avg60, host PSI) is context only and does not decide the trial.

If 6e5pyj's host assertion 1 cannot hold at the throughput-optimal cap, the remedy is a Definition-of-Done amendment, not a lower cap.

Kill switch: restore poweredge 23, orchestrator-cq 17, livespec-cq 2 and maxRunners 34 (the step-3 values), applying node_extended_resource and ci_converge_unit together.

## Orchestrator to 9, dev-tooling to 9, within 30 (2026-11-08)

The step-4 trial above closed with a KEEP at 17/30/12/1. ci-runtime-and-cost ruled it on 2026-11-08 at 07:00:56Z, and the numbers are on livespec-dev-tooling-6e5pyj. Fleet completions fell 170 -> 123, but jobs created fell with them, so that was a demand drop. On the queues holding waiting work, completions rose 112 -> 123. Fleet p95 fell 47.7 -> 46.3 minutes, and the orchestrator's fell 53.0 -> 48.8. At window end only livespec-dev-tooling held waiting jobs.

legacy-coordinator-agent then ruled (R301) to move 3 slots from the orchestrator to dev-tooling, keeping the cohort at 30. dev-tooling CI is what the next incident-response arm waits on.

| Queue | Change | maxRunners |
| --- | --- | --- |
| livespec-orchestrator-beads-fabro-cq | 12 -> 9 | max(2 x 9, 6) = 18 |
| livespec-dev-tooling-cq | 6 -> 9 | max(2 x 9, 6) = 18 |

Every other queue and every node profile is unchanged. The quotas still sum to 30, equal to poweredge 17 + gmktec 8 + hp 5.

ci-runtime-and-cost re-measures 60 minutes after the apply, from the apply time this change's applier reports. Kill switch: restore orchestrator-cq 12 with maxRunners 24, and dev-tooling-cq 6 with maxRunners 12, by applying ci_converge_unit.

## hp to 3 slots, cohort 28 (2026-11-09)

This is the refined hp trigger on livespec-dev-tooling-6e5pyj. ci-runtime-and-cost applied it on 2026-11-09 after the gate-lane reorder. The rule was set before the read: cut hp-xubuntu 5 -> 3 only if hp's job times have NOT fallen against the pre-reorder read AND hp still runs above 3.1x gmktec.

The gate lane put hp LAST at 12:44:41Z (gmktec 15, poweredge 10, hp 10). Nodes were mapped from the arc-runners `Scheduled` events and joined to the GitHub job records of livespec-dev-tooling CI runs created after 12:45Z.

| Job | hp before the reorder | hp after the reorder | gmktec after the reorder | hp / gmktec |
| --- | --- | --- | --- | --- |
| check-types | 54 s | 207 s (run 42620973747, job 129172710717) | 37 s (run 42622915919) | 5.6x |
| check-lint | 105 s and 23 s | 62 s (run 42620973747, job 129172710807) | 15 s (run 42622915919) | 4.1x |

hp's times did not fall: check-types rose and check-lint stayed flat. Both ratios are above 3.1x. At 13:37Z, hp ran only 2 runner pods, with 0 factory and 0 gate pods, and was still about 69 % busy (/proc/stat over 5 s). Those 2 pods ran about 8 pytest workers on its 16 CPUs, so even its pod-quiet state is loaded.

| Item | Change |
| --- | --- |
| hp-xubuntu `ADMISSION_CAPACITY_C` | 5 -> 3 |
| Cohort | 30 -> 28 (poweredge 17 + gmktec 8 + hp 3) |
| livespec-dev-tooling-cq | 9 -> 7; maxRunners max(2 x 7, 6) = 14 |

Every other queue is unchanged, so the quotas still sum to the node profiles. dev-tooling-cq donates the 2 slots because it took 3 on 2026-11-08 and remains the largest of the small queues. The master lane (livespec-dev-tooling-master-cq, 3) is untouched.

Apply: `just ansible-apply ansible/ci-pool.yml --tags node_extended_resource`, then the ci_converge_unit apply for the queue and maxRunners.

Revert: hp 5, dev-tooling-cq 9 and maxRunners 18, applied the same way.

Re-read hp and dev-tooling queue wait 60 minutes after apply-complete. That is the moment hp's allocatable churn-slot reads 3.
