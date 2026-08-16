# k3s + ARC + Kueue — phase 2 (model the fair-share formula)

Design artifacts mapping this epic's existing, UNCHANGED admission/
fair-share formula onto Kueue and ARC primitives, now partially
validated against the real live cluster. Phase 2 of 6 in the migration
(`../README.md` "Files" table has the full six-phase list); depends on
phase 1 (`livespec-s43svm.14`, PR
[#1419](https://github.com/thewoolleyman/livespec-dev-tooling/pull/1419),
closed 2026-08-16) for the k3s + ARC + Kueue install this phase's
manifests target.

**Validation status (`livespec-s43svm.15`), updated 2026-08-16:**
drafted as a design-only pass against pinned versions (k3s
v1.36.2+k3s1, ARC charts 0.14.2, Kueue v0.19.1) and public
documentation; once `.14` closed with a real, healthy live cluster,
`VALIDATION_CHECKLIST.md` items 1, 3, 5, and 7 were run for real
against `poweredge-xubuntu` and are CONFIRMED — two assumptions from
the original design-only pass turned out to be wrong (the Kueue API
field name/version, and the node-status patch's kubelet-restart
survival) and are corrected throughout this document. Items 2, 4, and
6 remain open; see `VALIDATION_CHECKLIST.md` for exactly what each
still needs. The real `livespec-cq`/`livespec-lq` pair
(`kueue/cluster-queue-livespec.yaml`) is applied and healthy on the
live cluster, carrying zero real traffic.

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
| `fair share of remaining host-wide capacity` | Kueue Cohort + `ClusterQueue.spec.cohortName` + Fair Sharing | Kueue's admission controller — orders and bounds admission across every repo's ClusterQueue sharing one cohort | `kueue/cluster-queue-*.yaml` |

## Personal account: repository is the only valid scope

Confirmed live, `livespec-s43svm.14`, 2026-08-16: `thewoolleyman` is a
personal GitHub User account, not an Organization. Phase 1's original
`arc/values.yaml`/`values-host-unique.yaml` pointed `githubConfigUrl`
at the account root (`https://github.com/thewoolleyman`) — ARC's own
URL parser (`github/actions/actions.go` in
`actions/actions-runner-controller`) recognizes exactly three scopes
(`GitHubScopeEnterprise`, `GitHubScopeOrganization`,
`GitHubScopeRepository` — no `GitHubScopeUser` exists at all), so a
single-path-segment URL like that ALWAYS resolves to
`GitHubScopeOrganization` regardless of what kind of account it
actually names. The client then called
`POST /orgs/thewoolleyman/actions/runners/registration-token`, which
404'd — not because of a missing permission (a separate, since-granted
issue), but because no such organization exists.

This is not a corner case to work around — it is a **structural fact
about GitHub's self-hosted-runner model**: only Enterprise and
Organization accounts get an account-wide runner pool; a personal User
account has access to exactly ONE scope, repository. There is no
account-wide fallback to fall back to.

