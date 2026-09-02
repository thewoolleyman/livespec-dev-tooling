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

There is a fourth number the table above does not carry — the
specification's "physical host-wide cap ... no configuration or recovery
path may derive or admit 964", enforced by the `ci-runner.io/churn-slot`
extended resource's node capacity rather than by any of the three
clauses. `kueue/DERIVATION.md` carries all four terms together, the
arithmetic that turns the third one into each repository's actual
`nominalQuota`, and the procedure for recomputing them when the host's
capacity changes. Read it before editing any number in `kueue/` or any
`maxRunners` in `arc/`.

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

## Two enforcement points, two DIFFERENT numbers

**Corrected 2026-08-19 by `livespec-s43svm.15`'s derivation. This
section previously required `maxRunners` and `nominalQuota` to carry the
SAME number; that was wrong, and every file asserting it has been
updated.**

`arc/values-<repo>.yaml`'s `maxRunners` and
`kueue/cluster-queue-<repo>.yaml`'s `nominalQuota` are two different
terms of the same `min()`, so they are correctly UNEQUAL:

- `maxRunners` is the formula's `doubled repository logical ceiling` — a
  property of the REPOSITORY (how many runner pods its workflows would
  ever want at once), enforced by ARC independently of Kueue.
- `nominalQuota` is the formula's `fair share of remaining host-wide
  capacity` — a property of the HOST (this repository's slice of the
  finite churn-slot budget), enforced by Kueue.

Forcing them equal collapses the formula. If a repository's ARC ceiling
equals its fair share, it can never scale into capacity a peer is
leaving idle, and the specification's "Repositories MAY fairly borrow
unused capacity" clause becomes unreachable — Kueue would grant the
borrow and ARC would refuse to create the pods. The correct relation is
`nominalQuota_i <= maxRunners_i`: a guaranteed floor no larger than the
hard ceiling.

Both are still needed. `maxRunners` alone gives no fair sharing;
`nominalQuota` alone lets Kueue admit workloads ARC's scale set then
refuses to scale into pods, since the two are independently-configured
controllers.

`kueue/DERIVATION.md` decides the generator question this section
previously deferred (`VALIDATION_CHECKLIST.md` item 6): with the
derivation parameterized and eight repositories, a generator is NOT
earned — the documented derivation plus committed files is the
mechanism.

## Why the physical cap holds regardless of the quota arithmetic

Kueue's `nominalQuota` is LOGICAL bookkeeping per ClusterQueue, while
the `ci-runner.io/churn-slot` extended resource
(`node-extended-resource/`) is registered on the actual node with a
FIXED, finite capacity. A Kueue-admitted workload still needs a
schedulable pod, and a pod requesting `ci-runner.io/churn-slot: "1"` can
only run while the node has an unclaimed unit of that resource — so no
matter what the SUM of nominal quotas across the cohort is, the number
of runner pods that can be simultaneously `Running` is hard-capped by
the extended resource's node capacity. This is exactly the "physical cap
remains exactly 482... no design may imply or admit 964" invariant,
enforced at the scheduler layer rather than by the admission formula's
own arithmetic. Proven empirically — `VALIDATION_CHECKLIST.md` item 7.

The practical consequence: no arithmetic mistake in `DERIVATION.md`'s
apportionment can over-admit. The worst a wrong quota sum can do is
under-use the host, or cap cohort borrowing lower than intended.

Note that the quotas as derived DO sum to exactly the node capacity
rather than exceeding it — not because exceeding it would be unsafe, but
because the sum is the one thing a human can verify by adding eight
integers, and because cohort borrowing is bounded by that sum. An
earlier version of this section argued the opposite case (quotas summing
ABOVE the physical cap), which followed from the retired
one-number-in-two-places model; see `kueue/DERIVATION.md`.

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
| `kueue/DERIVATION.md` | How the specification's admission formula becomes each repository's actual `nominalQuota`: the four terms and their mechanisms, the demand weights, the largest-remainder apportionment, the recomputation procedure for a new capacity, and the decisions on the generator question and the still-open permanent capacity. Read this before editing any number in `kueue/`. |
| `kueue/cluster-queue-<repo>.yaml` (9 files) | Every fleet repository's `ClusterQueue` + `LocalQueue`, one pair per repo, all in the `fleet-ci-runner-pool` cohort. Quotas derived per `DERIVATION.md` at capacity C=64 (the increase-ci-runners raise, 2026-08-30): `livespec` 10, `livespec-driver-codex` 9, `livespec-driver-claude` 9, four mid-band repos 8, `livespec-console-beads-fabro` 2, `livespec-driver-pi` 2 — summing to exactly 64. (History: first applied at C=16 summing to 16 across 8 repos, drift-verified 2026-08-19 `livespec-s43svm.27`; `livespec-driver-pi` joined as the ninth 2026-08-20.) |
| `kueue/cluster-queue-phase1-proof.yaml` | The phase-1 proof `ClusterQueue`/`LocalQueue`/`ResourceFlavor`, captured live 2026-08-19 so the Kueue tree is fully recreatable. Deliberately outside the `fleet-ci-runner-pool` cohort and quota'd on cpu/memory rather than churn-slot, so it is excluded from the apportionment and cannot consume a churn slot. |
| `arc/values-livespec.yaml` | Worked example: livespec's per-repo `AutoscalingRunnerSet` Helm values (`maxRunners: 36`, `githubConfigUrl` narrowed to this one repo, pod template wired to `livespec-lq` via the `kueue.x-k8s.io/queue-name` label and requesting one `ci-runner.io/churn-slot`). Not yet applied live — see `VALIDATION_CHECKLIST.md` item 5's disposition. |
| `arc/values-EXAMPLE-repo.yaml` | Template for every other fleet repository. |
| `arc/values-livespec-console-beads-fabro.yaml` | `livespec-s43svm.16`'s chosen first NON-GATING cutover lane (2026-08-16) — a standalone console app nothing else in the fleet depends on, and the smallest repo by live-measured demand weight. |
| `node-extended-resource/patch-node-churn-capacity.sh` | Idempotently registers `ci-runner.io/churn-slot` as a node-status extended resource with an explicit, non-defaulted capacity argument. Applied live at a small provisional capacity (4) for validation — see `VALIDATION_CHECKLIST.md` item 4. |
| `node-extended-resource/install-reapply-unit.sh` | Installs the patch script to `/usr/local/lib/ci-runner-k3s/` and the unit + timer to `/etc/systemd/system`, substituting the required capacity argument for the unit file's deliberate `CAPACITY_PLACEHOLDER`. Node-local; run it on any node added to the pool. Installed live on `poweredge-xubuntu` at capacity 16, 2026-08-19 (`livespec-s43svm.26`) — the units had been written in `.15` but never installed, so a k3s restart would have dropped `ci-runner.io/churn-slot` and stalled ALL Kueue admission. Re-installed at capacity 64 on 2026-08-30 (the increase-ci-runners raise, livespec epic `livespec-zec4mz`). |
| `node-extended-resource/reapply-node-extended-resource.service` + `.timer` | Every-5-minute reconciliation reapplying that patch — belt-and-suspenders; a live `systemctl restart k3s` did NOT drop the patch (see "Known caveat" below), but this is cheap insurance against scenarios not yet tested (full host reboot, a k3s version upgrade). |
| `node-inotify-budget/99-ci-runner-inotify.conf` | The per-user inotify INSTANCE budget (`fs.inotify.max_user_instances = 8192`) the pool needs, shipped as a `/etc/sysctl.d/` drop-in with its derivation in the file header. The kernel default 128 was exhausted at ~100 concurrent containers on 2026-09-01 and stalled fleet CI (livespec plan `ci-runner-pod-lifecycle-reliability`, epic `livespec-ifwnqj`, research/002); the relation is ratified as a host requirement in livespec core `non-functional-requirements.md` §"Self-hosted CI runner host requirements" (v216). |
| `node-inotify-budget/install-inotify-sysctl.sh` | Installs that drop-in to `/etc/sysctl.d/` and applies it now, parsing the intended value from the shipped file so the verify step cannot drift. Node-local; run it on any node added to the pool and after any node rebuild. No reapply timer (unlike `node-extended-resource/`): `systemd-sysctl` re-applies `/etc/sysctl.d/` at every boot, so the value is natively durable. Makes the interim hand-applied `/etc/sysctl.d/99-ci-runner-inotify.conf` (placed live on `poweredge-xubuntu` 2026-09-01) reproducible. |
| `wedged-runner/scan-wedged-runners.sh` | Finds runner pods that are `Running` and `ready=true` to Kubernetes but permanently dead to GitHub (the `Registration <uuid> was not found` loop), reporting pod, scale set, and age. Exits 1 when any is found, so it is usable directly as a check; `--clear` deletes them, opt-in. See "Wedged runner vs. saturation" below for why this cannot be inferred from any capacity signal. |
| `wedged-runner/install-wedged-runner-scan.sh` | Installs that scan to `/usr/local/lib/ci-runner-k3s/` and the unit + timer to `/etc/systemd/system`, substituting the required `report`/`clear` mode for the unit file's deliberate `MODE_PLACEHOLDER`. Node-local; run it on any node added to the pool. Installed live on `poweredge-xubuntu` in `clear` mode, 2026-08-19 (`livespec-s43svm.30`) — that script's header carries the argument for `clear` over `report` on a host with no failure routing. |
| `wedged-runner/scan-wedged-runners.service` + `.timer` | Every-5-minute wedged-runner sweep. Unlike the reapply timer this is not belt-and-suspenders: the wedged state is self-perpetuating (a dead runner suppresses the scale-up that would replace it), so without an external sweep the scale set stays blocked until a human notices — which is exactly how the condition was found, 33+ minutes into a held merge gate. |
| `arc/recycle-scale-set-runners.sh` | Deletes a scale set's IDLE runner pods after a `helm upgrade`, skipping any pod with a live `-workflow` companion. Run it at the end of every apply: `helm upgrade` replaces the listener but leaves existing runner pods on the old pod template and the old listener session. Closes the re-cut path into the wedged state; see "Recycle the runner pods after every upgrade" below for why that is a partial fix. |
| `VALIDATION_CHECKLIST.md` | What was, and still needs to be, confirmed against the live cluster. Items 1, 3, 5, and 7 CONFIRMED (2026-08-16); item 6 decided and item 4 superseded (2026-08-19, `kueue/DERIVATION.md`); only item 2 remains open. |
| `apparmor/ci-runner-workflow` | The AppArmor profile hook-generated WORKFLOW pods run under. Reproduces containerd's default deny set verbatim and widens only the `ptrace`/`signal` peer expressions — see "The workflow pod is not the runner pod" below. |
| `apparmor/install-apparmor-profile.sh` | Loads that profile on a runner NODE and converges the `arc-hook-pod-template` ConfigMap. Node-local: re-run per node and after any node rebuild. |
| `arc/hook-pod-template.yaml` | The pod-spec extension the ARC Kubernetes-mode container hook reads via `ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE`. Pins the workflow pod to that profile, and carries the warm uv cache's reader side (read-only mount + `postStart` copy + `UV_CACHE_DIR`; see `warm-cache/README.md`). Its header records which merge semantics each field depends on and the two keys it deliberately never sets. |
| `arc/converge-hook-pod-template.sh` | The one idempotent converge of the `arc-hook-pod-template` ConfigMap from that file, shared by `apparmor/install-apparmor-profile.sh` and `warm-cache/install-warm-cache.sh` so the two installers cannot drift on how it is written. |
| `warm-cache/` | Tier 1 of the cache tiers (livespec repo `plan/fleet-ci-runner-pool/research/design.md`), re-scoped to this lane under `livespec-s43svm.2`: a fleet-wide warm uv cache lower on the dedicated `/var/cache/ci-runner` volume, written only by the `ci-warm-cache` CronJob (`warm-cache-populate.sh`, generations + atomic symlink publish) and copied read-only into every workflow pod. `install-warm-cache.sh` derives the routed-repository list from `arc/values-*.yaml`. Measured: cold `uv sync` 7.9 s → 0.5 s warm + 0.8 s copy. See `warm-cache/README.md`. |
| `arc/values-livespec-overseer.yaml` | `livespec-overseer`'s per-repo `AutoscalingRunnerSet` values (`maxRunners: 65`, `livespec-overseer-lq`), and the first values file wiring the hook pod template — the reference implementation the other nine copy. Applied live 2026-08-18 (Helm revision 2). |
| `arc/values-livespec-dev-tooling.yaml`, `arc/values-livespec-driver-claude.yaml`, `arc/values-livespec-driver-codex.yaml`, `arc/values-livespec-orchestrator-git-jsonl.yaml`, `arc/values-livespec-runtime.yaml` | The five remaining per-repo scale sets, captured from their live Helm releases 2026-08-19 (`livespec-s43svm.26`) and wired to the hook pod template (`livespec-s43svm.25`). |
| `arc/values-livespec-driver-pi.yaml`, `kueue/cluster-queue-livespec-driver-pi.yaml` | The NINTH repository, stood up 2026-08-20 after the eight-repo cutover sequence had closed. Committed in the same change that created the scale set, rather than captured retroactively. Its `maxRunners: 13` is the fleet's first ACTUAL matrix-width measurement rather than a podman-era proxy, and its arrival is what surfaced the `max(1, …)` sum-invariant collision documented in `kueue/DERIVATION.md`. |
| `arc/values-poweredge-xubuntu-k3s.yaml` | The surviving PHASE-1 proof scale set, also live and also captured 2026-08-19. Named by scale set rather than by repo because it points at `livespec-dev-tooling`, which already owns a `values-<repo>.yaml`. Not Kueue-gated; see the file's header. Its phase-1 sibling `local-ci-k3s` (`arc/values-local-ci-k3s.yaml`, captured the same day) was retired — Helm release uninstalled 2026-08-23, file deleted — under `livespec-s43svm.28`, because no workflow in any fleet repo routed to it. |
| `reconstruct/converge-ci-stack.sh` | The one idempotent converge of the ENTIRE CI CLUSTER stack from this repository — ARC controller + all ten runner scale sets + the `arc-hook-pod-template` ConfigMap + Kueue core + every `ResourceFlavor`/`ClusterQueue`/`LocalQueue` — with zero manual `kubectl`/`helm` steps. One run takes an empty k3s datastore to all listeners `Running` and Kueue admitting. See "Reconstruct-on-boot" below for the scope boundary and the `install-arc.sh`/`install-kueue.sh` drift it supersedes. |
| `reconstruct/converge-ci-stack.service` | Boot-ordered `oneshot` (`After=k3s.service`) that runs the converge once per boot. This is what makes the host CATTLE: today none of the cluster stack re-applies on boot, so a datastore wipe loses it. |
| `reconstruct/install-converge-unit.sh` | Copies the converge script AND the `arc/`+`kueue/` artifacts it applies into `/usr/local/lib/ci-runner-k3s/` (the host carries no repo checkout, so the boot unit must be self-contained), installs the unit, and ENABLES it — not `--now`, since starting it applies the stack live. Node-local; re-run after editing any values/queue/template/converge artifact, and on any node rebuild. |
| `datastore-tmpfs/var-lib-rancher-k3s-server-db.mount` | systemd `.mount` unit backing the k3s kine/SQLite datastore directory (`/var/lib/rancher/k3s/server/db`, ~110 MB live) with tmpfs, so control-plane fsyncs are RAM-speed and never queue behind CI churn on the array (livespec plan `ci-runner-pod-lifecycle-reliability`, research/003: the kine `Slow SQL` stall that dropped Kueue's admission webhook fleet-wide on 2026-09-01). VOLATILE by design — cleared on every reboot, which is exactly what keeps the reconstruct-on-boot path exercised rather than rotting. See "Datastore on tmpfs" below for the two units it depends on, the fail-safe ordering, and the rollback. |
| `datastore-tmpfs/install-datastore-tmpfs.sh` | Installs that mount unit and ENABLES it for next boot — NEVER `--now`, since mounting over a RUNNING k3s's datastore would hide it mid-flight. Pre-gates on BOTH reconstruct units (`inject-github-app-secret.service`, `converge-ci-stack.service`) being enabled and refuses otherwise: a volatile datastore is safe only on a host that rebuilds itself. Node-local; re-run on any node rebuild. |

## Reconstruct-on-boot: the CI cluster stack as cattle

`reconstruct/` makes the single-node k3s host **reconstructible** — a
prerequisite for later making its datastore volatile (tmpfs). Today the
whole CI cluster stack lives ONLY in the k3s datastore, applied once by hand
(`../provision-k3s.sh` → `../install-arc.sh` → `../install-kueue.sh`, plus the
phase-2 per-repo scale sets and queues). Nothing re-applies on boot, so the
host is a PET: wipe the datastore and the cluster is gone. `reconstruct/`
closes that gap with a boot-ordered `systemd` `oneshot`
(`converge-ci-stack.service`, `After=k3s.service`) that runs one idempotent
converge script.

**What it converges, in order** (`converge-ci-stack.sh`): wait for the node
`Ready` → fail-closed pre-gate on the `arc-github-app-installation` secret →
ARC controller (`helm upgrade --install`, chart `0.14.2`) → all ten runner
scale sets from `arc/values-*.yaml` (each `helm upgrade --install`, chart
`0.14.2`) → the `arc-hook-pod-template` ConfigMap (via
`arc/converge-hook-pod-template.sh`) → Kueue core (`v0.19.1` manifests,
server-side apply + rollout + CRD-established wait) → `kueue/resource-flavor.yaml`
and every `kueue/cluster-queue-*.yaml`. Every operation is a
`helm upgrade --install` or a `kubectl apply`, so a second run against an
already-converged cluster makes no disruptive change.

**Starting from an EMPTY datastore** (GitHub App secret assumed present — a
sibling work-item, `livespec-qqzlek`, automates that re-injection), one boot
converges the cluster to all scale-set listeners `Running` and Kueue admitting
pods, with zero manual `kubectl`/`helm` steps.

**Scope boundary.** The converge owns the CLUSTER stack only. It does NOT own
the NODE-LOCAL machinery — the AppArmor profile (`apparmor/`), the inotify
sysctl budget (`node-inotify-budget/`), the churn-slot extended resource
(`node-extended-resource/`), and the warm uv cache (`warm-cache/`) — each of
which has its own installer and its own boot-durability (a `/etc/apparmor.d`
file, a `/etc/sysctl.d` drop-in, a reapply timer, a CronJob). It also decides
NO numbers: scale-set ceilings live in `arc/values-*.yaml` and queue quotas in
`kueue/cluster-queue-*.yaml`; the converge only makes those already-decided
artifacts durable. And it never creates the GitHub App secret — it fail-closes
if the secret is absent (`livespec-qqzlek` owns re-injection).

**Drift it supersedes.** `../install-arc.sh` step 2 applies the
`poweredge-xubuntu-k3s` release from the PHASE-1 file `arc/values-host-unique.yaml`;
the converge instead uses the phase-2 captured file
`arc/values-poweredge-xubuntu-k3s.yaml` for EVERY scale set (including that
one), and never calls `install-arc.sh` step 2. Likewise `../install-kueue.sh`
applies the phase-1 `kueue/resources.yaml` whose `phase1-proof-*` objects are
declared at `v1beta1`; the phase-2 tree carries the SAME objects at `v1beta2`
(`kueue/cluster-queue-phase1-proof.yaml`), so the converge INLINES only the
Kueue-core install and applies the phase-2 `kueue/` tree exclusively, rather
than invoking `install-kueue.sh` and double-applying those objects at two API
versions. Both choices mirror the same principle: the phase-2 captured
artifacts are the source of truth, the phase-1 installers are superseded.

**This item authors repo artifacts ONLY.** `install-converge-unit.sh` ENABLES
the unit (runs on next boot) but does not start it, because starting it applies
the stack live; the live cutover is a separate attended step.

## Datastore on tmpfs: making the volatility safe

k3s keeps the entire cluster state — every Deployment, CRD instance, queue,
Secret, and pod object — in one kine/SQLite datastore, `state.db` plus its
WAL under `/var/lib/rancher/k3s/server/db`. On `poweredge-xubuntu` that
directory sat on the same virtual disk as containerd's snapshots and every
runner's `local-path` work volume. Under 60+ concurrent CI jobs the array
ran at its cold-random-write service ceiling (livespec plan
`ci-runner-pod-lifecycle-reliability`, research/004: ~1,000 write IOPS at
~100 ms with a ~100-deep queue for 100 minutes), kine logged `Slow SQL`,
Kueue's leader lost its lease and exited by design, and its single
admission webhook (`mpod.kb.io`, `failurePolicy: Fail`) dropped — so every
pod creation in the fleet failed for the restart window (research/003).

`datastore-tmpfs/var-lib-rancher-k3s-server-db.mount` backs that directory
with tmpfs. Control-plane fsyncs become RAM-speed and can never queue
behind CI churn, so a datastore stall of that class cannot recur. The
datastore is small (~110 MB live; `size=2G` is a ceiling, not a
reservation) so the RAM cost is negligible — the objection that retired
the RAM-backed *work-volume* idea (`livespec-trxcf7`, hundreds of GiB) does
not apply here.

### Volatility is the point, and it is safe only because of two other units

tmpfs is cleared on **reboot** — it survives a plain
`systemctl restart k3s`, because the mount is owned by the kernel, not by
the k3s process. So after every boot k3s starts with an **empty**
datastore, and the cluster is rebuilt from this repository by, in order:

1. `secret-reinjection/inject-github-app-secret.service` — the GitHub App
   secret, decrypted as root from the host's own systemd credstore
   (seeded once, attended, from 1Password; `livespec-qqzlek`).
2. `reconstruct/converge-ci-stack.service` — ARC + every scale set + the
   hook-pod ConfigMap + Kueue + every queue (`livespec-olp4c5`; see
   "Reconstruct-on-boot" above).

That is the whole bargain: a host whose datastore rebuilds from git on
every boot is cattle; a host that merely *could* be rebuilt by a runbook
nobody runs is a pet with a plan. Making the datastore volatile forces the
rebuild path to be exercised on every reboot, so it cannot quietly rot.
It also means the two units above are a hard **precondition** —
`install-datastore-tmpfs.sh` refuses to install the mount unless both are
enabled, and the mount unit's own header says the same.

Because a reboot clears the datastore AND every container together, the
API server's view and the running containers can never disagree: there is
no split-brain, and deliberately **no snapshot/restore leg** — restoring a
stale datastore into a live cluster would be actively harmful, and the
maintainer's own reasoning (2026-09-02) was that a restore that is not the
exact latest state is worse than starting clean.

### Fail-safe ordering, and what a bad rebuild actually costs

The mount unit is ordered `Before=k3s.service` but k3s is **not** made to
`Require` it. If the tmpfs mount ever fails, k3s starts on the **on-disk
datastore underneath** — stale but intact — a degraded fallback rather
than a blocked boot. The `.mount` is also `WantedBy=` (not `RequiredBy=`)
`multi-user.target`, so a mount hiccup cannot hold up the machine.

None of this can brick the host. The tmpfs holds only the ~110 MB
datastore; the OS, the RAID array, the beads ledger, and every durable
file are untouched. A bug in the converge script degrades to "the CI
cluster comes up empty or wrong until someone re-runs the (fixed)
converge" — the converge only ever runs `helm upgrade --install` and
`kubectl apply`, so it creates and updates and never deletes host state.
And because the tmpfs is mounted **over** the on-disk directory (hiding
the disk copy, not deleting it), **rollback** is: stop k3s,
`systemctl disable --now var-lib-rancher-k3s-server-db.mount`, start k3s —
back on the original datastore.

### Cutover procedure and live state

The prep is zero-downtime: seed the credstore, install both reconstruct
units, install (enable, never start) this mount. The flip itself needs k3s
stopped, since the datastore cannot be swapped out from under a running
SQLite. The maintainer-set sequence (2026-09-02) is a **k3s-restart test
first** — `systemctl stop k3s` → `systemctl start` the mount (a fresh,
empty tmpfs) → `systemctl start k3s` → start the two units in order →
verify every scale set, queue and the secret came back from empty — and
a **full host reboot only after that test is de-kinked**, as the final
durability proof. Either event kills in-flight jobs (they orphan on the
empty datastore and re-run), the same class of event as the 2026-09-01
k3s restart. The added reboot cost is a couple of minutes, dominated by
the ARC-controller and Kueue rollout waits, most of which a reboot
already spends restarting the cluster today.

**The k3s-restart cutover test PASSED on `poweredge-xubuntu`, 2026-09-02.**
From `systemctl stop k3s` through a fresh empty tmpfs, k3s start (node
`Ready` in ~12 s, only the four default namespaces, no ARC or Kueue CRDs —
provably empty), the secret unit, and the converge (**47 s cold**, exit 0),
the cluster came back **identical to its pre-test baseline** — ARC
controller 1/1, 10 scale sets, 10 ClusterQueues, 10 LocalQueues, 2
ResourceFlavors, the hook ConfigMap, Kueue 1/1 — with **10 listener pods
Running, zero auth failures**, and real fleet jobs flowing through the
rebuilt cluster within ~2 minutes of the stop. Exactly one kink surfaced:
the secret unit's phase-3 verify counted 0 keys while the secret was
correctly rebuilt with 3 (an empty-line-vs-`grep -c .` bug), fixed and
re-proven live in `fix/secret-inject-verify-count` (`0c1dc719`). The
mount unit is now **enabled** for boot. Live state: datastore on tmpfs,
both reconstruct units enabled, credstore seeded, mount enabled + active.
What remains is the maintainer's **full host reboot** as the final
durability proof (mount + units firing unattended from a real boot).

### What this does NOT do

It does not own the reconstruct units (they have their own installers and
this README's "Reconstruct-on-boot" section), it does not touch the
node-local machinery (AppArmor, inotify, churn-slot, warm cache), and it
does not move the bulk CI churn off the array — that is the NVMe tiering
(`livespec-e2vcqf`), a separate, hardware-gated piece. Nor does it move
anything precious: the beads/Dolt ledger and backups stay on the
redundant RAID and must never go on tmpfs.

## The workflow pod is not the runner pod

The single most consequential thing to know about `containerMode:
kubernetes`, and the thing that cost `livespec-overseer` a reverted
cutover: **a job's `container:` image does not run in the runner pod.**
The runner's container hook (`/home/runner/k8s/index.js`) creates a
SEPARATE pod per job — `<runner-pod-name>-workflow` — and builds that
pod's spec itself.

So the `template.spec.securityContext` in a `values-<repo>.yaml` reaches
the runner pod ONLY. The pod where the repo's tests actually execute is
created with an EMPTY `securityContext`, inheriting containerd's
defaults, and nothing in the Helm values reaches it. Reading a scale
set's `securityContext` and concluding you know what the tests ran under
is reading the wrong pod.

`ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE` is the one supported seam. The
hook loads that file as untyped YAML and merges its `spec` into the
generated pod spec key by key, so fields pass through verbatim rather
than being dropped by a typed deserializer.

### What went wrong, and why it looked like a test bug

`livespec-overseer` was routed to `livespec-overseer-k3s` on 2026-08-17
and rolled back the same day: four tests failed deterministically on the
scale set while staying green on `ubuntu-latest` AND green in the same
Fabro image under plain docker. Root-caused 2026-08-18 (livespec epic
`livespec-s43svm.18`), one mechanism behind all four.

Ubuntu's `kernel.apparmor_restrict_unprivileged_userns=1` **stacks** the
AppArmor label of every confined task, so a workflow-pod process carries
the compound label `cri-containerd.apparmor.d//&unconfined` rather than
the bare profile name. containerd's default profile grants intra-container
`signal` and `ptrace` only to `peer=cri-containerd.apparmor.d` — a bare
peer name, which a stacked label does not match. The profile therefore
denied its own containers the operations those rules exist to allow:

