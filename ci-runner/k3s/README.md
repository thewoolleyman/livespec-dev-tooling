# k3s + ARC + Kueue — the fleet's gating CI runner pool

Durable, re-runnable artifacts that provision this fleet's self-hosted CI
runner pool on `poweredge-xubuntu`, backed by k3s + Actions Runner
Controller (ARC) + Kueue.

This tree was authored for **phase 1** of the migration off rootless
podman, when it stood up as a *second, independent* pool ALONGSIDE the
podman/dockershim pool at `../`, routing zero traffic. That framing is
kept below wherever it explains a design choice, but it now describes
history: the podman pool was decommissioned on 2026-08-21 and its source
deleted under `livespec-s43svm.19`. This is the only pool.

Design record and full migration rationale: livespec repo
`plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md`
("Migration decision: rootless-podman host -> k3s + Actions Runner
Controller + Kueue"), maintainer-directed 2026-08-15. This tree is
**phase 1 of 6** of that migration:

1. **Stand up k3s + ARC + Kueue alongside the existing pool** (this
   tree). New host-unique label, zero traffic routed. Prove one real,
   non-gating job runs end-to-end. *(you are here)*
2. Model the fleet's admission/fair-share formula in ARC
   AutoscalingRunnerSets + Kueue ClusterQueues/Cohort.
3. Incremental per-repo cutover.
4. Soak-under-load verification.
5. Full cutover.
6. Delete the podman/dockershim stack entirely.

## Rebuild sequence — the first step is `phase0-bare-metal/`, not `provision-k3s.sh`

A pool node is rebuilt from powered-on hardware with EMPTY STORAGE by running
these in order. The sequence starts at step 1 even when the node "already looks
right": every step's preconditions are established by the step before it
(`SPECIFICATION/non-functional-requirements.md` §"Runner-pool node rebuild
recipe").

1. **`phase0-bare-metal/storage-layout.sh profiles/<node>.env`** — the storage
   controller's virtual disk, the partition table, the volume groups, the
   logical volumes and the `mkfs` that puts the role labels (`ci-cache`,
   `ci-containerd`, `ci-workvols`) on them. Nothing below this line can run on a
   node that has not had this step: `phase2/storage-layout/install-storage-layout.sh`
   never formats anything and refuses when a role label resolves to zero block
   devices.
2. **`phase0-bare-metal/base-os-install.sh profiles/<node>.env`** — the base
   operating system installed onto the volumes step 1 created: the pinned
   release debootstrapped into the root logical volume, `/etc/fstab` found
   entirely by LABEL, `lvm2` and an initramfs that activates the root volume
   group, a signed shim and GRUB on the ESP with `root=` by LVM id, the firmware
   boot entry, the hostname, the network address and the operator account. This
   is the step that establishes the **installed operating system** step 3
   assumes and never creates.
3. **`provision-k3s.sh phase0-bare-metal/profiles/<node>.env`** — the pinned k3s
   in the role that profile declares: on a `server`, the control plane and the
   admin kubeconfig every later step reads; on an `agent`, the join to the
   cluster the profile names. It reads the same profile steps 1 and 2 used. On
   an `agent`, `secret-reinjection/seed-k3s-agent-join-token.sh <profile>` runs
   FIRST, under the `github-ci-runners` 1Password wrapper: it puts the join
   token at `CLUSTER_TOKEN_FILE`, `0600 root:root`, which this step refuses to
   provision without. The SEED also creates `/etc/rancher/k3s` when the node has
   never run k3s — that directory is otherwise made by the k3s installer this
   step runs, which is too late — so the two run in this order with no hand step
   between them.
4. **`sudo phase2/install-node.sh phase0-bare-metal/profiles/<node>.env`** — the
   ordered node-local runbook. It reads the node's cluster role and its
   admission capacity `C` from the same profile step 1 used, and runs the step
   plan that role calls for.
5. **`install-arc.sh`, `install-kueue.sh`** — the phase-1 by-hand cluster
   provisioning legs, superseded for boot durability by `phase2/reconstruct/`.

Every node-specific value in steps 1–4 comes from that node's
`phase0-bare-metal/profiles/<node>.env`; a second node is a second profile, not
a second procedure.

Two profiles are committed, and between them they exercise both shapes the
sequence has:

| Profile | The node it is | What it takes from the sequence |
|---|---|---|
| `phase0-bare-metal/profiles/poweredge-xubuntu.env` | the first pool node: a PowerEdge with a PERC H730P, three media, and the control plane | all four steps, `DISK_PLAN=whole-device`, `CLUSTER_ROLE=server`, capacity `C=32` |
| `phase0-bare-metal/profiles/gmktec-xubuntu.env` | the second pool node: a GMKtec with one 2 TB NVMe, no storage controller, and the Xubuntu it already runs | steps 1, 3 and 4. `DISK_PLAN=free-space` preserves the root and EFI partitions at `nvme0n1p1`/`nvme0n1p2` and puts volume group `nvmea` — all three tiers — in the 1441 GiB tail at `nvme0n1p3`; `CLUSTER_ROLE=agent` joins `https://192.168.1.200:6443` from `eno1` at `192.168.1.156/24` with a `node-role/ci=pending:NoSchedule` taint and capacity `C=0`. **Step 2 is skipped and refuses if run**: the node keeps its operating system, which is the whole reason its plan is `free-space`. |

**The `gmktec-xubuntu` build is this recipe's first rehearsal.** The first
node's profile was transcribed from a rebuild already done by hand, so the
sequence describes that node rather than having produced it; the second node has
not been built, so building it from `profiles/gmktec-xubuntu.env` is the first
end-to-end run of the committed procedure. See
`phase0-bare-metal/README.md` §"Rehearsed before trusted".

## Files

| Path | Role |
|---|---|
| `phase0-bare-metal/` | **Steps 1 and 2 of the rebuild sequence above** — the bare-metal stages that run BEFORE k3s exists and before `phase2/install-node.sh`'s admin-kubeconfig precondition. `storage-layout.sh <profile>` takes a node from empty storage to the controller virtual disk, GPT ESP + LVM physical volume, volume groups, logical volumes and role-labelled filesystems that `phase2/storage-layout/install-storage-layout.sh` then expects to find; `base-os-install.sh <profile>` takes those volumes to an installed, bootable operating system, writing the same five tier fstab lines that installer ensures. Every node-specific value lives in `profiles/<node>.env` — `profiles/poweredge-xubuntu.env` for the first node, `profiles/gmktec-xubuntu.env` for the second, whose `DISK_PLAN=free-space` keeps the operating system that node already runs and takes only its device's unpartitioned tail; the scripts carry none, and both parse it through the shared `profile.sh`. Re-runnable against a node already in its profile's declared state; destructive steps refuse unless the invocation carries `--i-consent-to-destroy=<target>` naming that exact target; `--dry-run` prints every command and executes none. See `phase0-bare-metal/README.md` for the stage order, the consent rule, and the standing rehearsal obligation. |
| `phase0-bare-metal/recovery-usb/` | The rescue environment every stage below is rebuilt FROM — a builder for the Ubuntu Desktop Recovery USB, its QEMU+OVMF boot harness, and the record of the two GRUB boot traps a rebuild re-hits without them. Runs before an operating system exists on the node, so before `provision-k3s.sh` and before `phase2/install-node.sh`'s admin-kubeconfig precondition. See `SPECIFICATION/non-functional-requirements.md` §"Runner-pool node rebuild recipe". |
| `provision-k3s.sh` | Idempotently installs this node's pinned k3s (`v1.36.2+k3s1`) in the ROLE its profile declares (`provision-k3s.sh phase0-bare-metal/profiles/<node>.env`; the role and every other node-specific value are read through the shared `phase0-bare-metal/profile.sh`, so a second node is a second profile and never a second script). A **`server`** runs the six steps it has always run, in that order and with the same install command: the fleet's `/etc/rancher/k3s/config.yaml` from `phase2/k3s-config/` (kubelet `max-pods`, the bundled `local-storage` disable) installed BEFORE the first start so it is already read; the k3s **server** with `traefik`/`servicelb` disabled (this node carries no ingress) and a `k3s-role=arc-runner-host` node label; the pinned `helm`; the Ready wait; the `ci-runner.io/cache-tier-carrier=true` label (idempotently, via `kubectl label --overwrite`, and ONLY when the `ci-cache` tier is actually mounted here) — that is the label the pool's hostPath singletons, the sccache redis, the crates proxy, the PyPI files proxy and the warm-cache CronJob, pin their `nodeSelector` to, because `k3s-role=arc-runner-host` is the RUNNER role and a second pool node carries it too; and the kubeconfig mode. An **`agent`** runs ONE of those steps — the pinned k3s **agent** install — and SKIPS the five that are the server's (the server-only `config.yaml`, `helm` for the converge, the Ready wait, the tier-carrier label and the kubeconfig mode), logging the reason for each. It joins `CLUSTER_JOIN_ADDRESS`, pins `--node-ip` from `NODE_ADDRESS` (mandatory on a node whose wired and wireless interfaces share a subnet), registers every `NODE_TAINTS` taint as its own `--node-taint`, and carries the same `k3s-role=arc-runner-host` label so the `phase2/` node pins still resolve. The join token is read AT RUN TIME by k3s out of `CLUSTER_TOKEN_FILE`, which is a PATH and never the token — this tree carries no secret — and the run REFUSES if that file is absent or readable beyond its owner. `--dry-run PROFILE` prints the plan for either role, including the exact install command, and executes nothing; `provision-k3s-exit-tests.sh` asserts both plans and the token-file refusals off-host. Never touches the existing `ci-runner` user, `runner@.service` instances, or podman. |
| `provision-k3s-exit-tests.sh` | This script's exit tests. Runs `provision-k3s.sh` only through `--dry-run`, never as root, with every host-mutating tool the steps reach for (`curl`, `k3s`, `kubectl`, `helm`, `install`, `chmod`, `tar`, `findmnt`) replaced by a tripwire — so the suite proves that a `server` profile's plan is byte-for-byte the command sequence the single-node era ran, that an `agent` profile's plan is the pinned agent join carrying the version pin, `--server`, `--token-file`, `--node-ip`, `--node-taint` and the runner-role label, that the five server-only steps are skipped with a reason each, and that an absent or too-readable join-token file is refused, while touching no host at all. §E runs the COMMITTED `phase0-bare-metal/profiles/gmktec-xubuntu.env` rather than a fixture derived from the first node's, redirecting only its `CLUSTER_TOKEN_FILE` at a scratch `0600` file (and asserting that is the only substituted line), so the second node's own data is proven to yield `--node-ip 192.168.1.156` and the `NoSchedule` taint. |
| `phase2/install-node.sh` | The ONE ordered runbook for every node-local installer under `phase2/` plus `secret-reinjection/` (`sudo phase2/install-node.sh phase0-bare-metal/profiles/<node>.env`). It reads the node's `CLUSTER_ROLE` and `ADMISSION_CAPACITY_C` from that profile, and logs every step — run or skipped — with the role. A **`server`** runs the whole ordered list: k3s config, the kernel budgets, the storage layout, the iDRAC thermal convergence, host tools, AppArmor profile + hook ConfigMap, churn-slot + timer, both scans, the log archive, the secret-reinjection unit, sccache + cache telemetry, the container hook, the converge unit + artifacts, the tmpfs mount, the storage sweep — enabled, never started. An **`agent`** runs the node-local subset of exactly that list, in exactly that order, and SKIPS the eight steps that are the server's — the iDRAC thermal convergence (PowerEdge hardware), the churn-slot reapply unit (its unit is ordered against `k3s.service` and its node-status patch selects EVERY labeled node, so the server's own reapply timer already applies it for the whole pool; `livespec-dev-tooling-ukbp`), the wedged-runner sweep, the runner-pod lifecycle sweep and the ARC log archive (each carries the admin `KUBECONFIG` and each sweeps or reads the pool CLUSTER-WIDE, so the server's own three timers already cover every node, this one included; `livespec-dev-tooling-qcq0`), the secret-reinjection unit and the reconstruct-on-boot converge (cluster-scoped, admin-kubeconfig-only; the converge is the only step that applies Kueue ClusterQueues and ARC scale sets, so skipping it is what omits them) and the tmpfs datastore (an agent has none) — logging the reason for each. AppArmor runs on both, `--profile-only` on an agent, because the profile is kernel state on every node while the `arc-hook-pod-template` ConfigMap is one cluster object. `--dry-run PROFILE` prints the plan for either role and executes nothing; `phase2/install-node-exit-tests.sh` asserts both plans off-host. The capacity is READ from the profile rather than typed on the command line, so the README's standing "never a stale literal" rule holds by construction; it is **32 since 2026-09-06** by measurement (`phase2/kueue/DERIVATION.md` "The step back to C = 32 on the tiered host (2026-09-06)"), and the profile's value must stay the one the ten ClusterQueue quotas sum to. Run it on a fresh node after this script, and re-run it after any edit to that tree. |
| `install-arc.sh` | Installs the ARC controller (Helm chart `gha-runner-scale-set-controller` 0.14.2) plus ONE `gha-runner-scale-set` (0.14.2) release, the host-unique-label scale set (see below). Phase 1 installed TWO here — one per label; the shared-pool-label release `local-ci-k3s` (`arc/values.yaml`) was retired under `livespec-s43svm.28`, see "Labels" below. Fails closed if the GitHub App installation-token secret isn't already present (never creates it). |
| `arc/values-host-unique.yaml` | Helm values for the host-unique-label release (`runnerScaleSetName: poweredge-xubuntu-k3s`), `maxRunners: 1`. Kubernetes-mode runners (containerd-backed pods, non-root `securityContext`, no privileged mode) — needing no equivalent of the deleted podman lane's dockershim/sanitize-hook pair. |
| `install-kueue.sh` | Installs Kueue `v0.19.1` from its released manifest, then applies `kueue/resources.yaml`. |
| `kueue/resources.yaml` | Minimal phase-1 `ResourceFlavor`/`ClusterQueue`/`LocalQueue` — just enough for Kueue to admit the proof job. Modeling the real fair-share formula is phase 2, deliberately deferred. |
| `test-job/proof-job.yml` | A `workflow_dispatch`-only GitHub Actions workflow targeting `runs-on: poweredge-xubuntu-k3s` (the scale set NAME as a bare string, not a label array — see the file's own comment) — the host-requirements "a host is proven by EXECUTING a job" proof. Never wired into any `needs:` chain or PR/push trigger, so it can never gate a merge. |
| `test-job/proof-job-kueue.yaml` | A raw, Kueue-admitted `batch/v1` Job (`suspend: true`, queued via `phase1-proof-lq`) — proves Kueue admission directly with `kubectl`, independent of GitHub's own dispatch plumbing. |
| `phase2/reconstruct/` | Reconstruct-on-boot for the WHOLE CI cluster stack: a boot-ordered `systemd` `oneshot` (`After=k3s.service`) that idempotently converges the ARC controller, all scale sets, the hook ConfigMap, and Kueue + every queue from this repo with zero manual steps — making the host reconstructible ("cattle") so its datastore can later be made volatile. It SUPERSEDES the by-hand `install-arc.sh` step 2 + `install-kueue.sh` phase-1 legs for boot durability; those remain the phase-1 provisioning path. See `phase2/README.md` "Reconstruct-on-boot" for the scope boundary and the drift it supersedes. |
| `phase2/datastore-tmpfs/` | The k3s kine/SQLite datastore on tmpfs: a systemd `.mount` unit (ordered `Before=k3s.service`, never `Required` by it) plus an installer that enables it for next boot and never starts it live. VOLATILE by design — cleared on every reboot so the reconstruct-on-boot path is exercised rather than rotting; safe only because `phase2/reconstruct/` + `secret-reinjection/` rebuild the cluster from empty, which the installer pre-gates on. Fail-safe: a mount failure degrades to the on-disk datastore rather than blocking boot; rollback is disable + restart k3s, the disk copy intact underneath. Removes the kine `Slow SQL` stall class of 2026-09-01 (livespec plan `ci-runner-pod-lifecycle-reliability`, research/003). See `phase2/README.md` "Datastore on tmpfs". |

## Pinned versions — nothing floats `latest`

| Component | Version | Where the pin lives |
|---|---|---|
| k3s | `v1.36.2+k3s1` | `provision-k3s.sh` (`INSTALL_K3S_VERSION`) — **held deliberately; see below** |
| ARC controller chart | `0.14.2` | `install-arc.sh` |
| ARC runner scale set chart | `0.14.2` | `install-arc.sh` and every `phase2/arc/values-*.yaml` apply |
| Runner image | `ghcr.io/actions/actions-runner:2.336.0@sha256:0cfdcc70…` | every `values-*.yaml` `template.spec.containers[0].image` |
| Kueue | `v0.19.1` | `install-kueue.sh` |
| helm | `v3.21.4` | `provision-k3s.sh` (`HELM_VERSION`; checksum-verified against the release's `.sha256sum`) — required by `phase2/reconstruct/converge-ci-stack.sh` |

The **k3s pin is HELD deliberately**, not merely un-bumped
(`livespec-n5eudb`, decided 2026-09-07). k3s `v1.36.2+k3s1` bundles
flannel `v0.28.4`, whose vxlan backend panics on a nil pointer in
`watchVXLANDevice` when its netlink subscription closes on `ENOBUFS` —
the 2026-09-06 06:07:03Z crash that took the API away and failed 17
in-flight jobs. Bumping buys nothing: the same defect is live at
flannel's development tip, the upstream report
`flannel-io/flannel#2549` is untriaged, the newest release `v0.28.9`
predates it, and every k3s tag checked (`v1.36.2`, `v1.36.3`,
`v1.36.4`, `v1.37.0-rc3`) bundles the same flannel. The mitigation is
the **churn-slot cap of 32**, which is the only thing currently
preventing recurrence — any increase toward 64 must land a mitigation
first. Detection is the `api-unavailable` Honeycomb alarm. The full
reasoning and mitigation ladder sit beside the pin in
`provision-k3s.sh`.

Nothing floats `latest` (rule restated here after the tree that first
carried it was deleted under `livespec-s43svm.19`). The runner image is
pinned by tag AND digest because the image embeds the container hook
whose merge behaviour two live mechanisms depend on — the job container's
`env` and `lifecycle` merge (the cache tiers' reader side: the warm-cache
seed's `UV_CACHE_DIR`, the cargo and compilation tiers' `postStart`) and
the workflow pod's `hostUsers` key
(`phase2/arc/hook-pod-template.yaml`); the pinned digest is the build
those were verified against. The image ran as the un-pinned `latest`
from phase 1 until 2026-08-25, when the then-current `latest`
(`2.336.0`, the digest above) was pinned in place — so the pin changed
no running bytes, only froze them. To bump: change tag and digest
together in every values file, re-read the hook's `initContainers`
behaviour against the template's header, `helm upgrade` each release,
and recycle idle runners (`phase2/arc/recycle-scale-set-runners.sh`).

Since `livespec-wm7c` the runner does not run the image's own container
hook but a fleet-patched rebuild of it (`phase2/container-hook/`), and
the image's externals are extracted host-side for the work-volume seed
— so a runner-image bump is ALSO a hook rebuild and a re-extraction:
run `phase2/container-hook/build-patched-hook.sh` on a developer host
BEFORE changing the values files and commit its `bundle/<new version>/`
in the same change, then re-run `phase2/install-node.sh` (step 7c) on
the node, then apply the values. The build derives the hook version the
new image bundles and fails loudly if `externals-skip.patch` no longer
applies to it — that failure blocks the bump until the patch is
re-derived, by design. Each values file states the runner version THREE
times — the `image:` pin, the `fleet-container-hook` hostPath
(`hooks/<version>/index.js`) and
`ACTIONS_RUNNER_PRESEEDED_EXTERNALS_VERSION` — and no file can inherit
it from another, because Helm applies each on its own with `-f` and
merges no shared base; `runner-image.sh`'s `assert_values_pins_agree`
refuses a half-rewritten set from both the build and the node install.
The full procedure and the failure modes are in
`phase2/container-hook/README.md` "Runner-image bump".

## Labels — confirmed distinct from the existing pool

When this tree was authored the governing clause read "Every runner
MUST carry both a shared pool label and a host-unique label". That
wording is HISTORY: v213 of the livespec repo's
`SPECIFICATION/non-functional-requirements.md` §"Self-hosted CI runner
host requirements" restated it as a PROPERTY — "Every pool member MUST
be separately addressable, in addition to being reachable through the
pool" — which a label-based pool satisfies with the label pair below,
and an autoscaling-runner-set pool satisfies by set-name addressing,
because ARC runners register with NO labels at all (the measurement
that forced the restatement is `phase2/README.md` "Registrations are
ephemeral"). This pool satisfies it with the per-repository scale sets
plus the host-unique `poweredge-xubuntu-k3s` set. The label table below
is kept as the phase-1 history it is. The existing
podman pool's actual labels were read directly from this repo's
`.github/workflows/ci.yml` (`select-ci-runner.local-runner-labels:
'["self-hosted","local-ci"]'`) rather than re-guessed. This tree's
phase-1 labels were chosen to be unambiguously distinct:

| | podman pool (deleted, `livespec-s43svm.19`) | this k3s+ARC pool, phase 1 |
|---|---|---|
| shared pool label | `local-ci` | `local-ci-k3s` (retired, `livespec-s43svm.28`) |
| host-unique label | (host-specific, registered per runner instance) | `poweredge-xubuntu-k3s` |

The shared-pool-label scale set `local-ci-k3s` was the phase-1 proof's
two-runner release (`arc/values.yaml`, since deleted). It was never
routed to by any workflow in any fleet repository — the per-repository
scale sets under `phase2/arc/` took the shared-pool role at the phase-3
cutover — so its Helm release was uninstalled from `arc-runners` on
2026-08-23 under `livespec-s43svm.28`. Only `poweredge-xubuntu-k3s`
remains from phase 1, because this repo's
`.github/workflows/k3s-arc-proof-job.yml` still targets it.

## Resource envelope (from the phase-1 read-only host inventory)

Measured 2026-08-15 on `poweredge-xubuntu` (per the ledger record on
`livespec-s43svm.14`), before any k3s installation:

- **CPU**: 72 cores.
- **Memory**: 188 GiB total, ~90 GiB available.
- **Disk**: 306 GB free on the root filesystem; 624 GB free on the
  dedicated `/var/cache/ci-runner` volume (at the time unrelated to
  k3s — it backed the podman pool's warm cache tiering; it now carries
  only the mountpoints of this pool's two other tiers, and the warm uv
  cache lower lives on the `ci-workvols` tier beside the runner work
  volumes it is reflink-copied into, `phase2/warm-cache/`).
- **Ports**: `6443/10250/10251/10252/10257/10259/8472/2379/2380` (the
  full k3s server + agent + embedded-etcd port set) were all UNBOUND —
  no conflict with the podman pool or anything else on the host.

- **Existing load**: the podman pool was running ~479-482 concurrent
  `runner@` units (near its documented cap) at inventory time, which
  the inventory judged ample headroom for a lightweight single-node k3s
  control plane (a few hundred MB to low GB for `k3s server` +
  `containerd` + the ARC controller + Kueue's controller-manager — a
  small fraction of the measured 90 GiB available).

This is intentionally the dated phase-1 baseline, not the current host
inventory. The PowerEdge exposes 377 GiB after the 2026-09-10 memory upgrade;
the current socket-level record lives in `poweredge-xubuntu-info/MEMORY.md`.

This envelope is why phase 1 provisions k3s ALONGSIDE the pool rather
than requiring any capacity trade-off: the host has room for both
simultaneously, and the podman pool's own capacity, config, and traffic
are unaffected by anything in this tree.

## Zero traffic routed yet

Nothing in this tree, and no workflow in this repo or any other fleet
repo, targets `poweredge-xubuntu-k3s` (or, while it existed,
`local-ci-k3s`) as a merge-gating `runs-on:` selector. `minRunners: 0`
on the ARC release means zero runner pods sit idle by default;
`test-job/proof-job.yml` is `workflow_dispatch`-only (no
`push`/`pull_request` trigger) so it can never become a required status
check. Cutting real traffic to the k3s pool was phase 3 of the
migration, and it landed on the per-repository scale sets under
`phase2/arc/`, not on these phase-1 names.

## GitHub registration scope — REPOSITORY, not organization (`thewoolleyman` is a personal account)

`arc/values-host-unique.yaml` (and, before its retirement, `arc/values.yaml`) sets
`githubConfigUrl` to `https://github.com/thewoolleyman/livespec-dev-tooling`
— a specific REPOSITORY, not the account-root form
`https://github.com/thewoolleyman`. This was discovered live during
`livespec-s43svm.14`: the account-root form routes ARC's controller to
GitHub's ORGANIZATION-level self-hosted-runner registration endpoint
(`POST /orgs/{org}/actions/runners/registration-token`), which returned
a `404 Not Found` even after the `thewoolleyman-ci-runners` GitHub App
installation was granted the "Self-hosted runners: read & write"
organization permission. Root cause, confirmed via
`gh api users/thewoolleyman --jq .type` returning `User`:
**`thewoolleyman` is a personal GitHub User account, not an
Organization.** GitHub's org-level self-hosted-runner API endpoints do
not exist for personal accounts at all — this is architectural, not a
permissions gap, and no scope grant on the App installation can change
it.

Self-hosted runners for a personal account are always registered
**per-repository**
(`https://github.com/{owner}/{repo}/actions/runners/registration-token`).
This matches how the existing podman pool has always worked (JIT
runner registration is per-repo, via `CI_RUNNER_LABELS` and
`../gate-runner/mint-jitconfig.sh` — never org-wide), and it is why
phase 1 scoped both of its ARC releases to `livespec-dev-tooling` specifically:
the phase-1 proof job (`test-job/proof-job.yml`) already lives in this
repo's own `.github/workflows/`, so a single repo-scoped
`githubConfigUrl` is enough to validate the ARC path end-to-end without
needing multi-repo ARC scope-fanout (out of scope for phase 1).

**Design implication for phase 3 (`livespec-s43svm.16`, per-repo
cutover):** because personal-account self-hosted-runner scope is always
per-repository, phase 3 cannot reuse a single shared, org-wide
`AutoscalingRunnerSet` the way an Organization account could. Each repo
being migrated onto the k3s+ARC+Kueue path needs its OWN
`githubConfigUrl` (and therefore its own `gha-runner-scale-set` Helm
release, or an equivalent one-release-per-repo pattern) — one
`AutoscalingRunnerSet` per repo, not one shared scale set fanning out
across repos. Whoever picks up `.16` should design the per-repo cutover
around that constraint from the start, rather than discovering it after
attempting a shared scale set.

## k3s uninstall procedure — what `k3s-uninstall.sh` actually does at v1.36.2+k3s1

k3s does not ship a static uninstall script; `install.sh` (fetched
above, and generated as `/usr/local/bin/k3s-uninstall.sh` at install
time) **writes** the uninstall script from a heredoc at install time,
so its content is pinned to the same `v1.36.2+k3s1` tag this tree
installs. Read directly from
`https://raw.githubusercontent.com/k3s-io/k3s/v1.36.2%2Bk3s1/install.sh`
(`create_uninstall()` at line 898, embedding `create_killall()`'s
script at line 797) rather than assumed, the generated
`/usr/local/bin/k3s-uninstall.sh` does, in order:

1. **Re-execs as root** if not already (`sudo --preserve-env=K3S_DATA_DIR`).
2. **Runs the embedded killall logic first**: stops every
   `k3s*.service` / `/etc/init.d/k3s*` unit; kills the process tree of
   every `containerd-shim` process rooted under
   `${K3S_DATA_DIR}/data/*/bin/`; unmounts and removes everything under
   `/run/k3s`, `/var/lib/kubelet/pods`, `/var/lib/kubelet/plugins`, and
   `/run/netns/cni-*`; deletes any `cni-*` network namespaces; deletes
   the `cni0`/`flannel.1`/`flannel-v6.1`/`kube-ipvs0`/`flannel-wg*`
   network interfaces (restoring any `tailscale --advertise-routes` if
   tailscale is present); removes `/var/lib/cni/`; and rewrites the
   `iptables`/`ip6tables` rule sets with every `KUBE-`/`CNI-`/flannel
   rule stripped out (everything else preserved).
3. **Disables the systemd unit**: `systemctl disable k3s`,
   `reset-failed`, `daemon-reload` (or the OpenRC equivalent), then
   removes the unit file and its env file.
4. **Bails out early** (leaving the data dirs intact) if it finds any
   OTHER `k3s*.service`/`/etc/init.d/k3s*` file still present — i.e. it
   refuses to remove shared state while another k3s instance (e.g. an
   agent) is still registered on the same host.
5. Otherwise removes the `kubectl`/`crictl`/`ctr` symlinks, then
   recursively deletes `/etc/rancher/k3s`, `/run/k3s`, `/run/flannel`,
   and `${K3S_DATA_DIR}` (default `/var/lib/rancher/k3s`) — walking
   mount points so it never deletes THROUGH an active bind-mount
   without unmounting it first — and `/var/lib/kubelet`.
6. Removes the `k3s` binary and the killall script itself, and (on
   RPM/SUSE-family hosts only — not the fleet's Ubuntu hosts) removes
   the `k3s-selinux` package and its yum/zypper repo file.

**What it never touches**: anything belonging to the former podman pool
(the `ci-runner` user, `runner@.service` instances, `containers.conf`,
dockershim, or `/var/cache/ci-runner`) — there was no shared state
between the two stacks by construction (different systemd units,
different container runtimes, different bind mounts). A k3s uninstall
on this host was therefore safe with respect to that pool's traffic,
matching the migration's side-by-side, no-shared-fate requirement. Those
host artifacts are stopped; their removal is tracked separately. This procedure is documented here as the phase-1
rollback path; it has not been rehearsed live against
`poweredge-xubuntu`, per this task's own scope (documenting the
procedure satisfies the requirement; a live rehearsal is not required).

## Credential separation

The GitHub App installation token that backs `arc-github-app-installation`
(referenced from `arc/values-host-unique.yaml` and every `phase2/arc/values-*.yaml`) MUST be created out-of-band —
`install-arc.sh` fails closed if the secret is missing rather than
creating it — from the same least-privilege, read-scoped source the
existing podman pool's supervisor already uses
(`../gate-runner/mint-jitconfig.sh`'s token minting), never a broader
fleet secret. This matches the existing host-requirements "Credential
separation" clause: the credential that mints runner registrations is
seeded from 1Password only by a human maintainer and, at boot, is readable
only by root (the reinjection unit below), never injected into a job's
environment.

### Automated boot reinjection (`secret-reinjection/`) — the out-of-band step, automated

`install-arc.sh` still never creates the secret. What was formerly a
MANUAL out-of-band step (create the secret by hand before running
`install-arc.sh`) is now automated by the boot-time unit under
`secret-reinjection/`, so a wiped or `tmpfs`-backed k3s datastore comes
back with the credential ARC needs after ONE boot, with no human
recreating it. This is the precondition for the tmpfs-datastore cutover
(sibling item `livespec-mx26zz`) and the reconstruct-on-boot converge
(sibling item `livespec-olp4c5`).

**The model: seed once from 1Password (attended), decrypt locally at boot
(unattended).** The three App values are stored host-encrypted in the
systemd credstore (`/etc/credstore.encrypted/`). A human maintainer seeds
them once from 1Password; thereafter the boot unit decrypts them locally as
root with `systemd-creds` — **no `op run`, no 1Password wrapper, no
network at boot.** (`op run` refuses to run as root, and this host has no
unattended identity in the `github-ci-runners` 1Password group, so the boot
path cannot touch 1Password at all. `systemd-creds` is already used on this
host for its own service-account token.) The credstore lives on durable
RAID, so it survives a `tmpfs`-datastore reboot; re-run the seed step to
rotate the key.

| Path | Role |
|---|---|
| `secret-reinjection/seed-github-app-creds.sh` | **Attended, run once by the maintainer** (a `github-ci-runners` group member). Under the 1Password wrapper it reads the three values and writes each host-encrypted into `/etc/credstore.encrypted/` via `systemd-creds encrypt` (value via STDIN, never argv). Also the re-seed step on key rotation. |
| `secret-reinjection/inject-github-app-secret.sh` | The **boot** injector, runs as root. Reads the three decrypted credentials from `$CREDENTIALS_DIRECTORY`, ensures the `arc-runners` namespace exists, then creates/refreshes `arc-github-app-installation` idempotently (`kubectl create … --dry-run=client -o yaml \| kubectl apply -f -`). |
| `secret-reinjection/inject-github-app-secret.service` | systemd oneshot (root) that decrypts the three credstore credentials via `LoadCredentialEncrypted=` and runs the injector at boot, `After=k3s.service` and `Before=converge-ci-stack.service` (the `livespec-olp4c5` converge, authored in the sibling PR `feat/ci-host-reconstruct-on-boot`), so the secret exists before ARC is brought up. |
| `secret-reinjection/seed-gate-forge-cred.sh` | **Attended, run once by the maintainer** (a `github-ci-runners` group member). The gate-forge sibling of `seed-github-app-creds.sh`: under the 1Password wrapper it reads ONE value, `GATE_FORGE_TOKEN` (the delegated gate's fine-grained PAT, Administration:Read + Metadata:Read on the gated repositories), and writes it host-encrypted to `/etc/credstore.encrypted/gate-forge-token` via `systemd-creds encrypt` (value via STDIN, never argv). Also the re-seed step when the PAT expires (~1-year expiry) or rotates. |
| `secret-reinjection/inject-gate-forge-secret.sh` | The **boot** injector for the gate credential, runs as root. Reads the decrypted `gate-forge-token` from `$CREDENTIALS_DIRECTORY`, ensures the `gates` namespace exists, then creates/refreshes `gate-forge-credential` (data key `GH_TOKEN`) idempotently (`kubectl create … --dry-run=client -o yaml \| kubectl apply -f -`), the token handed via `--from-file` straight from the root-only cred path. |
| `secret-reinjection/inject-gate-forge-secret.service` | systemd oneshot (root) that decrypts `gate-forge-token` via `LoadCredentialEncrypted=` and runs the injector at boot, `After=k3s.service`. No `Before=converge-ci-stack.service`: unlike the ARC App secret, no converge step consumes this Secret (delegated gate Jobs are submitted ad hoc by the gate-remote client), so running at boot after k3s suffices. Closes the reboot-durability gap that silently broke the delegated gate when a `tmpfs`-datastore reboot wiped the hand-created Secret (plan livespec `k3s-on-gmktec-for-vps-usage`, epic `livespec-sab5gn`). |
| `secret-reinjection/install-secret-reinjection-unit.sh` | Installs BOTH reinjection injectors to `/usr/local/lib/ci-runner-k3s/` and BOTH units (`inject-github-app-secret.service`, `inject-gate-forge-secret.service`) to `/etc/systemd/system/`, then `systemctl enable` (NOT `--now`) — arms them for next boot without applying live. Warns per unit if its credstore credentials are not yet seeded. |
| `secret-reinjection/seed-k3s-agent-join-token.sh` | **Attended, run once by the maintainer ON AN AGENT — the step BEFORE `provision-k3s.sh` on that node** (rebuild sequence step 3). Under the same 1Password wrapper it reads ONE value, `K3S_AGENT_JOIN_TOKEN_CI_RUNNER`, and writes it to the path the node's profile names in `CLUSTER_TOKEN_FILE` (`/etc/rancher/k3s/agent-join-token` on `gmktec-xubuntu`) via `sudo install` reading STDIN, mode `0600 root:root` — the exact file `provision-k3s.sh` REFUSES to provision an agent without, in `--dry-run` too. The value flows over STDIN and is never echoed, logged or placed on argv. Idempotent: a target whose bytes already equal the injected value is REPORTED, not rewritten (so a rotated token IS written). Refuses when the variable is unset or empty, when `CLUSTER_ROLE` is not `agent` (a server MINTS the token at `/var/lib/rancher/k3s/server/node-token`, which is the value being seeded), and when the target's parent directory does not exist AND is not the k3s configuration directory — a mistyped path is refused rather than manufactured. A missing `/etc/rancher/k3s`, or a directory beneath it, it CREATES instead (`install -d -m 0755 -o root -g root`, printed as a `+ ` line): that tree is normally the k3s installer's, which on an agent runs AFTER this seed, so leaving it to the operator left stage 3 of the rebuild recipe unstartable without a hand-run `mkdir` (found live on `gmktec-xubuntu` 2026-09-07). An EXISTING parent is left exactly as it is, mode and ownership untouched. `--dry-run PROFILE` prints the target, the mode and the parent's state (`exists` / will be created / would refuse), needs no credential, and executes nothing. Also the re-seed step on token rotation. |
| `secret-reinjection/seed-k3s-agent-join-token-exit-tests.sh` | That seed step's exit tests. Runs it against a FIXTURE token this suite invents (nothing here reads 1Password) writing into a scratch target, with `sudo`/`install` replaced by tripwires for every dry-run and refusal case — so the suite proves the printed target and mode, a byte-exact write at `0600`, an idempotent second run that runs no `install` at all, a rotated value that IS written, and each refusal, while touching no host. §F pins the fresh-node case under the suite's OWN scratch root: an absent `.../etc/rancher/k3s` is planned as a `+ install -d` line, created `0755` and only then written into, a near-miss (`.../etc/rancher/k3s-agent`) is still refused and created for nothing, and an existing parent comes back with the mode and ownership it went in with. Needs no root: the fake `sudo` rewrites `install`'s `-o root -g root` to the invoking user, and the suite passes unprivileged and as root alike. |

**No boot half, and why.** The App credentials above need one because they live
in the k3s datastore, which is volatile by design; the agent join token does
not. It is a file on the agent's own durable root filesystem, read AT RUN TIME
by k3s out of `CLUSTER_TOKEN_FILE` — so seeding it once is enough, and the
directory carries the attended half only. Storing the server's
`/var/lib/rancher/k3s/server/node-token` into the `github-ci-runners`
Environment as `K3S_AGENT_JOIN_TOKEN_CI_RUNNER` is the maintainer's own
one-time attended step; no script in this tree reads the server's token.

**1Password source (seed step only) — the least-privilege `github-ci-runners`
Environment, never a broader fleet secret.** `seed-github-app-creds.sh` runs
UNDER the dedicated `github-ci-runners` 1Password wrapper
(`/usr/local/bin/with-github-ci-runners-env.sh`) — the SAME wrapper and
Environment the podman pool's gate supervisor used
(`../gate-runner/gate-runner-supervisor.sh`). It injects three variables,
which flow into three credstore credential names and, at boot, onto the
secret's three data keys:

| 1Password Environment variable | credstore credential | Secret data key |
|---|---|---|
| `GITHUB_APP_ID_CI_RUNNER` | `arc-github-app-id` | `github_app_id` |
| `GITHUB_APP_INSTALLATION_ID_CI_RUNNER` | `arc-github-app-installation-id` | `github_app_installation_id` |
| `GITHUB_PRIVATE_KEY_CI_RUNNER` (PEM content) | `arc-github-app-private-key` | `github_app_private_key` |

(These var names are the exact ones `../gate-runner/gate-runner-supervisor.sh`
reads out of that same injected env; the seed step reuses them.) Seed with:

```bash
# as a github-ci-runners group member (e.g. cwoolley); sudo prompts for the host key
with-github-ci-runners-env.sh -- ci-runner/k3s/secret-reinjection/seed-github-app-creds.sh
```

**The gate forge credential — same wrapper, one more variable.**
`seed-gate-forge-cred.sh` runs under the SAME `github-ci-runners` Environment and
injects ONE additional variable, which flows into its own credstore credential
and, at boot, onto the `gate-forge-credential` Secret's single data key:

| 1Password Environment variable | credstore credential | Secret data key |
|---|---|---|
| `GATE_FORGE_TOKEN` (fine-grained PAT) | `gate-forge-token` | `GH_TOKEN` |

The PAT needs Administration:Read (branch-protection is admin-scoped) +
Metadata:Read (check-runs are readable via Metadata) on the gated repositories,
and nothing else — see `phase2/gates/gate-credentials.yaml`. Seed with:

```bash
# as a github-ci-runners group member (e.g. cwoolley); sudo prompts for the host key
with-github-ci-runners-env.sh -- ci-runner/k3s/secret-reinjection/seed-gate-forge-cred.sh
```

**The App private key never lands in git or on argv, at seed OR at boot.**
At seed, the value flows into `systemd-creds encrypt` via STDIN (only the
ciphertext is written to disk). At boot, `LoadCredentialEncrypted=` places
the decrypted key as a root-only file in `$CREDENTIALS_DIRECTORY`, and the
injector hands that path to `kubectl` via `--from-file` — never
`--from-literal` (which would expose it in `/proc/<pid>/cmdline` and `ps`).
The id fields (not secret-sensitive) use `--from-literal`. Neither script
runs `set -x`; both print only phase banners.

**Boot identity — root, no external preconditions.** The boot unit runs as
root (default), so it reads the default `0600 root:root` kubeconfig
(`Environment=KUBECONFIG=`) directly and needs no group grant, no wrapper,
and no network. Its only prerequisite is that the credstore has been seeded;
`install-secret-reinjection-unit.sh` warns if it has not.

**Namespace: `arc-runners`, not `arc-systems`.** Create the secret in
the `arc-runners` namespace — the namespace every `gha-runner-scale-set`
Helm release (step 2, and the per-repo releases) lives in, and the one their own
AutoscalingRunnerSet reconciler actually resolves `githubConfigSecret`
from. `arc-systems` is only the separate `gha-runner-scale-set-CONTROLLER`
release's namespace (step 1) — a secret placed there passes nothing
downstream and leaves the runner-set reconciler unable to find it,
confirmed live on `poweredge-xubuntu` (`livespec-6r90`, filed off
`livespec-s43svm.14`'s diagnosis). `arc-runners` may not exist yet on a
genuinely fresh install (`install-arc.sh` step 2 is what
`--create-namespace`'s it) — create it yourself first if you need to
place the secret before running the script: `kubectl create namespace
arc-runners`.

## Nature

These are **host operational artifacts** (shell, Helm values, Kubernetes
manifests, docs) — not Python product code — mirroring `../`'s own
"Nature" section: they are not part of the `just check` aggregate.
Recreatability is the contract: re-running `provision-k3s.sh` /
`install-arc.sh` / `install-kueue.sh` converges a fresh host, and
`test-job/proof-job.yml` + `test-job/proof-job-kueue.yaml` prove the
path executes a real job.
