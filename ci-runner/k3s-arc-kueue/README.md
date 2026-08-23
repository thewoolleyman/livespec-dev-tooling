# k3s + Actions Runner Controller + Kueue — new CI-runner path (zero traffic)

Provisioning artifacts for a **k3s + Actions Runner Controller (ARC) + Kueue**
self-hosted CI-runner path on `poweredge-xubuntu`, installed **alongside** the
existing rootless-podman/dockershim pool documented one level up in
[`../README.md`](../README.md). Nothing here stops, disables, reconfigures, or
removes any part of that pool.

> **ZERO traffic is routed to this path.** No workflow in any fleet repository
> carries `runs-on: poweredge-xubuntu-k3s`. The one workflow that does
> ([`proof-of-life-workflow.yml`](proof-of-life-workflow.yml)) is a template
> that does not live under `.github/workflows/`, is `workflow_dispatch`-only,
> and is not a required check anywhere.

This is **phase 1** (work-item `livespec-s43svm.14`) of a six-phase migration
off rootless podman. The full rationale — why podman was chosen originally (a
*security* property, not a concurrency one), why its SQLite contention is a
structural rather than a tunable problem, and why ARC is GitHub's own
recommended scaled self-hosted-runner architecture — is the write-once design
record at
`livespec/plan/fleet-ci-runner-pool/research/k3s-arc-kueue-migration.md`.
Phases `.15`–`.19` (fair-share modelling, incremental per-repo cutover,
soak-under-load verification, full cutover, deletion of the podman stack) are
tracked as children of epic `livespec-s43svm` in the `livespec` repo's ledger.

## Files

| Path | Role |
|---|---|
| `install-k3s.sh` | Installs a single-node k3s server pinned to `v1.36.2+k3s1`, via the official `https://get.k3s.io` installer with `INSTALL_K3S_VERSION` pinned (the installer is fetched, not vendored; the *version* is what is pinned). Idempotent — skips the installer when the wanted version is already present. Verifies the node reaches `Ready` before exiting 0. |
| `install-arc.sh` | Installs the `gha-runner-scale-set-controller` chart (pinned `0.14.2`) into namespace `arc-systems`, converges the GitHub App `Secret` into `arc-runners`, then installs one `gha-runner-scale-set` (same pinned version) from the values file below. |
| `arc-runner-scale-set-values.yaml` | Helm values for the single proof-of-life `AutoscalingRunnerSet`: `minRunners: 0`, `maxRunners: 2`, non-root pod `securityContext`, and the routing name. |
| `install-kueue.sh` | Applies Kueue pinned to `v0.19.1` from its official release manifest URL (`kubectl apply --server-side`, referenced not vendored), waits for the controller, then applies the placeholder queue set. |
| `kueue-proof-of-life.yaml` | The minimum `ResourceFlavor` / `ClusterQueue` / `LocalQueue` graph that proves Kueue admits. Quotas are placeholders, **not** a capacity decision. |
| `proof-of-life-workflow.yml` | Non-gating `workflow_dispatch` template proving one real job runs on this path: prints `hostname` and `id`, fails if the in-container uid is 0, and fails if the serviceaccount projection is absent (i.e. if the job did not actually land on a Kubernetes pod). |

Install order: `install-k3s.sh` → `install-arc.sh` → `install-kueue.sh`.

## Pinned versions

| Component | Version | Install form |
|---|---|---|
| k3s | `v1.36.2+k3s1` | `INSTALL_K3S_VERSION=v1.36.2+k3s1` passed to the official `https://get.k3s.io` script |
| ARC controller | `0.14.2` | `oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set-controller` |
| ARC runner scale set | `0.14.2` | `oci://ghcr.io/actions/actions-runner-controller-charts/gha-runner-scale-set` |
| Kueue | `v0.19.1` | `.../kueue/releases/download/v0.19.1/manifests.yaml` |

Nothing floats `latest`. Each version is overridable by an environment variable
at the top of its script so a bump is a reviewed, single-line change.

## Routing — the scale-set name, not a label array

The podman pool registers each runner with the label triple
`["self-hosted", "local-ci", "poweredge"]`: a shared pool label plus a
host-unique one, as
`livespec/SPECIFICATION/non-functional-requirements.md` §"Self-hosted CI runner
host requirements" requires.

ARC's `gha-runner-scale-set` mode does not work that way. A workflow selects a
scale set by its **name**, as a bare string:

```yaml
runs-on: poweredge-xubuntu-k3s
```

A `runs-on: [self-hosted, poweredge-xubuntu-k3s]` array would match nothing and
the job would queue indefinitely. This is stated plainly because it contradicts
the label-array intuition the podman path teaches.

The host-uniqueness invariant is nonetheless satisfied, and more strongly than a
distinct label would satisfy it: `poweredge-xubuntu-k3s` overlaps **no** token
the existing pool uses, so no repository's `CI_RUNNER_LABELS` variable — the
mechanism by which any gating repo's `ci.yml` selects the podman pool — can
route a single job here. `local-ci-k3s` was reserved as this path's non-overlapping
shared-pool token for when phase `.15` grew it past one instance; the growth
landed instead on per-repository scale sets (`../k3s/phase2/`), and the
`local-ci-k3s` release was retired under `livespec-s43svm.28`.

## Credential model

Unchanged from the podman path, deliberately. The `thewoolleyman-ci-runners`
GitHub App's private key lives in the dedicated `github-ci-runners` 1Password
environment and is injected only by `/usr/local/bin/with-github-ci-runners-env.sh`
— the same wrapper `gate-runner-supervisor.service` uses, and that the
decommissioned podman lane's `ci-runner-supervisor.service` used (see
[`../README.md`](../README.md), "Credential model"). So `install-arc.sh` is run
under that wrapper:

```bash
sudo /usr/local/bin/with-github-ci-runners-env.sh -- \
  ci-runner/k3s-arc-kueue/install-arc.sh
```

It reads the same variable names the existing units read
(`GITHUB_APP_ID_CI_RUNNER`, `GITHUB_APP_INSTALLATION_ID_CI_RUNNER`,
`GITHUB_PRIVATE_KEY_CI_RUNNER`) and pipes them into the `arc-github-app`
Kubernetes `Secret` over stdin — never through argv, never to a file, never into
git. No new secret store is introduced and no credential value appears anywhere
in this tree.

ARC consumes App credentials natively, so this path needs no equivalent of the
podman path's `mint-jitconfig.sh`: the controller registers and scales the runner
set by calling the GitHub API itself.

`githubConfigUrl` is repository-level (`https://github.com/thewoolleyman/livespec`
by default). `thewoolleyman` is a personal account rather than a GitHub
organisation, so ARC's org-level and enterprise-level config URLs do not apply —
this matches the existing supervisor's own per-repo runner pools. Set
`GITHUB_CONFIG_URL` to point a first smoke test at a throwaway repository
instead.

## Resource envelope — free headroom, not total capacity

Measured on `poweredge-xubuntu` on 2026-08-15, while the podman pool was running
near its documented cap (~479–482 concurrent `runner@thewoolleyman-*` units;
the host-wide invariant is "482, never imply 964"). These are **free/available**
figures, not the host's totals:

| Resource | Host total | Free / available at measurement |
|---|---|---|
| CPU | 72 cores | ample idle headroom under the ~480-unit load |
| RAM | 188 GiB | ~90 GiB available (`free -h`) |
| Root disk | 458 GB | 306 GB free |
| `/var/cache/ci-runner` (`/dev/sda5`) | 658 GB | 624 GB free |

A single-node k3s control plane needs roughly one core and ~1 GiB at rest, so it
fits inside that headroom with a wide margin. None of k3s's default ports
(6443, 10250, 10251, 10252, 10257, 10259, 8472/udp, 2379, 2380) were bound by
anything on the host at measurement time, and k3s was not installed.

## Uninstall — what `k3s-uninstall.sh` actually does

The official installer writes `/usr/local/bin/k3s-uninstall.sh` (and
`/usr/local/bin/k3s-killall.sh`, which the uninstaller runs first). Running

```bash
sudo /usr/local/bin/k3s-uninstall.sh
```

performs, in order, verbatim per the pinned installer source
(`https://raw.githubusercontent.com/k3s-io/k3s/v1.36.2+k3s1/install.sh`,
functions `create_killall` and `create_uninstall`):

**The killall leg**, inlined into the uninstaller:

1. `systemctl stop` every `/etc/systemd/system/k3s*.service`, and `stop` every
   executable `/etc/init.d/k3s*`.
2. `kill -9` the whole process tree of every running
   `${K3S_DATA_DIR}/data/*/bin/containerd-shim` — i.e. every pod's container
   processes.
3. Force-unmount and `rm -rf`, deepest path first, everything mounted under
   `/run/k3s`, `/var/lib/kubelet/pods`, `/var/lib/kubelet/plugins`, and
   `/run/netns/cni-`.
4. Delete every `cni-*` network namespace (`ip netns delete`).
5. Delete the CNI network interfaces: every interface with `master cni0`, then
   `cni0`, `flannel.1`, `flannel-v6.1`, `kube-ipvs0`, `flannel-wg`,
   `flannel-wg-v6`. If `tailscale` is present it clears advertised routes.
6. `rm -rf /var/lib/cni/`.
7. Filter every `KUBE-`, `CNI-`, and flannel rule out of `iptables` and
   `ip6tables` (save, grep out, restore).

**The uninstall leg proper:**

8. `systemctl disable k3s`, `systemctl reset-failed k3s`, `systemctl
   daemon-reload` (and `rc-update delete` on OpenRC hosts).
9. Remove the systemd unit file and its `.env` file.
10. **Abort here if any other `k3s*.service` unit remains** — it prints
    `Additional k3s services installed, skipping uninstall of k3s` and exits
    without removing binaries or data.
11. Remove the `kubectl`, `crictl`, and `ctr` symlinks from the install bin dir
    (only if they are symlinks).
12. `rm -rf /etc/rancher/k3s`, `/run/k3s`, `/run/flannel`; recursively
    unmount-aware-remove `${K3S_DATA_DIR}` (default `/var/lib/rancher/k3s`);
    `rm -rf /var/lib/kubelet`.
13. Remove the `k3s` binary and `k3s-killall.sh`; remove itself on exit.
14. Remove the `k3s-selinux` package and its repo file on `yum` / `rpm-ostree` /
    `zypper` hosts (a no-op on this Ubuntu host).

Note what is **not** in that list: nothing touches podman, the `ci-runner` or
`ci-sup` users, `/usr/local/lib/ci-runner/`, any `runner@*.service` or
`ci-runner-*` unit, or `/var/cache/ci-runner`. Uninstalling k3s therefore leaves
the existing pool untouched — which is the property that makes this a safe
side-by-side install.

ARC and Kueue are removed with `helm uninstall` and `kubectl delete -f` against
the pinned manifest respectively, but removing k3s removes the cluster they live
in, so neither is a prerequisite of the above.