**Consequence for `.16` (incremental per-repo cutover):** this design's
one-`AutoscalingRunnerSet`-per-repository pattern (see "Deriving a new
repository's ClusterQueue" below) is not merely the shape chosen for
Kueue fair-share modeling — for this fleet, on this account type, it is
the ONLY shape GitHub's own API makes possible. `.16` should not treat
"per-repo vs. shared org-wide set" as an open design question to
revisit; there is no shared-org-wide alternative available to compare
it against.

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

**CONFIRMED LIVE (2026-08-16, `VALIDATION_CHECKLIST.md` items 1 and 5,
against the pinned v0.19.1 install on `poweredge-xubuntu`) — corrects
this section's original, unvalidated assumptions:**

- The field is `spec.cohortName` (a plain string) under
  `kueue.x-k8s.io/v1beta2`, not `spec.cohort` under `v1beta1` — the
  latter is ACCEPTED but logs `"Warning: This version is deprecated.
  Use v1beta2 instead."` `kubectl explain` confirms `cohortName`
  "doesn't reference any object," so the flat, non-hierarchical model
  this design always intended is still correct — only the field name
  and apiVersion needed updating. (Kueue's newer first-class `Cohort`
  CRD, mentioned in an earlier draft of this section, remains available
  for hierarchical cohorts but is not used here, unchanged from the
  original reasoning.)
- **There is no `Configuration.fairSharing.enable` toggle at this
  version — an earlier draft of this design was wrong about that.**
  Reading `kubernetes-sigs/kueue`'s `apis/config/v1beta2/
  configuration_types.go` at the pinned tag shows `FairSharing` now
  has only a `preemptionStrategies` field; there is no boolean enable
  anywhere in scope (checked the feature-gate list too — no bare
  `FairSharing` gate exists, only two of its sub-behaviors, both
  Beta/default-true since v0.17). Empirically confirmed by direct
  test: two `ClusterQueue`s sharing a `cohortName`, with ZERO change
  to the Kueue `Configuration` ConfigMap, borrowed capacity from each
  other correctly — a `ClusterQueue` with `nominalQuota: 1` admitted 3
  concurrent workloads by borrowing 2 units from a cohort-mate with
  spare `nominalQuota: 3`. Basic cross-`ClusterQueue` borrowing is
  active by default; nothing needs to be "turned on." (The
  `enable-fair-sharing.sh` script this section originally described no
  longer exists — it targeted a Configuration field that was never
  real at this version.)
- Every `cluster-queue-*.yaml` in this design still sets
  `fairSharing.weight: 1` — equal weight for every repo, since the
  specification states no per-repo priority differentiation — this
  field itself IS real and accepted; only the separate "enable" step
  was fictional.

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
| `kueue/cluster-queue-livespec.yaml` | Worked example: livespec's `ClusterQueue` (`nominalQuota: 36`, doubled from its measured 18 podman-pool slots) + `LocalQueue`. Applied and healthy on the live cluster since 2026-08-16. |
| `kueue/cluster-queue-EXAMPLE-repo.yaml` | Template for every other fleet repository — copy, fill in the placeholders. |
| `arc/values-livespec.yaml` | Worked example: livespec's per-repo `AutoscalingRunnerSet` Helm values (`maxRunners: 36`, `githubConfigUrl` narrowed to this one repo, pod template wired to `livespec-lq` via the `kueue.x-k8s.io/queue-name` label and requesting one `ci-runner.io/churn-slot`). Not yet applied live — see `VALIDATION_CHECKLIST.md` item 5's disposition. |
| `arc/values-EXAMPLE-repo.yaml` | Template for every other fleet repository. |
| `kueue/cluster-queue-livespec-console-beads-fabro.yaml` + `arc/values-livespec-console-beads-fabro.yaml` | `livespec-s43svm.16`'s chosen first NON-GATING cutover lane (2026-08-16) — a standalone console app nothing else in the fleet depends on, and the smallest repo by live-measured slot width. `nominalQuota`/`maxRunners: 16`, UNDOUBLED (see that file's header for the correction below). Design-only in this PR — not yet applied live, no workflow routing changed yet. |
| `node-extended-resource/patch-node-churn-capacity.sh` | Idempotently registers `ci-runner.io/churn-slot` as a node-status extended resource with an explicit, non-defaulted capacity argument. Applied live at a small provisional capacity (4) for validation — see `VALIDATION_CHECKLIST.md` item 4. |
| `node-extended-resource/reapply-node-extended-resource.service` + `.timer` | Every-5-minute reconciliation reapplying that patch — belt-and-suspenders; a live `systemctl restart k3s` did NOT drop the patch (see "Known caveat" below), but this is cheap insurance against scenarios not yet tested (full host reboot, a k3s version upgrade). |
| `VALIDATION_CHECKLIST.md` | What was, and still needs to be, confirmed against the live cluster. Items 1, 3, 5, and 7 are now CONFIRMED (2026-08-16); items 2, 4, and 6 remain open. |

## Correction (2026-08-16, livespec-s43svm.16): the live pool does NOT
## independently double every repo's ceiling

This design's original worked example (`cluster-queue-livespec.yaml`,
`values-livespec.yaml`) assumed each repo's `nominalQuota`/`maxRunners`
is its own measured matrix width doubled, sized independently per repo
(livespec: 18 → 36). Reading the LIVE poweredge-xubuntu
`ci-runner-supervisor` unit (`systemctl cat ci-runner-supervisor`,
2026-08-16) shows the real apportionment is different:

```
--repos "thewoolleyman/livespec:75 thewoolleyman/livespec-dev-tooling:63 \
  thewoolleyman/livespec-driver-codex:67 thewoolleyman/livespec-driver-claude:66 \
  thewoolleyman/livespec-orchestrator-git-jsonl:66 thewoolleyman/livespec-overseer:65 \
  thewoolleyman/livespec-runtime:64 thewoolleyman/livespec-console-beads-fabro:16"
```

Those eight values SUM TO EXACTLY 482 — the physical host-wide cap. The
live pool apportions the FIXED 482 budget across repos by observed
demand; it does not give every repo an independently-doubled ceiling
that could itself sum past 482. `cluster-queue-livespec.yaml`'s
`nominalQuota: 36` (from a stale "18 slots" reading) is now known
inaccurate against the live figure (75) and is flagged here rather
than silently corrected in that file, to keep this note's provenance
clear. Reconciling the Kueue-side formula against this live
apportionment is real follow-up work (`livespec-s43svm.15`
`VALIDATION_CHECKLIST.md` item 4) — the new
`cluster-queue-livespec-console-beads-fabro.yaml` pair below
deliberately uses its own live-measured figure (16) UNDOUBLED rather
than assume either formula, since it is a first small proof lane, not
the steady-state post-cutover ceiling.

## Deriving a new repository's ClusterQueue

1. Read that repo's measured matrix width — its own
   `ci-runner-supervisor.service` `--slots` value if it is on the
   podman pool today (see `../../supervisor/README.md`), or its actual
   GitHub Actions matrix job count if not. Never guess.
2. Double it. (See the correction above: confirm against the LIVE
   `ci-runner-supervisor` unit's actual apportionment first — the
   original doubling assumption is not what the live pool runs today.)
3. Copy `kueue/cluster-queue-EXAMPLE-repo.yaml` to
   `kueue/cluster-queue-<repo>.yaml`, filling in `<REPO>` and
   `<DOUBLED_CEILING>`.
4. Copy `arc/values-EXAMPLE-repo.yaml` to `arc/values-<repo>.yaml`,
   filling in `<REPO>` and `<DOUBLED_CEILING>` — the SAME number as
   step 3 (see "Two enforcement points, one number" above).
5. Apply both once `.16` (incremental per-repo cutover) reaches that
   repo — not before; this design pass ships zero real cutover.

## Known caveat: the node-status patch's robustness, corrected against live evidence

`kubectl patch node --subresource=status` is the Kubernetes-documented
mechanism for a STATIC extended resource
(https://kubernetes.io/docs/tasks/administer-cluster/extended-resource-node/).
This section originally assumed, unvalidated, that kubelet does not
persist arbitrary keys placed there and that a kubelet restart would
silently drop `ci-runner.io/churn-slot`. **CONFIRMED LIVE (2026-08-16,
`VALIDATION_CHECKLIST.md` item 3): that assumption was WRONG, at least
for a `systemctl restart k3s` service restart.** The patched capacity
(`4` at the time of the test) was read back unchanged, both
`status.capacity` and `status.allocatable`, immediately after the node
reported `Ready` again post-restart. This has NOT been tested across a
full host reboot or a k3s version upgrade, so
`node-extended-resource/reapply-node-extended-resource.timer` (every 5
minutes) stays installed as cheap belt-and-suspenders for those
untested scenarios, not because the service-restart case needs it. If
this pattern doesn't hold for a full reboot either, a real device
plugin would be the more robust choice for a multi-node cluster (the
migration decision record notes k3s supports growing to multiple
nodes via embedded etcd) — reconsider then.

## Nature

Like `../` (phase 1), these are host operational artifacts (YAML, Helm
values, shell) — not Python product code — so they are NOT part of the
`just check` aggregate. Recreatability is still the contract:
`node-extended-resource/patch-node-churn-capacity.sh` is idempotent and
re-runnable, and every manifest is declarative (`kubectl apply`-able
repeatedly).