```
apparmor="DENIED" operation="signal" profile="cri-containerd.apparmor.d"
  peer="cri-containerd.apparmor.d//&unconfined"
```

`os.killpg` returns `EACCES` outright. The tmux failures are the same
denial wearing a disguise: tmux derives `#{pane_current_path}` by
readlink()ing `/proc/<pane foreground pgrp>/cwd`, and reading another
process's `/proc/PID/cwd` is a ptrace-read — so the denial surfaces as an
EMPTY STRING rather than an error, and laundered into assertion failures
that read like logic bugs in unrelated tests. Docker is unaffected because
`docker-default` is not stacked the same way, which is exactly why the
same image was green under plain docker and red in a pod.

Measured in a pod reproducing the workflow pod's spec:

| Pod AppArmor | child `/proc/PID/cwd` | `os.killpg` | `pane_current_path` | the 11 tests |
|---|---|---|---|---|
| containerd default (as shipped) | `EACCES` | `EACCES` | empty | 4 failed |
| `ci-runner-workflow` (the fix) | resolves | OK | correct | all passed |

The fix keeps every containerd deny rule and only widens the two peer
expressions. AppArmor stays in **enforce** mode; no capability was added
and nothing was made privileged. `type: Localhost` means a node missing
the profile fails pod admission rather than silently running unconfined.

