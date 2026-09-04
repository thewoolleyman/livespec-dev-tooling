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
| `kueue/cluster-queue-<repo>.yaml` (9 files) | Every fleet repository's `ClusterQueue` + `LocalQueue`, one pair per repo, all in the `fleet-ci-runner-pool` cohort. Quotas derived per `DERIVATION.md` at the CURRENT capacity **C=32 — INTERIM** (maintainer decision 2026-09-02, livespec plan `ci-runner-pod-lifecycle-reliability` / epic `livespec-ifwnqj`, until the NVMe tiering `livespec-e2vcqf` lifts the RAID's data-plane ceiling): `livespec` 5, `livespec-driver-codex` 5, five mid-band repos 4, `livespec-console-beads-fabro` 1, `livespec-driver-pi` 1 — summing to exactly 32. (History: C=64 from 2026-08-30 to 2026-09-02 — `livespec` 10, `livespec-driver-codex` 9, `livespec-driver-claude` 9, four mid-band repos 8, console 2, pi 2, summing to 64, the increase-ci-runners raise `livespec-zec4mz`, to be restored when e2vcqf lands; first applied at C=16 summing to 16 across 8 repos, drift-verified 2026-08-19 `livespec-s43svm.27`; `livespec-driver-pi` joined as the ninth 2026-08-20.) |
| `kueue/cluster-queue-phase1-proof.yaml` | The phase-1 proof `ClusterQueue`/`LocalQueue`/`ResourceFlavor`, captured live 2026-08-19 so the Kueue tree is fully recreatable. Deliberately outside the `fleet-ci-runner-pool` cohort and quota'd on cpu/memory rather than churn-slot, so it is excluded from the apportionment and cannot consume a churn slot. |
| `kueue/core/` (`kustomization.yaml`, `deployment-ha-patch.yaml`, `manager-config-patch.yaml`) | The fleet-owned kustomize overlay that IS the Kueue-core install: the upstream `v0.19.1` release manifest (by URL, pinned in lockstep with `KUEUE_VERSION` in `reconstruct/converge-ci-stack.sh`, which asserts they agree) plus two strategic-merge patches — the `kueue-controller-manager` Deployment at **2 replicas** with probe `timeoutSeconds` 1 → 5, and the `kueue-manager-config` ConfigMap carrying leader-election `leaseDuration 60s / renewDeadline 45s / retryPeriod 5s`. `reconstruct/converge-ci-stack.sh` step 4 applies it as one `kubectl apply --server-side -k` on every boot; `install-converge-unit.sh` copies the directory beside the converge. Why each number: the patch files' headers and "Kueue HA" below (livespec plan `ci-runner-pod-lifecycle-reliability`, item `livespec-okxbkg`). |
| `arc/values-livespec.yaml` | Worked example: livespec's per-repo `AutoscalingRunnerSet` Helm values (`maxRunners: 36`, `githubConfigUrl` narrowed to this one repo, pod template wired to `livespec-lq` via the `kueue.x-k8s.io/queue-name` label and requesting one `ci-runner.io/churn-slot`). Not yet applied live — see `VALIDATION_CHECKLIST.md` item 5's disposition. |
| `arc/values-EXAMPLE-repo.yaml` | Template for every other fleet repository. |
| `arc/values-livespec-console-beads-fabro.yaml` | `livespec-s43svm.16`'s chosen first NON-GATING cutover lane (2026-08-16) — a standalone console app nothing else in the fleet depends on, and the smallest repo by live-measured demand weight. |
| `node-extended-resource/patch-node-churn-capacity.sh` | Idempotently registers `ci-runner.io/churn-slot` as a node-status extended resource with an explicit, non-defaulted capacity argument. Applied live at a small provisional capacity (4) for validation — see `VALIDATION_CHECKLIST.md` item 4. |
| `node-extended-resource/install-reapply-unit.sh` | Installs the patch script to `/usr/local/lib/ci-runner-k3s/` and the unit + timer to `/etc/systemd/system`, substituting the required capacity argument for the unit file's deliberate `CAPACITY_PLACEHOLDER`. Node-local; run it on any node added to the pool. Installed live on `poweredge-xubuntu` at capacity 16, 2026-08-19 (`livespec-s43svm.26`) — the units had been written in `.15` but never installed, so a k3s restart would have dropped `ci-runner.io/churn-slot` and stalled ALL Kueue admission. Re-installed at capacity 64 on 2026-08-30 (the increase-ci-runners raise, livespec epic `livespec-zec4mz`); re-installed at capacity **32** on 2026-09-02 — an INTERIM throttle (maintainer decision, livespec epic `livespec-ifwnqj`; see `kueue/DERIVATION.md` "The derivation at C = 32") to be restored to 64 when `livespec-e2vcqf` lands. |
| `node-extended-resource/reapply-node-extended-resource.service` + `.timer` | Every-5-minute reconciliation reapplying that patch — belt-and-suspenders; a live `systemctl restart k3s` did NOT drop the patch (see "Known caveat" below), but this is cheap insurance against scenarios not yet tested (full host reboot, a k3s version upgrade). Since 2026-09-04 (`livespec-kgl3`) the timer also carries `OnCalendar=*:0/5`: `OnUnitActiveSec` re-arms only from a SUCCESSFUL activation, so after that morning's dependency-failed boot the timer had no next elapse at all; the wall-clock trigger fires every five minutes regardless of the service's history, and makes `Persistent=true` effective (it applies to `OnCalendar` timers only). See "After a dependency-failed boot" under "Reconstruct-on-boot". |
| `node-inotify-budget/99-ci-runner-inotify.conf` | The per-user inotify INSTANCE budget (`fs.inotify.max_user_instances = 8192`) the pool needs, shipped as a `/etc/sysctl.d/` drop-in with its derivation in the file header. The kernel default 128 was exhausted at ~100 concurrent containers on 2026-09-01 and stalled fleet CI (livespec plan `ci-runner-pod-lifecycle-reliability`, epic `livespec-ifwnqj`, research/002); the relation is ratified as a host requirement in livespec core `non-functional-requirements.md` §"Self-hosted CI runner host requirements" (v216). |
| `host-thermal/apply-idrac-thermal.sh` | Idempotently converges the PowerEdge node's iDRAC cooling configuration and verifies it: fan control re-asserted AUTOMATIC (the closed thermal loop; manual speeds are never used on a box that takes sustained multi-runner bursts — on 2026-09-04 the fans sat on the idle floor with CPUs at 72 °C under 39 runners until re-asserted), the "third-party PCIe card cooling response" DISABLED (iDRAC8's blind ~7.4k-RPM offset for non-Dell cards; the loop on CPU/DIMM/inlet/exhaust/PERC sensors is untouched), and the thermal profile set to "Minimum Power" (the least aggressive curve; "Maximum Performance" rejected as a cooling bias for turbo headroom the box never lacks). Reads first, writes only on drift. Decision record: `poweredge-xubuntu-info` FAN_COOLING.md; livespec plan `poweredge-raid-array-maintenance`. |
| `host-thermal/install-racadm.sh` | Installs Dell's in-band iDRAC CLI (`srvadmin-idracadm7` + `srvadmin-hapi`, 11.0.0.0) from Dell's OpenManage repository as two SHA-256-pinned `.deb` downloads (the host runs a newer Ubuntu than any codename Dell lists, so no repository line is added). The thermal profile has no IPMI form; racadm reaches the iDRAC attribute store over the host's internal pass-through as root with no credentials and no network path, which is what makes the setting reproducible from git on a rebuilt node. No-op when the pinned version is present. |
| `host-thermal/install-host-thermal.sh` + `apply-idrac-thermal.service` | Installs racadm, copies the apply script to `/usr/local/lib/ci-runner-k3s/`, enables the boot unit (`WantedBy=multi-user.target`, ordered only after the IPMI modules — deliberately NOT on the k3s/converge chain, which a failed k3s mount dependency skipped wholesale on 2026-09-04), and converges now. The settings live in the iDRAC and survive reboots and OS rebuilds by themselves; the boot re-apply is insurance for an iDRAC reset-to-defaults and the path by which a NEW node gets them. |
| `node-inotify-budget/install-inotify-sysctl.sh` | Installs that drop-in to `/etc/sysctl.d/` and applies it now, parsing the intended value from the shipped file so the verify step cannot drift. Node-local; run it on any node added to the pool and after any node rebuild. No reapply timer (unlike `node-extended-resource/`): `systemd-sysctl` re-applies `/etc/sysctl.d/` at every boot, so the value is natively durable. Makes the interim hand-applied `/etc/sysctl.d/99-ci-runner-inotify.conf` (placed live on `poweredge-xubuntu` 2026-09-01) reproducible. |
| `wedged-runner/scan-wedged-runners.sh` | Finds runner pods that are `Running` and `ready=true` to Kubernetes but permanently dead to GitHub (the `Registration <uuid> was not found` loop), reporting pod, scale set, and age. Exits 1 when any is found, so it is usable directly as a check; `--clear` deletes them, opt-in. See "Wedged runner vs. saturation" below for why this cannot be inferred from any capacity signal. |
| `wedged-runner/install-wedged-runner-scan.sh` | Installs that scan to `/usr/local/lib/ci-runner-k3s/` and the unit + timer to `/etc/systemd/system`, substituting the required `report`/`clear` mode for the unit file's deliberate `MODE_PLACEHOLDER`. Node-local; run it on any node added to the pool. Installed live on `poweredge-xubuntu` in `clear` mode, 2026-08-19 (`livespec-s43svm.30`) — that script's header carries the argument for `clear` over `report` on a host with no failure routing. |
| `wedged-runner/scan-wedged-runners.service` + `.timer` | Every-5-minute wedged-runner sweep. Unlike the reapply timer this is not belt-and-suspenders: the wedged state is self-perpetuating (a dead runner suppresses the scale-up that would replace it), so without an external sweep the scale set stays blocked until a human notices — which is exactly how the condition was found, 33+ minutes into a held merge gate. |
| `runner-pod-lifecycle/scan-runner-pod-lifecycle.sh` | Detects the runner-pod LIFECYCLE stall — the THIRD "jobs queued, nothing starting" case — as seven named classes read from node-side observables that persist long enough for a sweep to see them: `pvc-pending`, `bind-deadline`, `inotify-emfile`, `containerd-deadline`, `hook-failure`, `stale-listener`, `capacity-absent`. Every journal, log and event read is bounded to a 5-minute window (`containerd.log` rotates, and is walked backwards to the cutoff). Exits 1 naming each class with its count, 0 on a clean node, 2 when it cannot read one of its inputs — fail-closed, never a false clean. Report-only: nothing in this family is safe to auto-delete. Every sweep ends with ONE best-effort OTLP POST to the host collector — `livespec.ci_lifecycle.<class>` (one gauge per class, always emitted, 0 when clean), `livespec.ci_kueue.pending` / `.admitted`, `livespec.ci_churn_slot.allocatable` / `.quota_sum` — landing in the `livespec` env's `metrics` dataset; `--no-emit` skips it. See "Runner-pod lifecycle stall" → "The detector" below, and its "What every sweep emits to Honeycomb" (livespec plan `ci-runner-pod-lifecycle-reliability`, item `livespec-nhjpai`; emission `livespec-vwzv`). |
| `runner-pod-lifecycle/install-runner-pod-lifecycle-scan.sh` | Installs that scan to `/usr/local/lib/ci-runner-k3s/` and the unit + timer to `/etc/systemd/system`, enabled and started. No mode argument, by decision rather than omission: there is no clear mode (the installer's header says why). Node-local; run it on any node added to the pool and after any node rebuild. |
| `runner-pod-lifecycle/scan-runner-pod-lifecycle.service` + `.timer` | Every-5-minute lifecycle-stall sweep, report-only: `systemctl is-failed scan-runner-pod-lifecycle.service` and its journal are the signal, exactly as the wedge sweep's report mode. `OnBootSec=4min` sits after the boot converge so the first sweep after a reboot reads a converged cluster rather than one still being built. |
| `arc/recycle-scale-set-runners.sh` | Deletes a scale set's IDLE runner pods after a `helm upgrade`, skipping any pod with a live `-workflow` companion. Run it at the end of every apply: `helm upgrade` replaces the listener but leaves existing runner pods on the old pod template and the old listener session. Closes the re-cut path into the wedged state; see "Recycle the runner pods after every upgrade" below for why that is a partial fix. |
| `VALIDATION_CHECKLIST.md` | What was, and still needs to be, confirmed against the live cluster. Items 1, 3, 5, and 7 CONFIRMED (2026-08-16); item 6 decided and item 4 superseded (2026-08-19, `kueue/DERIVATION.md`); only item 2 remains open. |
| `apparmor/ci-runner-workflow` | The AppArmor profile hook-generated WORKFLOW pods run under. Reproduces containerd's default deny set verbatim and widens only the `ptrace`/`signal` peer expressions — see "The workflow pod is not the runner pod" below. |
| `apparmor/install-apparmor-profile.sh` | Loads that profile on a runner NODE and converges the `arc-hook-pod-template` ConfigMap. Node-local: re-run per node and after any node rebuild. |
| `arc/hook-pod-template.yaml` | The pod-spec extension the ARC Kubernetes-mode container hook reads via `ACTIONS_RUNNER_CONTAINER_HOOK_TEMPLATE`. Pins the workflow pod to that profile, and carries the warm uv cache's reader side — since `livespec-lvtu` just `UV_CACHE_DIR` and `UV_LINK_MODE=copy`, pointing uv at the hardlink seed the local-path provisioner made when the work volume was created (see `warm-cache/README.md`); the cache mounts nothing from the host and copies nothing — plus the warm cargo cache's reader side (the `postStart` write of `/.cargo/config.toml` pointing at `crates-proxy/`), the compilation cache's reader side (the `/opt/ci-runner/bin` mount, the `SCCACHE_REDIS_*` env, and the `[build] rustc-wrapper` stanza in the same file; see `sccache/README.md`), and the fleet-wide cache kill switch (`CI_CACHE_KILL_SWITCH`, which also removes the job's uv seed). Its header records which merge semantics each field depends on and the two keys it deliberately never sets. |
| `arc/converge-hook-pod-template.sh` | The one idempotent converge of the `arc-hook-pod-template` ConfigMap from that file, shared by `apparmor/install-apparmor-profile.sh` and `warm-cache/install-warm-cache.sh` so the two installers cannot drift on how it is written. |
| `warm-cache/` | Tier 1 of the cache tiers (livespec repo `plan/fleet-ci-runner-pool/research/design.md`), re-scoped to this lane under `livespec-s43svm.2`: a fleet-wide warm uv cache lower at `/var/lib/rancher/k3s/storage/.warm`, a hidden sibling of the runner work volumes on the `ci-workvols` tier, written only by the `ci-warm-cache` CronJob (`warm-cache-populate.sh`, generations + atomic symlink publish) and HARDLINK-seeded into every new work volume by the local-path provisioner's setup script (`local-path-provisioner/`). `install-warm-cache.sh` derives the routed-repository list from `arc/values-*.yaml`. Measured: cold `uv sync` 7.9 s → 0.5 s warm; the seed 2.3 s and 269 MB of metadata for the 1.4 GB / 159k-file live generation, against 6.8 s and 2.2 GB for the per-start byte copy it replaced (`livespec-lvtu`). See `warm-cache/README.md`, whose "Lesson" records why a per-start byte copy must never ship again. |
| `arc/values-livespec-overseer.yaml` | `livespec-overseer`'s per-repo `AutoscalingRunnerSet` values (`maxRunners: 65`, `livespec-overseer-lq`), and the first values file wiring the hook pod template — the reference implementation the other nine copy. Applied live 2026-08-18 (Helm revision 2). |
| `arc/values-livespec-dev-tooling.yaml`, `arc/values-livespec-driver-claude.yaml`, `arc/values-livespec-driver-codex.yaml`, `arc/values-livespec-orchestrator-git-jsonl.yaml`, `arc/values-livespec-runtime.yaml` | The five remaining per-repo scale sets, captured from their live Helm releases 2026-08-19 (`livespec-s43svm.26`) and wired to the hook pod template (`livespec-s43svm.25`). |
| `arc/values-livespec-driver-pi.yaml`, `kueue/cluster-queue-livespec-driver-pi.yaml` | The NINTH repository, stood up 2026-08-20 after the eight-repo cutover sequence had closed. Committed in the same change that created the scale set, rather than captured retroactively. Its `maxRunners: 13` is the fleet's first ACTUAL matrix-width measurement rather than a podman-era proxy, and its arrival is what surfaced the `max(1, …)` sum-invariant collision documented in `kueue/DERIVATION.md`. |
| `arc/values-livespec-orchestrator-beads-fabro.yaml`, `kueue/cluster-queue-livespec-orchestrator-beads-fabro.yaml` | The TENTH repository, stood up 2026-09-04 (livespec plan `ci-runner-pod-lifecycle-reliability`, Carrier G1, `livespec-ifwnqj.1`) after the maintainer settled that its recorded hosted-only caution (the fleet's live golden-master tier lives in a separate workflow on a separate runner) was no reason to keep its ordinary CI off the pool. Committed in the same change that created the scale set. Its `maxRunners: 42` is twice a MEASURED 21-job matrix (master run 33893048859), the second real measurement after `livespec-driver-pi`'s; its arrival moved exactly one sibling quota (`livespec-driver-codex` 5 → 4) — see `kueue/DERIVATION.md` "Recomputation on the tenth repository". Scale set `livespec-orchestrator-k3s`: the 33-character repo name is truncated at the last hyphen-bounded prefix that fits the 30-character budget, like `livespec-orchestrator-git-k3s`. |
| `arc/values-poweredge-xubuntu-k3s.yaml` | The surviving PHASE-1 proof scale set, also live and also captured 2026-08-19. Named by scale set rather than by repo because it points at `livespec-dev-tooling`, which already owns a `values-<repo>.yaml`. Not Kueue-gated; see the file's header. Its phase-1 sibling `local-ci-k3s` (`arc/values-local-ci-k3s.yaml`, captured the same day) was retired — Helm release uninstalled 2026-08-23, file deleted — under `livespec-s43svm.28`, because no workflow in any fleet repo routed to it. |
| `reconstruct/converge-ci-stack.sh` | The one idempotent converge of the ENTIRE CI CLUSTER stack from this repository — ARC controller + all eleven runner scale sets + the `arc-hook-pod-template` ConfigMap + Kueue core + every `ResourceFlavor`/`ClusterQueue`/`LocalQueue` — with zero manual `kubectl`/`helm` steps. One run takes an empty k3s datastore to all listeners `Running` and Kueue admitting — after first asserting (step 1b) that every runner node's allocatable `ci-runner.io/churn-slot` equals the capacity the INSTALLED reapply unit carries, and re-running `patch-node-churn-capacity.sh` when it does not (`livespec-kgl3`). See "Reconstruct-on-boot" below for the scope boundary and the `install-arc.sh`/`install-kueue.sh` drift it supersedes. |
| `reconstruct/converge-ci-stack.service` | Boot-ordered `oneshot` (`After=k3s.service`; `After=`/`Wants=` `reapply-node-extended-resource.service` and `inject-github-app-secret.service`, so a hand-started converge pulls the reapply in too) that runs the converge once per boot. This is what makes the host CATTLE: today none of the cluster stack re-applies on boot, so a datastore wipe loses it. |
| `reconstruct/install-converge-unit.sh` | Copies the converge script AND the `arc/`+`kueue/` artifacts it applies into `/usr/local/lib/ci-runner-k3s/` (the host carries no repo checkout, so the boot unit must be self-contained), installs the unit, and ENABLES it — not `--now`, since starting it applies the stack live. Node-local; re-run after editing any values/queue/template/converge artifact, and on any node rebuild. |
| `datastore-tmpfs/var-lib-rancher-k3s-server-db.mount` | systemd `.mount` unit backing the k3s kine/SQLite datastore directory (`/var/lib/rancher/k3s/server/db`, ~110 MB live) with tmpfs, so control-plane fsyncs are RAM-speed and never queue behind CI churn on the array (livespec plan `ci-runner-pod-lifecycle-reliability`, research/003: the kine `Slow SQL` stall that dropped Kueue's admission webhook fleet-wide on 2026-09-01). VOLATILE by design — cleared on every reboot, which is exactly what keeps the reconstruct-on-boot path exercised rather than rotting. See "Datastore on tmpfs" below for the two units it depends on, the fail-safe ordering, and the rollback. |
| `datastore-tmpfs/install-datastore-tmpfs.sh` | Installs that mount unit and ENABLES it for next boot — NEVER `--now`, since mounting over a RUNNING k3s's datastore would hide it mid-flight. Pre-gates on BOTH reconstruct units (`inject-github-app-secret.service`, `converge-ci-stack.service`) being enabled and refuses otherwise: a volatile datastore is safe only on a host that rebuilds itself. Node-local; re-run on any node rebuild. |
| `local-path-provisioner/local-path-provisioner.yaml` | The FLEET-OWNED local-path provisioner: k3s's bundled `local-storage.yaml` byte-for-byte plus the pool's tuning (`--worker-threads 8 --kube-client-qps 50 --kube-client-burst 100`, derivation in the header) and the warm-cache seed — its `setup` script hardlinks the current warm uv cache generation into every new work volume during PVC provisioning, inside the provisioner's busybox helper pod on the volume's parent mount — after the runner pod is scheduled and before it starts, so the runner pod's volume wait absorbs the ~2 s seed (`livespec-lvtu`; the header records the helper-pod facts it rests on, read from the provisioner's source). Applied by the converge on every boot in place of the bundled copy, which `k3s-config/` disables — the 2026-09-02 reboot proved k3s otherwise re-applies its own manifest and silently reverts the tuning (`livespec-sernfh`). |
| `k3s-config/config.yaml` + `install-k3s-config.sh` | The k3s server configuration as SOURCE (`kubelet-arg: max-pods=200`; `disable: [local-storage]`), installed to `/etc/rancher/k3s/config.yaml` plus the `local-storage.yaml.skip` packaged-manifest marker as a second enforcement point for the disable. Replaces the hand-written config of 2026-09-01 that lived nowhere in git (`livespec-a6lxuv`'s rebuild-durability leg). `../provision-k3s.sh` runs it before the first k3s start. Takes effect on the next k3s start; never restarts k3s itself. |
| `storage-sweep/sweep-runner-scratch.sh` + `.service` + `install-storage-sweep.sh` | Boot-ordered (`Before=k3s.service`) removal of every `pvc-*` directory under `/var/lib/rancher/k3s/storage`, gated on the datastore being EMPTY (`ConditionPathExists=!.../state.db`, re-checked by the script) so it can only ever run when no PV can reference a directory. Ends the orphan accumulation the tmpfs boot creates by design (`livespec-psq5we`: ~150 dirs / ~50 GB found 2026-09-02). Safe ONLY because every PVC on this pool is ephemeral runner scratch — see "Storage sweep" below before placing any other PVC on this node. |
| `crates-proxy/` | The cargo half of the warm dependency cache, HOST-SERVED (plan `ci-runner-cache-tiers`, `livespec-dev-tooling-oiltq3`, v054 §"Runner-pool build cache tiers"): one digest-pinned nginx `proxy_cache` in front of crates.io's sparse index and crate CDN on the `ci-cache` tier, read by every workflow pod over cluster DNS (the hook template's `postStart` writes `/.cargo/config.toml`) and by off-node consumers over hostPort 3080; no write surface, verified upstream TLS, stale-on-error. Zero bytes copied per job start — the reason it is not a lower like uv's. The populator pre-warms it. See `crates-proxy/README.md`. |
| `crates-proxy/converge-crates-proxy.sh` | The idempotent converge of the proxy's cluster objects with a bounded rollout wait — called by the boot converge (step 8b, before the warm cache whose populator pre-warms it) and by hand after editing the manifest. |
| `sccache/` | B1 of plan `ci-runner-cache-tiers` (`livespec-dev-tooling-ddiszt`): the shared Rust COMPILATION cache — a RAM-only redis (digest-pinned, `maxmemory 16gb` derived against the churn-slot cap, `allkeys-lru`, no persistence) that the pool-provided sccache binary (`install-sccache-binary.sh`, mounted read-only into every job at `/opt/ci-runner/bin`) reads from; unauthenticated = READ-ONLY by ACL, the populator the one writer with a host-held credential. The tier the console matrix's wall clock rides on. See `sccache/README.md`. |
| `sccache/converge-sccache-redis.sh` | The idempotent (root) converge of the compilation cache's cluster objects: writer credential, ACL Secret, the credential's projection into the populator's namespace, the redis Deployment + Service — called by the boot converge (step 8c) and by hand. |
| `sccache/install-sccache-binary.sh` | Node-local (root): the pinned, checksum-verified sccache binary under `/usr/local/lib/ci-runner-k3s/bin` — run by `install-node.sh` (7b), not by the boot converge. |
| `isolation/` | The build-cache tiers' NEGATIVE tests (v054 §"Runner-pool cache telemetry"; `livespec-dev-tooling-tqpszl`): `cache-negative-tests.sh` asserts from inside a routed job that the warm mount is unwritable, a redis SET with the pod's credentials is refused, no writer credential is present, and the crates proxy refuses writes — failing also when a precondition is missing. The timer and the report are `.github/workflows/ci-cache-negative-tests.yml` (every 6 h on the pool, conclusion exported to `github-ci`, trigger `CI cache negative tests failed`); `negative-control-job.yaml` is the deliberately misconfigured pod that proves the cases can go red. |
| `warm-cache/converge-warm-cache.sh` | The idempotent converge of the warm cache's CLUSTER objects (Namespace, CronJob, both ConfigMaps) with no populate Job — called by the boot converge (those objects are wiped with the tmpfs datastore; the CronJob was simply gone after the 2026-09-02 reboot) and by `install-warm-cache.sh`, which adds the attended initial populate. |
| `reconstruct/render-sa-kubeconfig.sh` | Renders a host-side kubeconfig from a ServiceAccount's populated token Secret (token never echoed). Used by the converge to re-render the Kueue-webhook probe's credential (`../../observability/kueue-webhook-probe-rbac.yaml`) on every boot, since the account it names is wiped with the datastore. |
| `node-keyring-budget/60-k3s-container-keyring.conf` + `install-keyring-sysctl.sh` | The per-user kernel keyring quota (`kernel.keys.maxkeys = 2000`, `maxbytes = 200000`) as a `/etc/sysctl.d/` drop-in. Every container start allocates a session keyring against uid 0 under containerd/runc; the kernel default of 200 was exhausted on this host on 2026-08-13 by two repositories' concurrency. The value had survived on the host only as an untracked drop-in under an earlier name; the 2026-09-02 gitops audit found it with no git source, and the installer now ships it under this name and removes the untracked predecessor. |
| `storage-layout/install-storage-layout.sh` | Ensures the FIVE `/etc/fstab` lines that define the node's storage layout — the three CI tiers found by filesystem LABEL (`ci-cache` at `/var/cache/ci-runner`, `ci-containerd` and `ci-workvols` mounted under it) and the two bind mounts putting containerd's store and the local-path PVC root on them — byte-exact and with no UUID argument, replacing a differing line for one of those mountpoints (fstab backed up first, `findmnt --verify` after); refuses unless each label resolves to exactly one device; installs the k3s drop-in below. Labels, not UUIDs, so the lines are identical on the array stand-in LVs and on the NVMe (livespec plan `ci-runner-pod-lifecycle-reliability`, `livespec-el5y`; see "Storage layout: media-neutral tier identity" below). Never formats, moves data, mounts, or restarts k3s. |
| `storage-layout/10-requires-storage-mounts.conf` | `k3s.service.d/` drop-in: `RequiresMountsFor=` both bind targets, so k3s refuses to start — loudly, every `After=k3s` oneshot failing by dependency — rather than silently running the pool's churn on `/` when a tier is missing. Kept by hand on the host from 2026-09-04's NVMe attempt; from git since `livespec-el5y`. |
| `datastore-tmpfs/20-requires-datastore-mount.conf` | `k3s.service.d/` drop-in installed by `install-datastore-tmpfs.sh` only: `RequiresMountsFor=` the tmpfs datastore mount, because since the 2026-09-04 array rebuild the directory underneath holds a stale backup restore, not a rollback copy. Changes the rollback steps — read its header. |
| `node-extended-resource/reapply-node-extended-resource.service` (boot ordering) | Since 2026-09-02 also `WantedBy=multi-user.target` and `Before=converge-ci-stack.service`: on a tmpfs-datastore boot the node object is new, so the churn-slot resource every queue is denominated in is applied before the queues, not up to a minute later by the timer's first tick. Since 2026-09-04 the converge states the same dependency from its side (`After=`/`Wants=`) and asserts the capacity itself at step 1b (`livespec-kgl3`). |
| `install-node.sh` | The ONE ordered runbook for the node-local half: runs every installer in this tree in dependency order with the right arguments (`sudo install-node.sh 64`), so a from-scratch rebuild is one command. Enables the boot units, never starts them, never restarts k3s. Lists what it deliberately leaves attended (credstore seeding, the OTel collector from its own repo, the initial warm-cache populate). |

## Reconstruct-on-boot: the CI cluster stack as cattle

`reconstruct/` makes the single-node k3s host **reconstructible** — the
precondition for its datastore being volatile (tmpfs, below). Before it,
the whole CI cluster stack lived ONLY in the k3s datastore, applied once by
hand (`../provision-k3s.sh` → `../install-arc.sh` → `../install-kueue.sh`,
plus the phase-2 per-repo scale sets and queues); nothing re-applied on
boot, so the host was a PET: wipe the datastore and the cluster is gone.
`reconstruct/` closes that gap with a boot-ordered `systemd` `oneshot`
(`converge-ci-stack.service`, `After=k3s.service`,
`After=`/`Wants=` `reapply-node-extended-resource.service` and
`After=`/`Wants=` `inject-github-app-secret.service`) that runs one
idempotent converge script.

**What it converges, in order** (`converge-ci-stack.sh`): wait for the API
(`/readyz`) and the node `Ready` → **the churn-slot capacity assertion**
(step 1b: every `k3s-role=arc-runner-host` node's allocatable
`ci-runner.io/churn-slot` must equal the capacity the installed
`reapply-node-extended-resource.service` carries in its `ExecStart`; a
missing or wrong value re-runs `patch-node-churn-capacity.sh` and
re-checks — see "After a dependency-failed boot" below) → fail-closed
pre-gate on the
`arc-github-app-installation` secret → the fleet-owned **local-path
provisioner** (`local-path-provisioner/`; the bundled copy is disabled by
`k3s-config/`) → **Kueue core** (the `kueue/core/` overlay: the `v0.19.1`
release manifest plus the fleet's HA patches — two replicas, probe timeouts,
leader-election tolerances; see "Kueue HA" below — as ONE server-side
kustomize apply, a rollout restart only when the manager's config actually
changed, then rollout + CRD-established wait) **and a wait for its mutating
webhook to have a ready endpoint** → `kueue/resource-flavor.yaml` and every
`kueue/cluster-queue-*.yaml` → ARC controller (`helm upgrade --install`,
chart `0.14.2`) → all eleven runner scale sets from `arc/values-*.yaml` (each
`helm upgrade --install`, chart `0.14.2`) → **the listener assertion**
(every `AutoscalingListener` must reference its scale set's CURRENT
`EphemeralRunnerSet`; a stale one is deleted so the controller recreates it,
then re-verified — see "Why 'N listeners Running' is not the proof" below)
→ the `arc-hook-pod-template`
ConfigMap (via `arc/converge-hook-pod-template.sh`) → the crates proxy
(`crates-proxy/converge-crates-proxy.sh`) → the sccache redis
(`sccache/converge-sccache-redis.sh`) → the warm cache's
cluster objects (`warm-cache/converge-warm-cache.sh`, no populate Job) →
the Kueue-webhook probe's RBAC re-applied and its host kubeconfig
re-rendered (`render-sa-kubeconfig.sh`). Every operation is a
`helm upgrade --install` or a `kubectl apply`, so a second run against an
already-converged cluster makes no disruptive change.

**Why that order.** The first real reboot (2026-09-02 12:14Z) ran ARC before
Kueue: ARC's controller was up at +10 s, Kueue's webhook had no endpoint
until +2m35s, and because `mpod.kb.io` has `failurePolicy: Fail` and
intercepts every pod outside `kube-system`/`kueue-system`, every
listener-pod create failed `no endpoints available for service
"kueue-webhook-service"` for ~80 s until ARC's own retry backoff recovered
it. Once that webhook configuration exists, NO pod can be created until its
server answers — so the server is brought up, and waited for, before
anything that creates pods. The provisioner comes first for the same
reason in the other direction: nothing can bind a PVC without it, and the
bundled copy that used to appear "for free" is now disabled.

**Why "N listeners Running" is not the proof, and step 7b.** ARC 0.14.2 can
create two `EphemeralRunnerSet`s for one scale set within seconds of the
helm apply — a transient one, then the live one — and a listener created in
that window captures the TRANSIENT name. Nothing corrects it: the
`AutoscalingListener` carries no ownerReference to the set and only patches
it when it must scale. So the listener pod shows `Running`, a "10 listeners
Running" checklist passes, and the FIRST job assigned to that repository
makes the listener fail `could not patch ephemeral runner set … not found`,
exit and crash-loop — that repository's jobs queue forever with every
capacity signal healthy. Boot 5 on 2026-09-02 lost that race for
`livespec-overseer` (31 minutes of queueing, found by a human; boots 2–4
simply did not lose it, which is why their passing checklists proved
nothing). The converge's step 7b therefore asserts, for every listener,
that `spec.ephemeralRunnerSetName` equals the CURRENT set of its scale set
(owned by that `AutoscalingRunnerSet`, not being deleted, newest by
creation time — a bare "the set exists" test would miss a superseded set
not yet deleted), polled and bounded to 150 s because listeners appear
asynchronously (~35 s after the helm applies on a boot from empty); a stale
listener is deleted at most once so the controller recreates it against the
live set (~30 s), and the check is re-run. The evidence line is
`listener->EphemeralRunnerSet: N/N consistent (M self-healed)` in the
converge's journal; a residual mismatch prints a `WARN` and the converge
CONTINUES (failing there would skip the hook ConfigMap, warm cache and probe
identity every job depends on, and `runner-pod-lifecycle/` reports the
class every five minutes as `stale-listener`). Item `livespec-bde2`.

*Proven on `poweredge-xubuntu`, 2026-09-03 (warm; the one-boot proof is
recorded with the next reboot).* Through the installed unit on a consistent
cluster: `listener->EphemeralRunnerSet: 10/10 consistent (0 self-healed)`,
`Result=success` in 41 s, nothing else changed. Then the race was
reproduced synthetically on the host's own single-runner scale set:
`kubectl patch autoscalinglistener poweredge-xubuntu-k3s-…-listener` to a
bogus `ephemeralRunnerSetName` — the patch PERSISTED (the controller does not
reconcile that field, which is exactly why the boot-5 race persisted) and
the controller restarted the listener pod against the bogus set, the
crash-loop shape. The next converge deleted the stale listener at
01:03:10Z, the controller recreated it with a new uid against the live set
at 01:03:11Z, and step 7b closed `10/10 consistent (1 self-healed)` three
seconds later with the listener pod Running.

**After a dependency-failed boot, a hand-started k3s revives nothing — and
step 1b.** On the 2026-09-04 06:31Z boot, stale NVMe lines in `/etc/fstab`
failed k3s's mount dependency, so EVERY `After=k3s.service` oneshot failed
by dependency in the same instant: `reapply-node-extended-resource`,
`inject-github-app-secret`, `converge-ci-stack`, `otel-collector-identity`,
`sweep-runner-scratch`. An operator then started k3s by hand and started
the converge by hand — but not the reapply unit. Its timer did not cover
the gap either: `OnBootSec=1min` had already fired into the failed
dependency, and `OnUnitActiveSec=5min` re-arms only from a SUCCESSFUL
activation, so with the boot activation failed the timer had NO next
elapse. The node carried no `ci-runner.io/churn-slot` allocatable at all
while the nine `ClusterQueue`s advertised a quota sum of 32: Kueue admits
against quota, the scheduler places against the node, so every admitted
runner pod would have been unschedulable, silently — no capacity signal
and no sweep class covered it — until a hand
`systemctl start reapply-node-extended-resource.service` at 07:52Z. Item
`livespec-kgl3`.

The lesson, as procedure: after ANY boot where a dependency failed, walk
`journalctl -b | grep 'Dependency failed for'` and `systemctl start` each
oneshot it lists — or reboot cleanly once the cause is fixed. Starting k3s
by hand revives none of them: a failed `oneshot` is not retried when its
dependency later comes up, and a unit you did not start stays failed. Three
mechanisms now make that walk a backstop rather than the only remedy:

- **The converge asserts the capacity itself (step 1b).** Right after the
  node reports `Ready`, before the provisioner, Kueue or any queue, it
  learns the intended capacity from the INSTALLED reapply unit's
  `ExecStart` argument (`systemctl show reapply-node-extended-resource.service
  -p ExecStart` — the one already-decided number on the host, so the
  converge decides no number of its own and no second copy exists to
  drift; `CONVERGE_CHURN_CAPACITY` overrides it outside the installed
  layout), compares every `k3s-role=arc-runner-host` node's allocatable to
  it, and on a mismatch or absence re-runs
  `patch-node-churn-capacity.sh <capacity>` (idempotent; the unit's own
  `ExecStart` target) and re-checks. The evidence line is
  `churn-slot capacity: N/N node(s) at C (M self-healed)`. A node still
  wrong afterwards is a `WARN` and the converge CONTINUES — the step-7b
  rule, binding harder here: failing at 1b would skip the whole cluster
  stack, so when the timer or an operator did restore the capacity there
  would be nothing for it to serve, whereas continuing leaves a fully
  built stack that admits and schedules the instant the capacity lands.
- **The converge unit `Wants=` the reapply unit.** The reapply already
  ordered itself `Before=` the converge; the converge now states
  `After=`/`Wants=` from its side (exactly as for the secret unit), so a
  HAND-STARTED converge pulls the reapply in as well. `Wants`, not
  `Requires`: if the reapply fails, the converge still runs and step 1b
  heals the capacity itself.
- **The reapply timer fires on the wall clock.** `OnCalendar=*:0/5` sits
  beside `OnBootSec`/`OnUnitActiveSec`, so the service is triggered every
  five minutes regardless of whether any previous activation succeeded; it
  also makes `Persistent=true` effective (that setting applies to
  `OnCalendar` timers only). A run may land twice in one five-minute span
  when the two periodic triggers drift apart — one idempotent
  `kubectl patch`, accepted.

And the condition is now a reading: `runner-pod-lifecycle/` reports
`capacity-absent` every five minutes when any selected node lacks the
resource or the nodes' allocatable total is below the queues' quota sum
(see "Runner-pod lifecycle stall" below).

**Starting from an EMPTY datastore** (the GitHub App secret re-injected by
`../secret-reinjection/`), one boot converges the cluster to every scale-set
listener `Running` AND referencing its scale set's current
`EphemeralRunnerSet` (the `listener->EphemeralRunnerSet: 10/10 consistent`
line above is the evidence — a `Running` count alone is not) and Kueue
admitting pods, with zero manual `kubectl`/`helm` steps — proven by the
2026-09-02 reboots (see "Datastore on tmpfs" below).

**Scope boundary.** The converge owns CLUSTER-side state (everything that
lives in the datastore) plus the one host file derived from it (the probe
kubeconfig). It does NOT own the NODE-LOCAL machinery — the AppArmor profile
(`apparmor/`), the inotify sysctl budget (`node-inotify-budget/`), the
churn-slot extended resource (`node-extended-resource/` — step 1b ASSERTS it
is present at the reapply unit's capacity and re-runs the patch when not,
but the number stays that unit's), the k3s server
config (`k3s-config/`), the orphaned-scratch sweep (`storage-sweep/`), and
the host OTel collector's own cluster identity (the `otel-collector`
repository's `otel-collector-identity.service`, the same boot-time
re-render pattern for the same reason) — each of which has its own
installer and its own boot-durability (a `/etc/apparmor.d` file, a
`/etc/sysctl.d` drop-in, a reapply timer, a config file, a `Before=k3s`
unit). `install-node.sh` runs those installers in order. The converge also
decides NO numbers: scale-set ceilings live in `arc/values-*.yaml`, queue
quotas in `kueue/cluster-queue-*.yaml`, the provisioner tuning in
`local-path-provisioner/local-path-provisioner.yaml`; the converge only makes
those already-decided artifacts durable. And it never creates the GitHub App
secret — it fail-closes if the secret is absent (`../secret-reinjection/`
owns re-injection).

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

## Kueue HA: two replicas and leader-election tolerances

`kueue/core/` makes the Kueue admission webhook survive a control-plane
latency spike. It is the fix for the failure class recorded in the livespec
plan `ci-runner-pod-lifecycle-reliability` research/003 (item
`livespec-okxbkg`), and it ships regardless of the datastore's location.

**The failure class.** On 2026-09-01, with 60+ concurrent CI jobs on the
RAID that then also held the k3s datastore, the API server's writes stalled
(`Slow SQL` bursts of ~2 s at 14:52:27–28Z and ~10 s at 14:58:00–09Z). Kueue's
single controller-manager could not renew its leader lease inside the default
10 s `renewDeadline`, lost the election and **exited by design** (14:57:45Z).
Because that one pod was also the only backend of `kueue-webhook-service`,
the pod-mutating webhook `mpod.kb.io` — `failurePolicy: Fail`, intercepting
every pod outside `kube-system`/`kueue-system` — had no endpoint: the API
server logged 27 webhook failures and ARC jobs died at `Initialize
containers` with `failed calling webhook "mpod.kb.io"`. A control-plane
hiccup became a fleet-wide admission outage.

**Two halves, two patches.** Both live in `kueue/core/` as strategic-merge
patches over the upstream release manifest, and each file's header carries
the full argument:

| Object | Field | Upstream | Fleet | Why |
|---|---|---|---|---|
| `Deployment/kueue-controller-manager` | `spec.replicas` | 1 | **2** | controller-runtime serves the admission webhook from EVERY replica; only the leader runs the reconcilers. Two pods behind the webhook Service means losing one (lease loss, eviction, rolling restart) leaves the webhook answering. |
| same | liveness + readiness `timeoutSeconds` | 1 | **5** | Three missed 1 s readiness deadlines drop a pod from the webhook's READY endpoints — under exactly the latency this exists to survive, both replicas could be marked unready at once. Periods and thresholds are unchanged, so a dead pod is still replaced. |
| `ConfigMap/kueue-manager-config` | `leaderElection.leaseDuration` / `renewDeadline` / `retryPeriod` | 15s / 10s / 2s (defaults; upstream sets neither) | **60s / 45s / 5s** | `renewDeadline` 45 s is 4.5× the longest measured stall and well past the 10 s that was crossed; `leaseDuration` must exceed it and bounds how long *reconciliation* pauses after a true leader death; the webhook does not depend on the lease at all. |

Two replicas, not three: leader election is a Lease, not a quorum, so a third
adds nothing on one node. Upstream's `RollingUpdate 25%/25%` at two replicas
rounds to `maxUnavailable 0 / maxSurge 1`, so even a rollout brings a new pod
up before an old one goes.

**What it deliberately does NOT do.** It adds no throughput (Kueue's
admission rate is the leader's alone) and fixes no datastore — the stall's
*cause* was removed by moving the datastore to tmpfs ("Datastore on tmpfs"
below); this is symptom resilience against any future latency spike. And the
webhook's `failurePolicy` stays `Fail`: `Ignore` was REJECTED in the plan's
scope amendment, because a pod that bypasses the webhook bypasses churn-slot
gating, which is the physical cap the whole admission formula rests on.

**How it stays durable — and why it is an overlay.** The upstream manifest
carries `replicas: 1`, the 1 s timeouts and no durations, and
`reconstruct/converge-ci-stack.sh` step 4 re-applies Kueue core on every boot
(the datastore is empty). Patching *after* that apply would be undone by the
next converge — and on a warm converge the two applies would flip the
ConfigMap back and forth, restarting the manager every run. So the converge
applies `kueue/core/` as ONE `kubectl apply --server-side -k`: upstream plus
patches, merged, a single object set. It asserts the overlay's pinned release
URL agrees with its own `KUEUE_VERSION` (the two are bumped together, with
`install-kueue.sh` and "Pinned versions"), and it restarts the manager ONLY
when the ConfigMap's *content* changed across the apply — never on a boot
from empty (the Deployment is created against the new ConfigMap already) and
never on an unchanged warm run, which stays a no-op.

**Verification.** The acceptance is observable on the cluster, not inferred
from a green apply: `kubectl -n kueue-system get deploy kueue-controller-manager`
shows `2/2`; the `kueue-webhook-service` EndpointSlice lists BOTH pod
addresses ready; deleting the pod that holds the `c1f6bfd2.kueue.x-k8s.io`
Lease and immediately creating a pod in `arc-runners` carrying the
`kueue.x-k8s.io/queue-name` label still yields the mutated shape (the
`kueue.x-k8s.io/admission` scheduling gate and `kueue.x-k8s.io/managed`
label) with zero `mpod.kb.io` failures in the k3s journal; and the running
manager's config shows the three durations. The existing
`ci-kueue-webhook-probe` gauge (`livespec.ci_kueue.webhook_ready_endpoints`)
now reads 2 in the healthy state — its alarm condition (`< 1`) is unchanged.

**Proven live on `poweredge-xubuntu`, 2026-09-02.** A server-side `kubectl
diff` of the overlay against the cluster showed exactly six deltas —
`replicas 1 → 2`, both probe `timeoutSeconds 1 → 5`, and the three durations
added — and nothing else (an earlier draft of the ConfigMap patch had been
truncated and would have dropped `- "pod"` from `integrations.frameworks`,
i.e. the pod gating itself; the diff is what caught it, and the patch body is
now generated verbatim from upstream plus the five inserted lines). The live
apply at 17:59:59Z rolled to `2/2` in 34 s with the old pod retired only
after both new ones were Ready; the webhook EndpointSlice listed both
addresses; the `c1f6bfd2.kueue.x-k8s.io` Lease showed `leaseDurationSeconds:
60`; both managers logged `Configuration loaded` with `leaseDuration: 1m0s /
renewDeadline: 45s / retryPeriod: 5s`; and the k3s journal carried zero
`mpod.kb.io` failures and zero `no endpoints available` errors across the
rollout. Leader-kill test at 18:03:06Z: the lease-holding pod was deleted and,
in the same second, a pod carrying `kueue.x-k8s.io/queue-name:
livespec-dev-tooling-lq` was created in `arc-runners` — it came back from the
API server already mutated (`kueue.x-k8s.io/managed=true`, the `admission` and
`topology` scheduling gates, a Workload object) and was admitted 3 s later;
the surviving replica was the sole ready endpoint; the lease transferred to it
in **2 s**; the Deployment was back to `2/2` at +13 s; zero webhook failures
in the window. (Both managers also log a `Stopping and waiting for … runnables`
sequence seconds after start — that is Kueue's certificate-bootstrap manager
shutting down before the real manager starts, not a crash; restarts stay 0.)
Durability and the no-op property, 18:04Z: `install-converge-unit.sh` was
re-run from this tree and `systemctl start converge-ci-stack.service` — the
installed copy, the same path a boot takes — completed `Result=success` in
59 s; step 4 server-side-applied the overlay's 79 objects with no
`kueue-manager-config changed` line, and both Kueue pods were identical
before and after (same names, same container start times): the overlay is
what the boot path applies, and a warm converge restarts nothing.

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

The mount unit is ordered `Before=k3s.service`, and since 2026-09-04 k3s
**requires** it: `datastore-tmpfs/20-requires-datastore-mount.conf`, a
`k3s.service.d/` drop-in that `install-datastore-tmpfs.sh` installs,
carries `RequiresMountsFor=/var/lib/rancher/k3s/server/db`. Before that,
k3s was deliberately not made to require the mount, so a failed tmpfs
mount meant k3s started on the on-disk datastore underneath — "stale but
intact" while that copy was the pre-cutover rollback. The 2026-09-04
array rebuild replaced it with a 2026-08-27 backup restore, and a k3s
that started on it would run an old cluster state against live
containers. Failing loud is the honest outcome: k3s does not start, every
`After=k3s` oneshot fails by dependency, `systemctl --failed` is red. The
`.mount` is still `WantedBy=` (not `RequiredBy=`) `multi-user.target`, so
the machine itself boots; only k3s waits (`livespec-el5y`).

None of this can brick the host. The tmpfs holds only the ~110 MB
datastore; the OS, the RAID array, the beads ledger, and every durable
file are untouched. A bug in the converge script degrades to "the CI
cluster comes up empty or wrong until someone re-runs the (fixed)
converge" — the converge only ever runs `helm upgrade --install` and
`kubectl apply`, so it creates and updates and never deletes host state.
And because the tmpfs is mounted **over** the on-disk directory (hiding
the disk copy, not deleting it), **rollback** is: stop k3s,
`systemctl disable --now var-lib-rancher-k3s-server-db.mount`, remove
`/etc/systemd/system/k3s.service.d/20-requires-datastore-mount.conf` and
`systemctl daemon-reload`, start k3s — on whatever the on-disk directory
last held (since the 2026-09-04 rebuild, the stale restore; retiring it is
a pending maintainer decision on `livespec-ifwnqj`).

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

**The full host reboot PASSED on `poweredge-xubuntu`, 2026-09-02 12:14Z**
(agent-performed over ssh, maintainer-delegated), unattended from boot with
no manual unit starts: host booted 12:17:19Z; k3s up on a fresh EMPTY tmpfs
at +33 s; `inject-github-app-secret.service` rebuilt the secret with 3 keys
in 1 s; `converge-ci-stack.service` ran 2m39s to `Result=success`; node
`Ready`, ARC controller 1/1, 10 scale sets, 10 ClusterQueues, 10
LocalQueues, 2 ResourceFlavors, the hook ConfigMap, Kueue 1/1; all ten
listeners `Running` at +4m20s with zero auth failures; inotify 8192,
allocatable pods 200, churn-slot 64 all held. The pre-cutover on-disk
`state.db` (79.8 MB + 85 MB WAL) is intact under the mount as rollback
insurance. That boot ALSO found what this directory now fixes — the things
that were in the datastore or derived from it and came back wrong or not at
all: the provisioner tuning (reverted to the bundled defaults →
`local-path-provisioner/` + `k3s-config/`), the ARC-before-Kueue ordering
(→ the converge order above), the warm-cache CronJob (gone →
`warm-cache/converge-warm-cache.sh` in the converge), the Kueue-webhook
probe's ServiceAccount (gone, probe failing every 5 min →
`render-sa-kubeconfig.sh` in the converge), the host OTel collector's
ServiceAccount (gone, collector crash-looping → its own repo's
`otel-collector-identity.service`), and every PVC directory orphaned by
design (→ `storage-sweep/`).

### What this does NOT do

It does not own the reconstruct units (they have their own installers and
this README's "Reconstruct-on-boot" section), it does not touch the
node-local machinery (AppArmor, inotify, churn-slot, k3s config, the sweep),
and it does not move the bulk CI churn off the array — that is the NVMe
tiering (`livespec-e2vcqf`), a separate, hardware-gated piece. Nor does it
move anything precious: the beads/Dolt ledger and backups stay on the
redundant RAID and must never go on tmpfs.

## Storage sweep: the tmpfs boot orphans every PVC directory, on purpose

Every runner's `work` volume is a `local-path` PVC — a directory under
`/var/lib/rancher/k3s/storage` (an fstab bind mount of the `ci-workvols`
tier). The provisioner deletes that
directory only when it deletes a PV it can still see. Two things break
that: under pod churn it leaks directories whose claims vanished before it
got to them (research/001 of the livespec plan counted 76 such stale claims
in 20 minutes), and on every tmpfs boot the datastore is EMPTY, so every
directory that existed at reboot has no PV and never will (2026-09-02:
~150 orphans, ~50 GB, on an array that is latency-bound at its
cold-random-write ceiling).

`storage-sweep/sweep-runner-scratch.service` runs `Before=k3s.service` and
removes every `pvc-*` directory there — and keeps everything else, which
since `livespec-lvtu` includes `.warm`, the warm uv cache lower that lives
beside them (`warm-cache/`) and must survive a boot. It is safe under exactly two
conditions, and both are enforced rather than assumed: **(1)** every PVC on
this pool is a 5 Gi ephemeral runner work volume — nothing precious is ever
placed here; **(2)** the datastore is empty when it runs, so no PV can
reference anything — the unit's `ConditionPathExists=!.../state.db` skips
it on any boot where the tmpfs mount is absent (since 2026-09-04 k3s does
not start at all in that case — `20-requires-datastore-mount.conf` — so the
condition is a second guard, not the only one), and the script refuses under a running k3s and across
any mount point below the root. Condition (1) is a property of the pool,
not of the mechanism: **before placing any non-ephemeral PVC on this node,
disable this unit first.**

## Storage layout: media-neutral tier identity

Three CI tiers live on dedicated volumes, and two bind mounts put
containerd's store and the local-path PVC root on them. Every path in
this table is fixed; only the medium behind a label ever changes.

| Tier | Label = LV name | Mounted at | Bound onto | Holds |
|---|---|---|---|---|
| tier root | `ci-cache` | `/var/cache/ci-runner` | — | the crates proxy's store (`crates-proxy/`) and the two tier mountpoints below — the warm uv cache left it under `livespec-lvtu` |
| containerd store | `ci-containerd` | `/var/cache/ci-runner/k3s-containerd` | `/var/lib/rancher/k3s/agent/containerd` | image layers, snapshots, container root filesystems |
| runner work volumes | `ci-workvols` | `/var/cache/ci-runner/k3s-storage` | `/var/lib/rancher/k3s/storage` | every runner's `local-path` PVC scratch, and beside them the warm uv cache lower (`.warm`, `warm-cache/`) each volume is hardlink-seeded from — one filesystem by necessity, since a hardlink crosses neither a filesystem nor a mount |

`storage-layout/install-storage-layout.sh` ensures the five `/etc/fstab`
lines that say exactly this (its header lists them byte-for-byte) and the
k3s drop-in that makes k3s refuse to start unless both binds are mounted.

### Why labels, and the 16-byte rule

The tiers are moving media. On 2026-09-04 they are three 1 TiB LVs in
VG `poweredge` on the rebuilt 7-drive RAID-5; when the NVMe hardware lands
(livespec plan `poweredge-raid-array-maintenance`, `livespec-e2vcqf`) the
containerd store and the work volumes each move to an LV of the **same
name** in one VG per NVMe drive; the warm uv cache moves WITH the work
volumes (it lives on `ci-workvols` so it can be hardlinked into them), and
only the tier root stays on the array. A
filesystem UUID is minted by every `mkfs`, so a UUID-keyed fstab has to
change on every move, and the git copy of the layout can never be
byte-identical to the host's — which is exactly how the layout drifted out
of git in the first place (the host's tier lines had no source until
`livespec-el5y`). A label is chosen by us and is the same on any medium.
The maintainer's rule (2026-09-04) is that the array uses the SAME volume
names as the NVMe will, so nothing but the data copy and a performance
comparison needs the hardware; labels are that rule in fstab terms, and
the LV names repeat them so `lvs` and `findmnt` tell the same story.

An ext4 label holds **16 bytes**. The stand-in names this replaced had
already tripped over it: the LV `standin-containerd` carried the label
`standin-containe`, silently truncated. `ci-containerd` (13), `ci-workvols`
(11) and `ci-cache` (8) fit; keep any future role name under 16.

### The k3s drop-ins: fail loud, never silently on `/`

Every path above exists whether or not its volume is mounted, so a k3s
that starts with a tier missing runs the whole pool's churn on the root
filesystem, silently, until `/` fills — the failure the 2026-08-28
relocation was done to prevent. Two `k3s.service.d/` drop-ins make that
impossible: `storage-layout/10-requires-storage-mounts.conf` requires both
bind targets, and `datastore-tmpfs/20-requires-datastore-mount.conf`
(installed only where the datastore is volatile) requires the tmpfs
datastore mount. A missing tier then means k3s does not start, every
`After=k3s` oneshot fails by dependency, and `systemctl --failed` is red —
which is what the 2026-09-04 boot with stale NVMe fstab lines looked like,
and why it was caught. The bind lines also `x-systemd.requires-mounts-for=`
their own **source** mount, not merely the cache volume, so systemd cannot
bind an empty mountpoint directory before the tier volume lands on it.

### Moving a tier to new media

The procedure that keeps fstab unchanged and the installer a no-op
throughout (`ci-containerd` shown; `ci-workvols` is identical):

1. Create the volume on the new medium with the role's LV name in that
   medium's VG (`lvcreate -n ci-containerd -L <size> <vg>`), then format it
   with a **temporary** label: `mkfs.ext4 -L new-containerd <device>`
   (`new-` + role, still under 16 bytes). Two devices must never carry the
   role label at once; the installer refuses to run while they do.
2. Mount it somewhere temporary and copy: `rsync -aHAXS --numeric-ids
   --delete /var/cache/ci-runner/k3s-containerd/ <tmp>/`. Repeat the rsync
   just before the switch; the second pass should report no differences.
3. In a quiet window (0 workflow pods, every scale set at 0 runners):
   `systemctl stop k3s` (the bind mounts stay mounted — `k3s-killall.sh`
   does not unmount them), `umount /var/lib/rancher/k3s/agent/containerd`,
   `umount /var/cache/ci-runner/k3s-containerd`, then swap the labels so
   only the new volume carries the role: `tune2fs -L old-containerd
   <old device>` and `tune2fs -L ci-containerd <new device>`, then
   `mount -a`. `findmnt` must show the new device at both paths.
   `systemctl start k3s`. **Never `udevadm trigger` a mounted device-mapper
   volume** to refresh `/dev/disk/by-label`: on 2026-09-04 that marked the
   dm devices not-ready, systemd stopped all four tier mounts, and the
   `RequiresMountsFor` drop-in stopped k3s ahead of them (shims orphaned,
   every listener `Unknown`). `blkid` reads the new label directly,
   `mount -a` resolves `LABEL=` through it, and `lvchange --refresh` or the
   next boot refreshes the symlinks (livespec plan
   `poweredge-raid-array-maintenance`, research note
   `nvme-pex8747-gen3-link-fault.md`, gotcha 3).
4. Run `install-storage-layout.sh`: it reports every line `present` and
   the drop-in byte-identical. The old volume keeps the data under
   `old-containerd` until it is reclaimed.

Renaming a tier **in place** (what 2026-09-04 did to the stand-in LVs) is
step 3's label change alone, on a live mounted filesystem: `lvrename` and
`tune2fs -L` are both safe while mounted, fstab found the volumes by UUID
until the installer rewrote the lines by label, and the same `udevadm`
rule applies.

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
exactly; at `C = 64` (the increase-ci-runners raise, 2026-08-30) it gave
`livespec` 10, `livespec-driver-codex` 9, `livespec-driver-claude` 9, four
mid-band repos 8, `livespec-console-beads-fabro` 2, and `livespec-driver-pi`
2 — summing to exactly 64; and at the current INTERIM `C = 32` (2026-09-02,
until `livespec-e2vcqf` lands) it gives `livespec` 5, `livespec-driver-codex`
5, five mid-band repos 4, `livespec-console-beads-fabro` 1, and
`livespec-driver-pi` 1 — summing to exactly 32. The doubling
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
`values-<repo>.yaml` — four names diverge, all for reasons recorded in
the files themselves:

| Live release | Values file |
|---|---|
| `livespec-local-ci-k3s` | `arc/values-livespec.yaml` |
| `livespec-console-beads-k3s` | `arc/values-livespec-console-beads-fabro.yaml` |
| `livespec-orchestrator-git-k3s` | `arc/values-livespec-orchestrator-git-jsonl.yaml` |
| `livespec-orchestrator-k3s` | `arc/values-livespec-orchestrator-beads-fabro.yaml` |
| `livespec-dev-tooling-k3s` | `arc/values-livespec-dev-tooling.yaml` |
| `livespec-driver-claude-k3s` | `arc/values-livespec-driver-claude.yaml` |
| `livespec-driver-codex-k3s` | `arc/values-livespec-driver-codex.yaml` |
| `livespec-driver-pi-k3s` | `arc/values-livespec-driver-pi.yaml` |
| `livespec-overseer-k3s` | `arc/values-livespec-overseer.yaml` |
| `livespec-runtime-k3s` | `arc/values-livespec-runtime.yaml` |
| `poweredge-xubuntu-k3s` | `arc/values-poweredge-xubuntu-k3s.yaml` |

(A twelfth row, `local-ci-k3s` → `arc/values-local-ci-k3s.yaml`, was
retired under `livespec-s43svm.28`.)

The first three diverge because a scale-set name must stay <=30 characters
(see the naming rule above) while a values file is named for the repo it
serves; the fourth for the same reason.

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

All ten fleet repositories already have both files (the ninth,
`livespec-driver-pi`, joined 2026-08-20; the tenth,
`livespec-orchestrator-beads-fabro`, 2026-09-04). These steps are for
the NEXT repository joining the pool.

1. Establish the new repository's demand weight `w` by measuring its
   actual GitHub Actions matrix job count. Never guess. (Before the podman
   pool was decommissioned this step also allowed reading that repository's
   `ci-runner-supervisor.service` `--slots` value; that pool and its
   documentation are gone, so measurement is the only source.)
2. Add it to `kueue/DERIVATION.md`'s weight table and RE-DERIVE every
   repository's `nominalQuota` at the current capacity `C` — adding a
   repository changes the weight sum, so every existing quota moves.
   Follow that file's "Recomputing at another C" steps; the quotas must still
   sum to exactly `C`.
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

### The detector: `runner-pod-lifecycle/`

Those two commands are now run for you, widened to the whole family, every
five minutes: `runner-pod-lifecycle/scan-runner-pod-lifecycle.sh` (installed
by `install-runner-pod-lifecycle-scan.sh`, driven by the `.timer`) is the
second gate beside the wedge sweep — the wedge scan answers "is a runner
dead to GitHub?", this one answers "is the host failing to bring pods up?".
It reports seven classes, each read from the node-side observable that
persists long enough for a sweep to see it (the ARC hook string itself is
written by a runner that exits moments later, so it is a bonus, not the
signal):

| Class | Read from | Fires when |
|---|---|---|
| `pvc-pending` | PVCs in `arc-runners` | any Pending longer than 120 s (the provisioner's own helper-pod ceiling) |
| `bind-deadline` | k3s journal, last 5 min | any `binding volumes: context deadline exceeded` |
| `inotify-emfile` | `containerd.log`, last 5 min (walked backwards to the cutoff — the file rotates) | any `failed to create inotify fd` |
| `containerd-deadline` | pod container states now; `arc-runners` events, last 5 min | a container in `StartError`; a `Failed`/`FailedCreatePodSandBox` event carrying `context deadline exceeded` or `failed to create shim task`; or ≥ 20 `FailedKillPod` (teardown starvation, the 2026-09-02 17:55Z shape — calibrated live: 7–14 per window while the backlog tail drained with nothing failing, 25–27 beside a PVC Pending 209 s, ~80 at the StartError) |
| `hook-failure` | runner-pod logs, last 5 min; Pending `-workflow` pods | the hook's `Executing the custom container implementation failed`; or a workflow pod Pending longer than 480 s (the hook gives up at ~13 min) |
| `stale-listener` | `arc-systems` listener pods; `AutoscalingListener.spec.ephemeralRunnerSetName` vs existing `EphemeralRunnerSet`s | a listener not Running or waiting in a crash loop; or a reference to a set that does not exist (the ARC 0.14.2 boot race that queued `livespec-overseer` for 31 min on 2026-09-02; converge-side fix `livespec-bde2`) |
| `capacity-absent` | `k3s-role=arc-runner-host` nodes' `status.allocatable`; every `ClusterQueue`'s `nominalQuota` for `ci-runner.io/churn-slot` | a selected node without the resource; or the nodes' allocatable total below the queues' quota sum (2026-09-04: a dependency-failed boot left the reapply unit unrun and the node at none against a quota sum of 32 from 06:31Z to 07:52Z; converge assertion + timer fallback `livespec-kgl3`) |

Exit 1 names every present class with its count and prints the per-class
detail (which PVC, which pod, which event) followed by where each class is
worked; exit 0 is a clean node; exit 2 means the scan could not read one of
its inputs (journal, `containerd.log`, the API server) and refused to report
a clean node it had not looked at. Report-only, with no `--clear`: nothing
here is safe to delete automatically, and the two safe remedies
(`stale-listener` → delete the `AutoscalingListener`; the controller
recreates it; `capacity-absent` → `systemctl start
reapply-node-extended-resource.service`, which the converge and the reapply
timer also drive) are actions the report names for an operator.
Consecutive sweeps with findings are counted (`/var/lib/ci-runner-k3s/
runner-pod-lifecycle-streak`) and an `ESCALATION` line appears from the
second, as in the wedge sweep. Thresholds are flags/env
(`--window`, `--pvc-pending-seconds`, `--workflow-pending-seconds`,
`--killpod-min`, `--containerd-log` for a fixture, `--state-file`,
`--node-selector`).

**Proven live on `poweredge-xubuntu`, 2026-09-02, during a real stall.**
Run by hand at ~18:2xZ while the earlier release waves' teardown backlog was
still starving containerd (`sda` 87–93 % busy under two running jobs): exit
1 with `pvc-pending=5` (five PVCs Pending > 120 s) and
`containerd-deadline=26`; a minute later `pvc-pending=1`
(`…-runner-52xz9-work`, 209 s) and `containerd-deadline=27` (27
`FailedKillPod` in 5 min) with the `ESCALATION` line on the second
consecutive finding. A synthetic `failed to create inotify fd` line with a
fresh timestamp, fed through `--containerd-log`, was counted as
`inotify-emfile=1`; a missing log path exited 2 (`FATAL: cannot read …`);
with every threshold raised out of reach the same node took the `CLEAN`
exit-0 path. The first draft aborted with status 141 on the real 33 MB
`containerd.log` — `awk`'s early exit closes the pipe under `tac`, which
dies of SIGPIPE, and `pipefail` turned the bounded read into a crash — fixed
by absorbing `tac`'s status; the one-line fixture had hidden it. Installed
by `install-runner-pod-lifecycle-scan.sh` at 18:20Z: timer active and
enabled, first sweep immediate, journal carrying
`containerd-deadline=25` with the PVC already bound — the five-minute
window tiling as designed.

#### What every sweep emits to Honeycomb (`livespec-vwzv`)

The classes above were, until 2026-09-04, a journal-only reading. The
maintainer's directive that day: the churn-slot cap `C`
(`kueue/DERIVATION.md` calls it "a measured ceiling, not a free parameter")
and the CI routing are to be re-derived from MEASURED Honeycomb data, so
every signal that derivation needs is captured beside what the host
collector already exports (the `system.disk.*` rows per device, the
`system.filesystem.*` rows per tier mountpoint, `k8s.pod.phase` per pod,
and the heartbeat's `livespec.ci_listeners.active` /
`livespec.ci_runners.active`). So the sweep now ends with ONE OTLP/HTTP
metrics POST to the host collector (`http://127.0.0.1:4319/v1/metrics` —
the heartbeat's endpoint, JSON shape and `curl` flags), which the collector
exports to the `livespec` environment's `metrics` dataset. That environment
is a Honeycomb Metrics 2.0 environment with ONE metrics dataset, so rows
are told apart by metric name and resource attributes, never by dataset:

| Resource attribute / scope | Value |
|---|---|
| `service.name` | `ci-runner-lifecycle` |
| `host.name` | `$(hostname)` — `poweredge-xubuntu`; the collector's `resourcedetection` (`override: false`) keeps it |
| instrumentation scope name | `runner-pod-lifecycle` |

| Gauge | Value | Read from |
|---|---|---|
| `livespec.ci_lifecycle.<class>` — one gauge per class, class name verbatim: `pvc-pending`, `bind-deadline`, `inotify-emfile`, `containerd-deadline`, `hook-failure`, `stale-listener`, `capacity-absent` | the count the report carries for that class. **Always emitted, 0 when clean** — an absent metric is indistinguishable from a broken emitter | the sweep's own findings |
| `livespec.ci_kueue.pending` | Kueue workloads waiting for admission | `ClusterQueue.status.pendingWorkloads`, summed over every ClusterQueue that covers `ci-runner.io/churn-slot` — the pool's nine queues; `phase1-proof-cq` covers `cpu`/`memory` only and is excluded |
| `livespec.ci_kueue.admitted` | Kueue workloads admitted and not yet finished | `ClusterQueue.status.admittedWorkloads`, the same sum |
| `livespec.ci_churn_slot.quota_sum` | `C` as the queues have it — the cohort's guaranteed churn-slot total | the sum of `nominalQuota` for `ci-runner.io/churn-slot` over the same queues; 32 at the 2026-09-02 interim |
| `livespec.ci_churn_slot.allocatable` | `C` as the scheduler has it | `Node.status.allocatable["ci-runner.io/churn-slot"]` summed over the nodes (one node today); 0 when the extended resource is not registered, which IS a reading — the capacity is absent |

Why ClusterQueue status rather than `kubectl get workloads -A`: one list
call yields pending, admitted AND the quota sum, and the per-queue counters
are the ones Kueue's own admission loop maintains; a workloads listing would
have to be classified item by item on its `QuotaReserved` / `Admitted`
conditions to reach the same numbers.

**Best-effort, by contract.** The report and the exit code are the
interface the journal and `systemctl is-failed` depend on, so a collector
outage must not turn a clean node into a failed unit or mask a stall: a
`curl` failure is logged (`emit: POST to … FAILED`, with the values that
were not posted) and absorbed, and the call site is guarded so that even a
bug in the emitter cannot change the exit code. One fail-closed split is
kept: the class gauges come from variables the sweep already computed and
are always sent; the Kueue and node gauges need two extra reads, and when a
read FAILS those gauges are OMITTED (and the failure logged) rather than
sent as false zeros — the heartbeat's split between "0" and "could not
read". No trigger pairs with these gauges: like the heartbeat's
`io_stall_pct` pair they are decision inputs, not alarms.

Knobs: `--no-emit` (or `RPL_NO_EMIT=1`) skips the POST entirely — for a
hand run on a node whose collector you do not want to feed, or a fixture run
off the host; `--otlp-endpoint URL`, `RPL_OTLP_ENDPOINT`, or the heartbeat
family's host-wide `CI_RUNNER_HEARTBEAT_OTLP` override the endpoint, in that
order of precedence. The service, timer and installer are unchanged: the
unit already runs as root with the cluster kubeconfig, `curl` is already on
the host for the heartbeat, and the default endpoint is loopback.

**Joining the disk rows to the cache tiers.** The collector's
`system.disk.*` rows (`operations`, `weighted_io_time`, `io`, every 30 s)
carry `device` = `sda` / `dm-N`. `dm-N` numbering is host- and boot-specific
(LVM activation order), so never hard-code it. The `system.filesystem.*`
rows carry BOTH `device` (`/dev/dm-N`) and `mountpoint`, so join through
the mountpoint: query `system.filesystem.usage` grouped by `device` and
`mountpoint` over the window of interest, strip `/dev/`, and filter the disk
rows on that `device`. The tiers, with the mapping the live host carried on
2026-09-04 (re-derive it for every window you query):

| Tier | Mountpoint | `device` on 2026-09-04 |
|---|---|---|
| ci-cache | `/var/cache/ci-runner` | `dm-2` |
| ci-containerd | `/var/cache/ci-runner/k3s-containerd` | `dm-3` |
| ci-workvols | `/var/cache/ci-runner/k3s-storage` | `dm-4` |
| the whole array | (`sda2` is the LVM physical volume under every tier) | `sda` |

**The retrospective query recipe** — three queries on the `metrics`
dataset, every one filtered to `host.name = poweredge-xubuntu`, granularity
300 s (the sweep's and the heartbeat's cadence; the collector scrapes every
30 s), lined up on one time axis:

1. **Concurrency** — `COUNT_DISTINCT(k8s.pod.name)` WHERE
   `k8s.namespace.name = arc-runners` AND `k8s.pod.name ends-with -workflow`
   AND `k8s.pod.phase = 2` (2 is Running in the k8s_cluster receiver's
   encoding). Workflow pods, not runner pods, because the workflow pod is
   where the job's containers actually run (see "The workflow pod is not the
   runner pod" above). Proven 2026-09-04: 12–35 concurrent across a 6 h
   window.
2. **Array queue time per operation** — two named calculations,
   `wt = SUM(system.disk.weighted_io_time)` and
   `ops = SUM(system.disk.operations)`, both WHERE `device = sda`, and the
   query-math formula `$wt / $ops`. Both metrics are cumulative monotonic
   sums, so Honeycomb applies `INCREASE` per step before the `SUM`, and the
   ratio is the mean seconds an operation spent queued in that step.
   `RATE_SUM`, `RATE_AVG` and `RATE_MAX` are NOT allowed on a metrics
   dataset; for a per-second rate use a calculated field
   `RATE($system.disk.operations)` and aggregate that. Proven 2026-09-04:
   about 0.01 s per operation idle, 0.04 at the window's peak. Repeat per
   tier with `device = dm-N` from the join above.
3. **The lifecycle gauges** — `MAX(livespec.ci_lifecycle.<class>)` for each
   class, `MAX(livespec.ci_kueue.pending)`,
   `MAX(livespec.ci_kueue.admitted)`,
   `MAX(livespec.ci_churn_slot.allocatable)`,
   `MAX(livespec.ci_churn_slot.quota_sum)`, plus the heartbeat's
   `MAX(livespec.ci_runners.active)`.

The question the three answer together: at what workflow-pod concurrency
does the array's queue time per operation climb, and do the lifecycle
classes (or Kueue's pending count) rise at the same moment. That
concurrency, measured from real traffic rather than a synthetic benchmark,
is the ceiling `C`.

The first two as `run_query` specs (the Honeycomb MCP shape; the Query
Builder's fields are the same):

```json
{"calculations":[{"op":"COUNT_DISTINCT","column":"k8s.pod.name"}],
 "filters":[{"column":"host.name","op":"=","value":"poweredge-xubuntu"},
            {"column":"k8s.namespace.name","op":"=","value":"arc-runners"},
            {"column":"k8s.pod.name","op":"ends-with","value":"-workflow"},
            {"column":"k8s.pod.phase","op":"=","value":2}],
 "granularity":300}
```

```json
{"calculations":[{"op":"SUM","column":"system.disk.weighted_io_time","name":"wt"},
                 {"op":"SUM","column":"system.disk.operations","name":"ops"}],
 "formulas":[{"name":"queue_s_per_op","expression":"$wt / $ops"}],
 "filters":[{"column":"host.name","op":"=","value":"poweredge-xubuntu"},
            {"column":"device","op":"=","value":"sda"}],
 "granularity":300}
```

**Boundary.** The cache tiers' own telemetry — the `build.cache.*`
attributes, the `cache.warm-copy` and `cache.job-summary` spans, dataset
`github-ci` — belongs to plan `ci-runner-cache-tiers`
(`plan/ci-runner-cache-tiers/research/003-cache-observability.md` in this
repository); nothing in that family is emitted here, and the disk and
filesystem rows this recipe joins are the collector's, not the cache's.

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
`/etc/sysctl.d/99-ci-runner-inotify.conf`, now shipped by
`node-inotify-budget/`); local-path-provisioner `--worker-threads 8
--kube-client-qps 50 --kube-client-burst 100` (first a live Deployment
patch, which k3s DID revert on the 2026-09-02 reboot by re-applying its
bundled `local-storage.yaml`; now the fleet-owned
`local-path-provisioner/` manifest applied by the boot converge, with the
bundled copy disabled by `k3s-config/` — `livespec-sernfh`); kubelet
`max-pods` 110 → 200 (see `kueue/DERIVATION.md`, "The pod-capacity
constraint"; now `k3s-config/config.yaml`). Kueue HA is `livespec-okxbkg`.

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
