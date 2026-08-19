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
registered on the node. It is `16` as of 2026-08-19.

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
- **`C = 482` is the design-envelope steady-state target**, inherited
  from the podman pool's measured physical ceiling and recorded in
  `patch-node-churn-capacity.sh`'s own header. It is a target, not a
  proven value — nothing has run the k3s pool anywhere near it.

So the answer is bracketed between 16 (proven) and 482 (targeted), with
a large untested interval between. The podman pool has been stopped
since 2026-08-13, so the side-by-side joint-budget constraint that
`README.md` documents no longer binds; the remaining reason for caution
is simply that the k3s container-churn profile at high concurrency has
not been measured. Probing upward is a capacity decision for the epic.

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