Apply it to a node with `apparmor/install-apparmor-profile.sh`, then add
the volume, `volumeMount`, and env var shown in
`arc/values-livespec-overseer.yaml` to that repo's values file.

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
clear.

**RESOLVED 2026-08-19 (`livespec-s43svm.15`), see
`kueue/DERIVATION.md`.** Those eight values are the derivation's DEMAND
WEIGHTS `w_i`, not logical ceilings — the distinction this note was
missing. Each repository's `nominalQuota` is now its largest-remainder
share of the host's registered churn-slot capacity `C`, apportioned by
`w_i`; at `C = 482` that reproduces the podman apportionment above
exactly, and at the current `C = 64` (the increase-ci-runners raise,
2026-08-30) it gives `livespec` 10, `livespec-driver-codex` 9,
`livespec-driver-claude` 9, four mid-band repos 8, `livespec-console-beads-fabro`
2, and `livespec-driver-pi` 2 — summing to exactly 64. The doubling
clause did not disappear — it moved to where it belongs, ARC's
`maxRunners`, which is a per-repository ceiling and not a share of the
host at all.

## Enumerating the pool — where the members actually are

**The GitHub repository runners API cannot tell you what is in this
pool**, and the way it fails is worse than returning nothing: it returns
a confident, complete-looking answer that is wrong. This is the single
most misleading thing about operating this pool, so it is stated before
anything on this page that depends on it.

