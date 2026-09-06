# Deriving the per-repository Kueue quotas from the admission formula

This file is `livespec-s43svm.15`'s deliverable: it maps the fleet's
EXISTING, UNCHANGED admission/fair-share formula onto the ARC and Kueue
mechanisms, and shows the arithmetic that produces the committed
`cluster-queue-<repo>.yaml` files beside it. The formula itself is not
redesigned here — its authority is
`SPECIFICATION/non-functional-requirements.md` section "Adaptive JIT
runner admission budget", and the sentence being modeled is:

> Each repository's logical ceiling MUST be doubled to support two
> concurrent matrix pipelines. The physical host-wide cap remains
> exactly 482 active runners; no configuration or recovery path may
> derive or admit 964 runners. Repositories MAY fairly borrow unused
> capacity, and the desired admission for each repository MUST be
> `min(queued jobs, doubled repository logical ceiling, fair share of
> remaining host-wide capacity)`.

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
| `doubled repository logical ceiling` | ARC `AutoscalingRunnerSet.maxRunners` | `../arc/values-<repo>.yaml` |
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
own, independently of Kueue. It answers "how many runner pods would this
repository ever want at once", which is a property of the REPOSITORY's
workflows (its matrix width, doubled for two concurrent pipelines) —
not a property of the host.

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

## Inputs

**The demand weights `w_i`.** The podman-era `ci-runner-supervisor`
apportioned the full 482-slot physical budget across the fleet by
observed demand. Those values, read from the live host
(`systemctl cat ci-runner-supervisor`, 2026-08-16, and journaled on
`livespec-s43svm.15`), are this derivation's demand weights:

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
were: an apportionment OF that cap. Note carefully what they are and are
not — `w_i` is a measured DEMAND WEIGHT, not the repository's logical
ceiling. The two were conflated in a 2026-08-16 note on `README.md`; the
distinction matters because the logical ceiling feeds `maxRunners` while
the demand weight feeds `nominalQuota`.

**The capacity `C`.** The `ci-runner.io/churn-slot` capacity currently
registered on the node. It is `64` — first set 2026-08-30 by the
increase-ci-runners raise (livespec epic livespec-zec4mz), lowered to the
INTERIM `32` on 2026-09-02 while the RAID's data plane was the ceiling, and
RESTORED to `64` on 2026-09-06 once both NVMe drives carried the churn; see
"The derivation at C = 64 restored (2026-09-06)" below. It was `16` from
2026-08-19 until the first raise.

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
repository below 1. This did not trigger at `C = 16` or at `C = 8`; it
begins to matter as `C` approaches the repository count, and is written
down here so the case is decided rather than improvised.

**The invariant to check after any recomputation:** the quotas sum to
exactly `C`, the registered node capacity. Nothing enforces this
mechanically — see "Is a generator worth building?" below.

**The invariant has ONE known exception, and it is forced by step 5.**
The `max(1, ...)` floor can lift a repository whose apportionment rounds
to zero, which adds a unit the apportionment did not allocate. That
cannot happen while every repository's exact share exceeds 1, so it did
not arise at eight repositories, and it DOES arise at nine — see
"Recomputation on the ninth repository (2026-08-20)" below. When it
fires, the raw apportionment still sums to exactly `C` and the committed
quotas sum to `C + k`, where `k` is the number of floored-up
repositories. Do not restore the sum by re-quoting some other repository
below its apportioned share; that trades a harmless one-unit
over-reservation for a real, silent under-allocation of a repo that
earned its slots.

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

**This is where the sum invariant breaks, and the break is the rule's,
not a maintainer's.** Step 5's `max(1, ...)` floor lifts
`livespec-driver-pi` from 0 to 1, so the raw apportionment sums to
exactly `C = 16` while the COMMITTED quotas sum to **17**. Kueue then
holds one slot of nominal quota against capacity the node does not have.
That is harmless in operation — the scheduler is the final gate, and the
excess is one slot out of sixteen — but it makes the invariant as
originally written false, which is why it is documented here rather than
silently absorbed.

**The open decision, which this section does not make.** Two clean
resolutions exist, and both are fleet-level calls rather than something
to settle while provisioning one repo:

1. Raise `C` to 17 and recompute, so the registered capacity matches the
   committed quotas. This needs the same iowait-headroom justification
   any capacity change needs; `C` is a measured ceiling, not a free
   parameter. See "The permanent C is still an open question" below.
2. Keep `C = 16` and record a standing exception: the committed sum is
   `C + k` where `k` counts floored-up repositories. This costs nothing
   operationally and keeps the capacity number honest.

Until one is chosen, the committed state is option 2 by default, with
`k = 1`. What must NOT happen is a maintainer noticing the 17 and
"fixing" it by cutting some other repository to restore 16 — that would
convert a harmless over-reservation into a real under-allocation.

**Note for the next repository.** A tenth repo makes this worse rather
than better: at `C = 16` the mid-band repos are already at their floor
of 2, so each new small repo arrives with a sub-1 share, is floored up
to 1, and adds another unit to the excess. The `max(1, ...)` collision
is therefore a growth property of the rule at low `C`, not a one-off.

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
node-local install mechanism — `../node-inotify-budget/install-inotify-sysctl.sh`
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
wait. `maxRunners` is unchanged — it is each repository's logical ceiling, not
the quota. The pod-capacity constraint is comfortably met: `2 x 32 + helpers +
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

## Recomputing at another C

The derivation is parameterized so a capacity change is mechanical:

1. Read the new capacity `C` (whatever
   `../node-extended-resource/patch-node-churn-capacity.sh` was given).
2. Recompute the table above with the same `w_i` — they do not change
   with capacity; they are a demand profile, not a capacity split.
3. Rewrite each `cluster-queue-<repo>.yaml`'s `nominalQuota` and verify
   the eight values sum to exactly `C`.
4. Apply, and confirm `kubectl get clusterqueue` reports the new sum.

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

So the answer is bracketed between 16 (soak-proven safe) and 482 (targeted),
with a large interval between — and as of 2026-08-30 the live value sits at
**64, un-soaked**, placed inside that interval on purpose to probe it under
real load (see the `C = 64` entry above). The podman pool has been stopped
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
