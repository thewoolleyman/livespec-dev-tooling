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

## Files

| Path | Role |
|---|---|
| `provision-k3s.sh` | Idempotently installs a single-node k3s server, pinned to `v1.36.2+k3s1`, with `traefik`/`servicelb` disabled (this node carries no ingress) and a `k3s-role=arc-runner-host` node label. Never touches the existing `ci-runner` user, `runner@.service` instances, or podman. |
| `install-arc.sh` | Installs the ARC controller (Helm chart `gha-runner-scale-set-controller` 0.14.2) plus ONE `gha-runner-scale-set` (0.14.2) release, the host-unique-label scale set (see below). Phase 1 installed TWO here — one per label; the shared-pool-label release `local-ci-k3s` (`arc/values.yaml`) was retired under `livespec-s43svm.28`, see "Labels" below. Fails closed if the GitHub App installation-token secret isn't already present (never creates it). |
| `arc/values-host-unique.yaml` | Helm values for the host-unique-label release (`runnerScaleSetName: poweredge-xubuntu-k3s`), `maxRunners: 1`. Kubernetes-mode runners (containerd-backed pods, non-root `securityContext`, no privileged mode) — needing no equivalent of the deleted podman lane's dockershim/sanitize-hook pair. |
| `install-kueue.sh` | Installs Kueue `v0.19.1` from its released manifest, then applies `kueue/resources.yaml`. |
| `kueue/resources.yaml` | Minimal phase-1 `ResourceFlavor`/`ClusterQueue`/`LocalQueue` — just enough for Kueue to admit the proof job. Modeling the real fair-share formula is phase 2, deliberately deferred. |
| `test-job/proof-job.yml` | A `workflow_dispatch`-only GitHub Actions workflow targeting `runs-on: poweredge-xubuntu-k3s` (the scale set NAME as a bare string, not a label array — see the file's own comment) — the host-requirements "a host is proven by EXECUTING a job" proof. Never wired into any `needs:` chain or PR/push trigger, so it can never gate a merge. |
| `test-job/proof-job-kueue.yaml` | A raw, Kueue-admitted `batch/v1` Job (`suspend: true`, queued via `phase1-proof-lq`) — proves Kueue admission directly with `kubectl`, independent of GitHub's own dispatch plumbing. |

## Labels — confirmed distinct from the existing pool

Every runner MUST carry both a shared pool label and a host-unique
label, per livespec repo `SPECIFICATION/non-functional-requirements.md`
section "Self-hosted CI runner host requirements" ("Every runner MUST
carry both a shared pool label and a host-unique label"). The existing
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
  this pool's warm uv cache lower, `phase2/warm-cache/`).
- **Ports**: `6443/10250/10251/10252/10257/10259/8472/2379/2380` (the
  full k3s server + agent + embedded-etcd port set) were all UNBOUND —
  no conflict with the podman pool or anything else on the host.
- **Existing load**: the podman pool was running ~479-482 concurrent
  `runner@` units (near its documented cap) at inventory time, which
  the inventory judged ample headroom for a lightweight single-node k3s
  control plane (a few hundred MB to low GB for `k3s server` +
  `containerd` + the ARC controller + Kueue's controller-manager — a
  small fraction of the measured 90 GiB available).

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
readable only by the supervising identity (here, whoever runs
`install-arc.sh` with cluster-admin `kubectl` access), never injected
into a job's environment.

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