Two facts combine, and neither is obvious on its own.

**ARC runners register with an EMPTY label array** and are selected by
SCALE SET NAME, not by label. Measured 2026-08-21 on
`thewoolleyman/livespec`, mid-job:

```
{"total_count":1,"runners":[{"id":31096,
  "name":"livespec-local-ci-k3s-d4j8r-runner-xndz6",
  "status":"offline","busy":false,"labels":[]}]}
```

So an ARC member carries neither a shared pool label nor a host-unique
one — not by oversight, but because that mode does not use labels at all.

**They are visible only WHILE a runner pod exists.** A scale set runs
`minRunners: 0`, so pods exist only during a job, and each registration
is ephemeral — one job, then deregister. Three consecutive reads of the
listing above during one CI run returned three, then two, then one
runner. An IDLE scale set contributes nothing to the listing whatsoever.

> **Do not read that absence as structural.** An earlier survey
> (2026-08-21, `livespec-s43svm.40`) queried
> `livespec-console-beads-fabro` at a moment when no job was running, saw
> only its sixteen permanently-registered podman-era runners, and
> concluded ARC runners "do not appear in the repository runners API at
> all". They do — transiently. Transient absence read as structural
> absence, from a single well-formed query against the right endpoint.
> The correct statement is that the listing answers "which runners are
> registered RIGHT NOW", which for an ephemeral autoscaling pool is not
> the same question as "what is in this pool".

