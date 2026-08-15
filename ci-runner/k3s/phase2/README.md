# k3s + ARC + Kueue — phase 2 (model the fair-share formula)

Design artifacts — NOT yet applied to any live cluster — mapping this
epic's existing, UNCHANGED admission/fair-share formula onto Kueue and
ARC primitives. Phase 2 of 6 in the migration (`../README.md` "Files"
table has the full six-phase list); depends on phase 1
(`livespec-s43svm.14`, PR
[#1419](https://github.com/thewoolleyman/livespec-dev-tooling/pull/1419),
merged) for the k3s + ARC + Kueue install this phase's manifests target.

**Scope of this pass (`livespec-s43svm.15`): design only, not
validation.** Everything under this directory is drafted and reasoned
about against the pinned versions (k3s v1.36.2+k3s1, ARC charts 0.14.2,
Kueue v0.19.1) and public documentation, but NONE of it has been
applied to `poweredge-xubuntu` or any live cluster by this work — `.14`'s
remaining live-host install steps are a separate, actively-owned track,
and this design pass does not touch that host. See
`VALIDATION_CHECKLIST.md` for exactly what must be run, and by whom,
once a live cluster exists to run it against.

## The formula, unchanged

`livespec-dev-tooling` `SPECIFICATION/non-functional-requirements.md`
section "Adaptive JIT runner admission budget":

> Desired admission for each repository MUST be `min(queued jobs,
> doubled repository logical ceiling, fair share of remaining
> host-wide capacity)`.

Per the migration decision record (livespec repo
`plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md`), this
formula is NOT being redesigned — it is being RE-HOMED from
hand-rolled bash-supervisor logic onto Kueue's Cohort/Fair-Sharing
admission controller and ARC's per-repo AutoscalingRunnerSets, which
already implement close to this exact shape as a matured, community-
maintained reconciliation loop.

## Three clauses, three enforcement points

| Formula clause | Kubernetes primitive | Where it's enforced | Files |
|---|---|---|---|
| `queued jobs` | ARC's per-repo scale-set listener | ARC's own controller, reading GitHub's actual queued-job count for that repo/scale-set — no design change needed, this is ARC's native behavior | `arc/values-*.yaml` |
| `doubled repository logical ceiling` | ARC `AutoscalingRunnerSet.maxRunners` | ARC's controller — will never scale a given repo's runner pods past this cap regardless of what Kueue would otherwise admit | `arc/values-*.yaml` (`maxRunners`) |
| `fair share of remaining host-wide capacity` | Kueue Cohort + `ClusterQueue.spec.cohort` + Fair Sharing | Kueue's admission controller — orders and bounds admission across every repo's ClusterQueue sharing one cohort | `kueue/cluster-queue-*.yaml`, `kueue/enable-fair-sharing.sh` |

## Two enforcement points, one number

Each repository's doubled logical ceiling appears TWICE — once as
`arc/values-<repo>.yaml`'s `maxRunners`, once as
`kueue/cluster-queue-<repo>.yaml`'s `nominalQuota`. This is deliberate,
not duplication-by-oversight: ARC's `maxRunners` is a HARD ceiling
independent of Kueue (belt), while Kueue's `nominalQuota` is what makes
that capacity fairly SHARED with other repos rather than exclusively
reserved (suspenders). Either one alone is insufficient: `maxRunners`
alone gives every repo an exclusive, non-borrowable slice (no fair
sharing); `nominalQuota` alone lets Kueue admit workloads that ARC's
own scale-set would then refuse to scale into pods, since Kueue
admission and ARC scaling are two independently-configured
controllers.

A generator/lockstep-check that derives one from the other and fails
if they drift is real follow-up work, but is deliberately NOT built in
this design pass (see `VALIDATION_CHECKLIST.md` item 6) — the fleet is
small enough (roughly ten repositories) that hand-authoring both files
per repo, as `arc/values-livespec.yaml` and
`kueue/cluster-queue-livespec.yaml` demonstrate, is tractable without
new tooling, and a generator built before the manifest SHAPE is proven
against a live cluster risks encoding a shape that has to be redone.

## Why per-repo quotas summing above 482 is safe

`kueue/cluster-queue-livespec.yaml`'s `nominalQuota: 36` is livespec's
OWN doubled ceiling. If every fleet repository's doubled ceiling were
summed, the total would likely exceed 482 (that's the whole point of
"doubled" — headroom for two concurrent matrix pipelines PER repo, not
a promise that all repos hit that ceiling simultaneously). This does
NOT risk implying 964 total runners, because Kueue's `nominalQuota` is
a LOGICAL bookkeeping ceiling per ClusterQueue, while the
`ci-runner.io/churn-slot` extended resource
(`node-extended-resource/`) is registered on the actual node with a
FIXED, finite capacity. A Kueue-admitted workload still needs a
schedulable pod, and a pod requesting `ci-runner.io/churn-slot: "1"`
can only run while the node has an unclaimed unit of that resource —
so no matter how high the SUM of nominal quotas across the cohort
climbs, the number of runner pods that can be simultaneously `Running`
is hard-capped by the extended resource's node capacity. This is
exactly the "physical cap remains exactly 482... no design may imply
or admit 964" invariant, enforced at the scheduler layer rather than
by the admission-formula's own arithmetic.

## The iowait/container-churn bottleneck as an extended resource

Per the migration decision record's own honest caveat: the fleet's
measured bottleneck (`livespec-s43svm.11`'s evidence — 65-89% iowait on
the 72-core host during a contended run) is disk I/O from concurrent
container churn, not CPU or memory, and Kubernetes' default scheduler
bin-packs on CPU/memory requests only. `kueue/resource-flavor.yaml` and
every `arc/values-*.yaml`'s pod `resources.requests`/`limits` key
Kueue's and the scheduler's admission math on `ci-runner.io/churn-slot`
instead — a synthetic, COUNTING extended resource
(`node-extended-resource/patch-node-churn-capacity.sh`) whose node
capacity models "how many concurrently-churning runner pods this host
can absorb without iowait-induced slowdown," not raw CPU/memory
headroom. This is the concrete answer to the migration decision
record's "would need to be modeled deliberately" caveat.

## Why per-repo quotas summing above 482 must NOT be set to 482 during side-by-side migration

The steady-state target capacity for `ci-runner.io/churn-slot` is 482 —
but ONLY once the podman pool is fully retired
(`livespec-s43svm.19`). During phases 1-4 (`.14`-`.17`), the SAME
physical host runs BOTH pools concurrently, sharing the SAME iowait
budget the 482 figure describes. Setting the k3s pool's node capacity
to a flat 482 while the podman pool is also running near its own ~482
concurrent `runner@` units would let the two pools JOINTLY imply
something close to the 964 the specification explicitly prohibits —
even though neither pool's own configuration exceeds 482 in isolation.
`patch-node-churn-capacity.sh` therefore takes capacity as a REQUIRED
argument rather than hardcoding either number, and this is flagged as
an explicit joint-budget coordination requirement for whoever drives
the incremental cutover (`livespec-s43svm.16`) — see
`VALIDATION_CHECKLIST.md` item 4. This design pass does not pick a
provisional side-by-side number itself: that is a live-host capacity
decision, not a design-time one, and making it here would be guessing
at data (current live podman pool headroom) this pass has no
authorization to go measure by touching the host.

## Fair Sharing, and what it changes

Kueue supports basic cohort quota-borrowing (one ClusterQueue using
another's unused `nominalQuota`) without any extra configuration once
two ClusterQueues share a `spec.cohort` value — this alone would
satisfy "repositories MAY fairly borrow unused shared capacity" in a
weak sense. `kueue/enable-fair-sharing.sh` turns on the stronger
property: when MULTIPLE repos have pending (queued-but-not-yet-
admitted) demand competing for the same borrowed capacity, Fair Sharing
orders admission by each ClusterQueue's `fairSharing.weight` relative
to its recent borrowed usage, rather than plain FIFO-by-arrival. Every
`cluster-queue-*.yaml` in this design sets `fairSharing.weight: 1` —
equal weight for every repo — because the specification states no
per-repo priority differentiation; a future change to weight some
repos higher would be a one-line edit per `ClusterQueue`, not a
redesign.

Kueue v0.19.1 also ships a first-class `Cohort` CRD
(`kueue.x-k8s.io/v1alpha1`) for hierarchical/nested cohorts with their
own resource groups. This design deliberately uses the simpler
string-typed `ClusterQueue.spec.cohort` field instead: the fleet's
cohort is flat (one level, N repo ClusterQueues, no sub-cohorts), so
the `Cohort` CRD's extra structure would not be earning its complexity
yet. Confirm this field is still valid and behaves as documented
against the pinned v0.19.1 CRDs once a live cluster exists —
`VALIDATION_CHECKLIST.md` item 1.

## What does NOT move to Kueue/ARC: the GitHub REST point budget and circuit breaker

The formula's OTHER half — installation-wide REST point budget
accounting, the 450-point startup burst, and the shared 403/429/
Retry-After circuit breaker (same spec section, same
`livespec-s43svm.5`) — governs calls to GitHub's REST API when MINTING
runner registrations, which is a concern about ARC's OWN controller's
GitHub API usage, not something Kueue (a purely Kubernetes-internal
scheduler) has any visibility into.

**Source-read finding (2026-08-15, no live cluster needed — see
`VALIDATION_CHECKLIST.md` item 2 for the full trace): this is a real,
confirmed gap, not redundant with what ARC ships.** ARC's
[`actions/scaleset`](https://github.com/actions/scaleset) client wraps
`hashicorp/go-retryablehttp` for its registration-token and JIT-config
minting calls, retrying `429`/`5xx` but explicitly NOT a bare `403` —
the one custom `401`/`403`-retry override in that library is scoped to
a different call (the tenant-URL/JWT exchange), not either minting
call. The controller-runtime reconcile loop's own generic workqueue
rate limiter eventually retries a failed reconcile, but it is not
GitHub-response-aware (no `Retry-After` honoring, no distinction
between a genuine secondary-rate-limit `403` and a permanent error).
**STILL OPEN:** whether this gap manifests in practice (vs. staying
theoretical because GitHub simply never returns a bare `403` to this
fleet's actual call volume) needs a live-cluster observation —
`VALIDATION_CHECKLIST.md` item 2's remaining leg.

## Files

| Path | Role |
|---|---|
| `kueue/resource-flavor.yaml` | The one `ResourceFlavor` every per-repo `ClusterQueue` requests from, keyed on the `ci-runner.io/churn-slot` extended resource. |
| `kueue/enable-fair-sharing.sh` | One-time, human-supervised step to turn on Kueue's cluster-wide Fair Sharing config (off by default; not something a ConfigMap can be safely auto-patched for — see the script's own header). |
| `kueue/cluster-queue-livespec.yaml` | Worked example: livespec's `ClusterQueue` (`nominalQuota: 36`, doubled from its measured 18 podman-pool slots) + `LocalQueue`. |
| `kueue/cluster-queue-EXAMPLE-repo.yaml` | Template for every other fleet repository — copy, fill in the placeholders. |
| `arc/values-livespec.yaml` | Worked example: livespec's per-repo `AutoscalingRunnerSet` Helm values (`maxRunners: 36`, `githubConfigUrl` narrowed to this one repo, pod template wired to `livespec-lq` via the `kueue.x-k8s.io/queue-name` label and requesting one `ci-runner.io/churn-slot`). |
| `arc/values-EXAMPLE-repo.yaml` | Template for every other fleet repository. |
| `node-extended-resource/patch-node-churn-capacity.sh` | Idempotently registers `ci-runner.io/churn-slot` as a node-status extended resource with an explicit, non-defaulted capacity argument. |
| `node-extended-resource/reapply-node-extended-resource.service` + `.timer` | Every-5-minute reconciliation reapplying that patch, because a node-status patch (not a device-plugin registration) does not survive a kubelet restart — see the caveat below. |
| `VALIDATION_CHECKLIST.md` | What to run, and confirm, once `.14`'s live cluster exists. Explicitly NOT run by this design pass. |

## Deriving a new repository's ClusterQueue

1. Read that repo's measured matrix width — its own
   `ci-runner-supervisor.service` `--slots` value if it is on the
   podman pool today (see `../../supervisor/README.md`), or its actual
   GitHub Actions matrix job count if not. Never guess.
2. Double it.
3. Copy `kueue/cluster-queue-EXAMPLE-repo.yaml` to
   `kueue/cluster-queue-<repo>.yaml`, filling in `<REPO>` and
   `<DOUBLED_CEILING>`.
4. Copy `arc/values-EXAMPLE-repo.yaml` to `arc/values-<repo>.yaml`,
   filling in `<REPO>` and `<DOUBLED_CEILING>` — the SAME number as
   step 3 (see "Two enforcement points, one number" above).
5. Apply both once `.16` (incremental per-repo cutover) reaches that
   repo — not before; this design pass ships zero real cutover.

## Known caveat: the node-status patch is not device-plugin-robust

`kubectl patch node --subresource=status` is the Kubernetes-documented
mechanism for a STATIC extended resource
(https://kubernetes.io/docs/tasks/administer-cluster/extended-resource-node/),
but kubelet does not own or persist arbitrary keys placed there the way
it does for a registered device plugin's resources — a kubelet restart
can reset `status.capacity` to only what kubelet itself computed,
silently dropping `ci-runner.io/churn-slot` until reapplied. The
`reapply-node-extended-resource.timer` (every 5 minutes) is the
pragmatic, homelab-single-node answer to this rather than building a
real device plugin, which would be the more robust choice for a
multi-node cluster this fleet does not have yet. If/when the fleet
grows to multiple k3s nodes (the migration decision record notes k3s
supports this via embedded etcd), reconsider this — a real device
plugin would then be earning its complexity.

## Nature

Like `../` (phase 1), these are host operational artifacts (YAML, Helm
values, shell) — not Python product code — so they are NOT part of the
`just check` aggregate. Recreatability is still the contract:
`node-extended-resource/patch-node-churn-capacity.sh` and
`kueue/enable-fair-sharing.sh` are idempotent and re-runnable, and every
manifest is declarative (`kubectl apply`-able repeatedly).