The pool itself is enumerable only from the cluster:

```bash
# The scale sets — one per repository, and the unit a job selects.
kubectl -n arc-runners get autoscalingrunnersets \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}'

# The live runner pods, if any. An idle scale set runs minRunners: 0, so
# an EMPTY listing is the normal healthy state, not a missing pool.
kubectl -n arc-runners get pods \
  -l app.kubernetes.io/component=runner \
  -o custom-columns=NAME:.metadata.name,SET:.metadata.labels.actions\.github\.com/scale-set-name,PHASE:.status.phase

# Which repository each set serves.
helm get values <scale-set-name> -n arc-runners | grep githubConfigUrl
```

The `install-arc.sh` scripts already run the first of these as a
post-install verification step. That is not the same as documenting where
the pool is enumerable: an operator triaging a stalled job is not reading
an installer.

**Addressing one member.** The unit of addressing here is the scale set,
so directing work at one member means routing to its set — through the
repository's `CI_RUNNER_LABELS` variable (see
[`../../set-ci-runner-labels.sh`](../../set-ci-runner-labels.sh), which is
the only sanctioned way to write it) or a literal `runs-on` in a
non-gating workflow. When the pool grows past one host, binding a set to a
particular host is a placement concern — node selectors, taints, or a
per-host set — and MUST be decided then rather than assumed now; nothing
on this page currently constrains where a set's pods land, because with
one node there is nowhere else for them to go.

## Applying a scale set's values

Every LIVE `AutoscalingRunnerSet` on `poweredge-xubuntu` now has a
committed values file in `arc/` — captured under `livespec-s43svm.26`
after six of them had been provisioned imperatively during
`livespec-s43svm.16`'s per-repo cutover and never written down. The
contract that closes is recreatability: the cluster's runner
configuration can be regenerated from this repository rather than only
read back off the cluster with `helm get values`.

Apply one scale set (from a checkout on the node, `KUBECONFIG` pointed
at k3s):

```bash
helm upgrade --install <scale-set-name> \
  --namespace arc-runners \
  --values ci-runner/k3s/phase2/arc/values-<repo>.yaml \
  oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set \
  --version 0.14.2
```

`--values` alone REPLACES the release's user-supplied values; do not add
`--reuse-values`, which would merge the file on top of whatever the
release already carries and quietly preserve any imperative drift this
capture exists to eliminate.

The mapping from scale-set name to values file is not always
`values-<repo>.yaml` — three names diverge, all for reasons recorded in
the files themselves:

| Live release | Values file |
|---|---|
| `livespec-local-ci-k3s` | `arc/values-livespec.yaml` |
| `livespec-console-beads-k3s` | `arc/values-livespec-console-beads-fabro.yaml` |
| `livespec-orchestrator-git-k3s` | `arc/values-livespec-orchestrator-git-jsonl.yaml` |
| `livespec-dev-tooling-k3s` | `arc/values-livespec-dev-tooling.yaml` |
| `livespec-driver-claude-k3s` | `arc/values-livespec-driver-claude.yaml` |
| `livespec-driver-codex-k3s` | `arc/values-livespec-driver-codex.yaml` |
| `livespec-driver-pi-k3s` | `arc/values-livespec-driver-pi.yaml` |
| `livespec-overseer-k3s` | `arc/values-livespec-overseer.yaml` |
| `livespec-runtime-k3s` | `arc/values-livespec-runtime.yaml` |
| `poweredge-xubuntu-k3s` | `arc/values-poweredge-xubuntu-k3s.yaml` |

(A twelfth row, `local-ci-k3s` → `arc/values-local-ci-k3s.yaml`, was
retired under `livespec-s43svm.28`.)

The first two diverge because a scale-set name must stay <=30 characters
(see the naming rule above) while a values file is named for the repo it
serves; the third for the same reason.

To check a release against its file without changing anything, compare
the two YAML documents directly — `helm get values <release> -n
arc-runners` prints exactly the user-supplied values a `--values` apply
would set, so a semantic match of those two documents IS the zero-drift
check:

```bash
helm get values <scale-set-name> -n arc-runners | tail -n +2 > /tmp/live.yaml
diff <(yq -P 'sort_keys(..)' /tmp/live.yaml) \
     <(yq -P 'sort_keys(..)' ci-runner/k3s/phase2/arc/values-<repo>.yaml)
```

### Recycle the runner pods after every upgrade

`helm upgrade` replaces the LISTENER. It does not touch runner pods that
were already `Running`, so those keep serving the pre-upgrade pod
template and stay registered against the previous listener session.
Finish every apply with:

```bash
ci-runner/k3s/phase2/arc/recycle-scale-set-runners.sh <scale-set-name>
```

It deletes that scale set's IDLE runner pods and deliberately skips any
pod with a live `<pod>-workflow` companion, because such a pod is
executing somebody's job and retires on its own — so the recycle is safe
to run unconditionally after an upgrade rather than only when the pool
looks quiet. An idle scale set runs `min-runners: 0` and usually has no
pods at all, in which case the script is a no-op.

Two things this buys. The first is that the values you just applied are
actually in effect, rather than reaching only pods created later — the
reason `livespec-s43svm.25`'s AppArmor rollout had to watch a green run
per release. The second is that a registration issued against the old
listener cannot survive into the new one and strand the scale set in the
wedged state described below.

That second reason is a partial fix and should not be read as more.
Both wedges observed on 2026-08-19 were created roughly an hour AFTER
the last re-cut, so recycling would not have prevented either one; it
closes one known way in, and the trigger for the rest is still open
(`livespec-s43svm.30`).

### Every scale set carries the workflow-pod AppArmor wiring

`livespec-s43svm.25` (2026-08-19) rolled `values-livespec-overseer.yaml`'s
hook-pod-template wiring — the `hook-pod-template` volume, its
`volumeMount`, and `ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE` — to every
other live scale set, one release at a time with a watched green run each.

The reason is not that the other repos' suites were failing. It is that a
suite which does not exercise intra-pod `ptrace`/`signal` today is
LATENT-broken rather than unaffected: the containerd default denies those
operations on this host (see "The workflow pod is not the runner pod"
below), so the first test in any repo that reaches for them fails
deterministically and — as `livespec-overseer` paid for — in a disguise
that reads like a logic bug somewhere else entirely. Wiring every scale
set makes the profile the property of the POOL rather than of one repo.

`arc/values-EXAMPLE-repo.yaml` carries the wiring too, so a scale set
derived from the template after this date gets it without a second
decision.

## Deriving a new repository's ClusterQueue

All eight fleet repositories already have both files. These steps are
for a NINTH repository joining the pool.

1. Establish the new repository's demand weight `w` by measuring its
   actual GitHub Actions matrix job count. Never guess. (Before the podman
   pool was decommissioned this step also allowed reading that repository's
   `ci-runner-supervisor.service` `--slots` value; that pool and its
   documentation are gone, so measurement is the only source.)
2. Add it to `kueue/DERIVATION.md`'s weight table and RE-DERIVE every
   repository's `nominalQuota` at the current capacity `C` — adding a
   repository changes the weight sum, so every existing quota moves.
   Follow that file's "Recomputing at another C" steps; the eight-plus-one
   quotas must still sum to exactly `C`.
3. Copy any existing `kueue/cluster-queue-<repo>.yaml` to the new
   repository's name, substituting the repo name and its derived
   `nominalQuota`, and rewrite the moved quotas in the other files.
4. Copy `arc/values-EXAMPLE-repo.yaml` to `arc/values-<repo>.yaml`. Its
   `maxRunners` is the repository's DOUBLED LOGICAL CEILING — a
   different number from step 3's quota, and larger; see "Two
   enforcement points, two DIFFERENT numbers" above. Set
   `runnerScaleSetName` per the naming rule below — do NOT use
   `<repo>-local-ci-k3s`.
5. Apply, and confirm `kubectl get clusterqueue` still sums to `C`.
6. Route the repository at its scale set, through the guarded writer:

   ```bash
   ci-runner/set-ci-runner-labels.sh thewoolleyman/<repo> <scale-set-name> --dry-run
   ci-runner/set-ci-runner-labels.sh thewoolleyman/<repo> <scale-set-name>
   ```

   Steps 1–5 are cluster changes. Step 6 is the security boundary, and
   it is the one step that must not be a bare `gh variable set` — see
   below.

### Step 6 is the security boundary, so it is not a bare variable write

A repository begins gating merges on self-hosted capacity at the
instant its `CI_RUNNER_LABELS` variable names a self-hosted label. Not
when its scale set is installed, not when its ClusterQueue is
committed — at that write. The livespec repo's
`SPECIFICATION/non-functional-requirements.md` §"Self-hosted CI runner
host requirements" makes the containment-floor reduction CONDITIONAL on
a precondition that engages at exactly that moment: self-hosted
capacity may carry a repository's merge gate ONLY while no
fork-originating workflow can execute on it, enforced by the
repository's fork-pull-request approval setting **at its strictest
tier** (`all_external_contributors`), because under the weaker tiers a
RETURNING outside contributor's fork pull request runs its
fork-controlled workflow definition with no approval event.

Nothing used to attach that precondition to the write, and the cost was
real. Nine repositories were cut over during `livespec-s43svm.16`/`.18`
with the tier simply assumed to hold; on 2026-08-21 two of them —
`livespec-overseer` and `livespec-driver-pi` — were found gating merges
on self-hosted capacity at `first_time_contributors`, live and
unnoticed since their cutovers. `livespec-driver-pi` is the instructive
one: it was cut over as the ninth repository on 2026-08-20, its tier had
never been strict, and its cutover was otherwise performed correctly. A
checklist row would not have caught it, which is why the check is bound
to the write rather than written down beside it.

`../../set-ci-runner-labels.sh` reads the tier first and REFUSES the
write unless it is strict — including when the tier cannot be read at
all, since an unreadable tier is not a strict tier. `--set-tier`
corrects a weak tier in the same operation and then re-reads to verify
before touching the variable. Routing BACK to hosted capacity
(`ubuntu-latest`) reads no tier and is never blocked: failover away from
a sick pool must not depend on a permissions endpoint.

This is not a CI-resident gate, and could not be one. The tier endpoint
needs fine-grained `Administration: read`, which the workflow
`permissions:` key does not expose and `GITHUB_TOKEN` can therefore
never hold; the script runs in the maintainer's shell under the
maintainer's own credential. The reasoning is recorded in full on
`livespec-s43svm.39`.

### `runnerScaleSetName` MUST stay <=30 characters

livespec-s43svm.22 (root-caused 2026-08-17, upstream
actions/actions-runner-controller#4368, closed won't-fix — "pick a
shorter name") found that `runner-container-hooks`' k8s hook
truncates the per-job "workflow" pod name at a hard 63-character
Kubernetes limit, applied to the FULL runner-pod name
(`<scaleset>-<ephemeralrunnerset-suffix>-runner-<pod-suffix>`), not
just the scale-set portion. Past ~35 characters of scale-set name the
truncation eats the per-runner unique suffix entirely, so every
CONCURRENTLY running runner in that scale set produces the
byte-identical workflow-pod name and every job but the first fails
with `pods "..." already exists` — deterministic under any 2+-job
matrix, and invisible to a single-job proof-of-life dispatch (which is
exactly why phase-1/phase-2's own single-job proofs never caught it).

Use `<repo>-k3s` (NOT `<repo>-local-ci-k3s`, which was the original,
now-abandoned scheme and cost 13 characters this fix cannot afford).
30 characters total leaves a 5-character margin below the hard
35-character boundary, since the ephemeralrunnerset-suffix length
(observed as 5 characters live) is not a contract this fleet can rely
on staying fixed. When `<repo>-k3s` itself exceeds 30 characters,
truncate the repo-name portion at the longest hyphen-bounded prefix
that fits — mechanically, never a hand-picked abbreviation (this fleet
already bans ambiguous ad hoc abbreviations elsewhere — see
`livespec/AGENTS.md` "the bare word `beads-fabro` is BANNED"). Example:
`livespec-console-beads-fabro` (29 chars) does not fit the 26-character
budget after `-k3s`, so its scale set is named
`livespec-console-beads-k3s` (26 chars) — the last hyphen-bounded
prefix that fits, not an invented shorthand.

## Wedged runner vs. saturation — jobs queued, nothing starting

These are two DIFFERENT failures that look identical from GitHub and
have OPPOSITE fixes. Both present as: a job sits `queued` against a k3s
scale set, its `runner_name` empty, and nothing starts. Triage them
apart before touching any capacity number — two separate sessions
misdiagnosed the wedge as saturation on 2026-08-19 (`livespec-s43svm.30`),
and one of them raised the churn-slot capacity, which cannot help.

**Saturation** is the pool genuinely being full: every churn slot is
committed, so Kueue holds new workloads. Real, and the fix is capacity.

**A wedged runner** is a runner pod that is `Running` and `ready=true`
to Kubernetes but whose GitHub registration was invalidated
server-side. It never exits. It loops forever on `Registration <uuid>
was not found` → `Reload credentials` → sleep ~55s. ARC counts it as a
live runner, so the listener computes `"assigned job"=1 decision=1
currentRunnerCount=1`, re-patches `replicas=1` every ~50s, and never
creates a pod that could take the queued job. **Raising capacity cannot
clear this**, at any number, because the scale set is not short of
capacity — it believes it already has a runner. The only remedy is to
delete the dead pod.

The reason the wedge is easy to misroute is that it is invisible to
every capacity signal: pod phase `Running`, readiness `true`, Kueue zero
gated and zero pending, node allocatable with headroom. It presents as
saturation while showing none of saturation's evidence, and "no evidence
of saturation" reads as "look harder for saturation" unless you know to
look for this instead.

### The two discriminating commands

Run both. They are independent; either can be the answer.

Saturation — are workloads actually being held for want of a slot?

```bash
kubectl get workloads -A \
  -o custom-columns=NS:.metadata.namespace,NAME:.metadata.name,ADMITTED:.status.conditions[?\(@.type==\"Admitted\"\)].status
kubectl get nodes -l k3s-role=arc-runner-host \
  -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.status.allocatable.ci-runner\.io/churn-slot}{"\n"}{end}'
```

Saturated means unadmitted workloads present AND allocatable churn-slot
fully consumed. If nothing is pending and the node has headroom, the
pool is not saturated and no capacity change will help.

Wedge — is a live-looking runner pod actually dead?

```bash
ci-runner/k3s/phase2/wedged-runner/scan-wedged-runners.sh
```

It exits 0 when clean and 1 with a per-pod report when any runner pod is
wedged, naming the pod, its scale set, and its age. It needs no GitHub
API call: the log signature is emitted only after the broker has told
the runner its own registration does not exist, and the runner has no
code path that re-registers, so the string plus a recency window is
certainty rather than a heuristic.

### Clearing a wedge

```bash
kubectl delete pod -n arc-runners <pod-name>          # one pod
ci-runner/k3s/phase2/wedged-runner/scan-wedged-runners.sh --clear   # all flagged
```

ARC creates a replacement within seconds and the queued job is claimed
by it — verified live on 2026-08-19, where a `check-coverage` job that
had been queued 33+ minutes went `in_progress` on the replacement pod.
Deleting a scale-set runner pod is safe by construction: the pods are
ephemeral, serve at most one job each, and a wedged one cannot hold work
at all.

### It runs automatically

`wedged-runner/install-wedged-runner-scan.sh` installs the sweep as a
systemd timer on a runner node, every 5 minutes, in an explicitly-chosen
`report` or `clear` mode. `poweredge-xubuntu` runs it in `clear` mode
(2026-08-19), because nothing on that host routes systemd unit failures
anywhere a human sees them — a report-only sweep there would reproduce
the very recovery path that already failed, a wedge sitting until
somebody happens to look. See that script's header for the full argument
and the three guards that make an unattended delete safe.

### Known limitation: automatic clearing hides recurrence

Running the sweep in `clear` mode absorbs recurrences silently. That is the
point when the wedge is rare, and it is a hazard when it is not: if whatever
causes wedging gets worse, the timer will delete pods every five minutes
forever and nothing says the condition escalated. That is the same
invisible-signal failure this whole section exists to fix, reintroduced one
level up — and it matters more than usual because the trigger is still
unknown (below), so there is no independent signal that would catch the
escalation instead.

The mitigation is deliberately small. The scan remembers whether the previous
run also found wedged pods (a counter under `/var/lib/ci-runner-k3s/`, tracked
in BOTH modes because repeated *findings* are the signal, not repeated
deletions) and prints a distinct line when findings repeat:

```
ESCALATION: wedged runners found on N CONSECUTIVE sweeps. ...
```

So a one-off wedge stays quiet and a recurring one gets louder. Check for it
with:

```bash
journalctl -u scan-wedged-runners.service --since -1d | grep ESCALATION
```

Be clear about what this is: a journal-visible signal, not a routed alert.
Nothing pages anyone, and an operator who never reads the journal still learns
nothing. Wiring it into the fleet attention surface is tracked separately on
`livespec-s43svm.30`.

### The trigger is not yet proven, and the leading hypothesis is Kueue gating

Tracked on `livespec-s43svm.30`. What is ruled OUT: re-cut invalidation.
Both observed instances were created about an hour AFTER the most recent
`helm upgrade`, so recycling runner pods on upgrade (above) would not
have prevented either.

What the evidence points AT is the gap Kueue opens between a runner's
registration being issued and its container actually starting. At
03:35Z on 2026-08-19 both affected scale sets were heavily
oversubscribed against their own quotas — `livespec-console-beads-k3s`
patched `replicas=16` against a `nominalQuota` of **1** churn-slot, and
`livespec-overseer-k3s` patched `replicas=5`-`6` against a quota of
**2**. Both wedged pods started around 03:43Z, roughly eight minutes
later, which is what being held at the back of a queue like that looks
like. No other scale set was oversubscribed at that ratio, and no other
scale set wedged.

The mechanism that turns a long gating delay into a dead registration is
NOT established. Two candidates, distinguishable by experiment:

- The registration simply expires between issuance and use. Weak on its
  own — an eight-minute wait is short against a JIT config's usual
  lifetime.
- ARC supersedes it. If the ephemeral-runner controller gives up on a
  pod that has not become ready and re-issues, the originally-issued
  registration is dead by the time the still-gated pod finally starts
  with it.

The second fits the timing better and predicts that the wedge rate
scales with gating delay, which is testable directly: drive a burst
well past a scale set's `nominalQuota` and watch whether pods admitted
late wedge at a higher rate than pods admitted immediately. Until that
is settled, the detector above is the load-bearing mitigation, and a
scale set whose `maxRunners` sits far above its Kueue quota is the
configuration to be suspicious of.

#### Every sweep now records the measurement that settles it

Both candidates above share one prediction — that a wedged pod waited a
long time between being created and actually starting — so that wait is
what the scan measures. `scan-wedged-runners.sh` reports a **gate time**
for every pod it looks at:

```
gate = .status.containerStatuses[runner].state.running.startedAt
       - .metadata.creationTimestamp
```

Read it alongside, not instead of, the `age` on the same line. `age`
comes from `.status.startTime`, which the kubelet sets only once the pod
has been admitted — so `age` deliberately excludes the waiting period
under suspicion, and the two numbers diverging is itself the signal.

The readings, and what each one means:

| Reading | What it tells you |
|---|---|
| `gate=<n>s (LONG …)` on a WEDGED pod | Consistent with the hypothesis. Not proof — record `n` and move on. |
| `gate=<n>s (PROMPT -- FALSIFIES …)` on a WEDGED pod | **Kills the hypothesis.** A pod that started promptly and wedged anyway cannot have wedged from waiting. Reopen the mechanism question. |
| `gate=<n>s (prompt)` on a healthy `ok` pod | Control-group data. The hypothesis also claims promptly-started pods do not wedge, so these are the observations that would make a long-gate correlation meaningful rather than incidental. |
| `gate=unknown` | One of the two timestamps was missing. Carries no evidence either way, and is reported as `unknown` rather than as `0` precisely so it is never mistaken for the falsifying reading. |

`LONG` versus `prompt` is a reading aid only — it is a label applied at
`--gate-long-seconds` (default 300s, an order-of-magnitude marker rather
than a measured boundary) and it changes nothing about what is scanned,
flagged, or deleted. The raw `created=` and `runner-started=` timestamps
are printed beside every wedged pod, including on the line that deletes
one, so the number can always be re-derived rather than trusted — and so
the evidence survives the pod that carried it.

This does not settle the trigger on its own. It means the NEXT incident
arrives as evidence instead of as a repeat of the last one, which is the
cheapest available step given that the burst experiment above needs a
deliberate load window.

## Runner-pod lifecycle stall — the THIRD "jobs queued, nothing starting" case

The two cases above assume the pool can create a pod at all. On 2026-09-01
it could not, and neither discriminating command fired: the wedge scan was
clean (7-8 `Running` runner pods, 0 hits), Kueue showed 16 admitted /
0 pending against the console queue, and the node had 700m of 72 CPU
requested and 8 of 64 churn slots allocated — while three PRs sat with
every job queued for 17-60 minutes.

What was happening (livespec plan `ci-runner-pod-lifecycle-reliability`,
epic `livespec-ifwnqj`, research/001-004 — the measured chain):

1. `fs.inotify.max_user_instances` was at the kernel default 128. Every
   containerd shim holds two inotify instances (the cgroup OOM watch);
   kubelet/cadvisor hold ~21; at ~100 concurrent containers uid 0 hit the
   cap, containerd logged `failed to create inotify fd: too many open
   files`, and sandbox lifecycle calls (`KillPodSandbox`, `StopContainer`)
   timed out with `DeadlineExceeded`.
2. The local-path provisioner's per-PVC helper pod therefore sometimes
   exceeded its 120 s ceiling (`ProvisioningFailed: ... create process
   timeout after 120 seconds`), PVC provisioning latency reached
   ~11 minutes, and the scheduler's volume-bind deadline (600 s) expired on
   runner pods (`FailedScheduling: ... PreBind plugin "VolumeBinding":
   binding volumes: context deadline exceeded`) — 94 expiries in
   20 minutes. Each expiry re-queued the pod and left stale claims in the
   provisioner's queue, so the backlog grew instead of draining.
3. A separate variant the same afternoon: the k3s kine/SQLite datastore
   shares the CI-churn disk; under 60+ jobs its writes stalled, the
   single-replica Kueue lost its leader lease and exited by design, and its
   `failurePolicy: Fail` pod webhook (`mpod.kb.io`) made every pod creation
   in the fleet fail for the restart window (27 API-server failures in
   3 minutes; carrier `livespec-okxbkg`).

### The two discriminating commands for this case

```bash
kubectl get pvc -n arc-runners --no-headers | awk '$2=="Pending"' | wc -l
sudo grep -c 'failed to create inotify fd' /var/lib/rancher/k3s/agent/containerd/containerd.log
```

A Pending-PVC count that grows while runner pods cycle `Pending` →
`FailedScheduling` is the lifecycle stall; a non-zero second count names
the inotify cap specifically. For the datastore variant look for a fresh
`kueue-controller-manager` restart, `Slow SQL: INSERT INTO kine` in the k3s
journal, and `failed calling webhook "mpod.kb.io"` in job logs.

### What a CI consumer sees

The job is claimed, then fails at `Initialize containers` with the ARC
Kubernetes hook's `Executing the custom container implementation failed.
Please contact your self hosted runner administrator.` — the `-workflow`
pod could not be created. That is a host condition, not a test failure:
re-run the job on the same commit once the host has cleared.

### Why neither prior remedy applies

Deleting pods (the wedge fix) adds churn to the provisioner's queue, and
raising capacity (the saturation fix) adds containers to an exhausted
kernel budget — the 2026-08-30 raise from C = 16 to 64 is what pushed the
container count into the cap. The host fixes applied 2026-09-01:
`fs.inotify.max_user_instances` 128 → 8192 (persisted in
`/etc/sysctl.d/99-ci-runner-inotify.conf`); local-path-provisioner
`--worker-threads 8 --kube-client-qps 50 --kube-client-burst 100` (live
Deployment only — k3s can re-apply its bundled `local-storage.yaml` on a
restart, which is what `livespec-sernfh` exists to end); kubelet `max-pods`
110 → 200 (see `kueue/DERIVATION.md`, "The pod-capacity constraint"). Making
the first two durable in this directory's node-local install mechanism is
`livespec-a6lxuv`'s open leg; Kueue HA is `livespec-okxbkg`.

## ARC log retention: archive before the kubelet's buffer rotates

Container logs live in the kubelet's rotating buffer, and the ARC controller
is chatty enough to churn through it fast. Measured on `poweredge-xubuntu`
on 2026-08-19:

| Source | Retention observed |
|---|---|
| `deploy/arc-gha-rs-controller` | **~70 minutes** (31,961 lines, 07:02Z–08:13Z) |
| the same, re-measured 4 min later under load | **~4 minutes** |
| a scale-set listener (`livespec-overseer-k3s`) | ~9 hours |

Retention is a function of log VOLUME, so it is shortest exactly when an
incident makes the log worth reading. That is not a theoretical concern
here: it is why `livespec-s43svm.30`'s trigger is still open. A wedged
runner at 03:43Z was investigated around 08:00Z, and the controller log
that would have said whether ARC deleted the runner's registration had
rotated away hours before. The grep for it returned zero.

**A zero from a log that does not cover the window is not evidence of
absence.** It reads identically to a real negative, which is what makes it
the more dangerous of the two — the reader banks a conclusion the data
never supported. The reframing that IS on `.30` came from the listener
logs, and only because their nine-hour margin happened to cover the
incident. That margin is a property of current traffic, not a guarantee.

### What is installed

`arc-log-archive/` ships a script, a oneshot unit, and a 2-minute timer.
Each pass appends only the lines it has not already archived, per pod:

```
/var/log/arc-archive/<pod>.log            the archive (rolled at 1 GiB, one generation)
/var/lib/ci-runner-k3s/arc-log-archive/   per-pod "last archived timestamp" state
```

Install it on any node in the pool, and after any node rebuild:

```bash
sudo ci-runner/k3s/phase2/arc-log-archive/install-arc-log-archive.sh
```

Read it during an incident exactly as you would read `kubectl logs`, except
that it reaches back:

```bash
grep -h "same name" /var/log/arc-archive/arc-gha-rs-controller-*.log
```

### The sizing came from measurement, and the first estimate was wrong

Archiving the live cluster once on 2026-08-19 gave the numbers the ceiling is
set from:

| Measured | Value |
|---|---|
| bytes per archived line | 328 |
| controller output rate | 576 lines in ~40s — about **860 lines/min** |
| controller volume | **16.2 MB/hour** |
| 1 GiB roll ceiling | ~63 hours per generation, ~5 days across both |

The first draft of this used 256 MiB on an ESTIMATED ~450 lines/min and
described it as "on the order of a week". The measured rate is roughly
double, which made that claim wrong by about a factor of ten — 256 MiB is
really about sixteen hours. Worth stating plainly rather than silently
correcting, because a retention horizon shorter than the gap between an
incident and its investigation reintroduces exactly the failure this
archive exists to prevent, only further out.

### Why not simply raise the kubelet's rotation limits

That is the direct fix, and it is deliberately not taken.
`--container-log-max-size` and `--container-log-max-files` are k3s **server**
arguments, so changing them means restarting k3s — on the host that carries
every fleet repository's gating CI. A diagnostic improvement does not earn an
outage window.

The archive runs entirely beside the cluster, creates no Kubernetes object,
and is removed by disabling one timer. If the rotation limits are ever raised
for other reasons, it stays correct and simply has less work to do.

### Two details worth knowing before you rely on it

- **The interval is set by the shortest measured retention, not by load.**
  Two minutes, against a buffer that was seen collapsing to four. The rest of
  this tree runs its timers at five, and five would not be safe here.
- **The de-duplication is load-bearing, not tidiness.** `--since-time` is
  inclusive at its boundary, so a naive implementation re-appends the
  boundary line every pass. A forensic grep that returns the same line eleven
  times invites the reader to infer a repeating event that never repeated —
  the same class of error as the vacuous zero above, arrived at from the
  opposite direction.

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
