# Warm uv cache — tier 1 of the cache tiers, on the k3s/ARC lane

Tier 1 of the three cache tiers in the livespec repo's
`plan/fleet-ci-runner-pool/research/design.md` ("Cache tiers, and the
volume that holds them"; maintainer-directed 2026-08-13: local caching of
the runner cache is in scope), re-scoped from the deleted podman lane to
this pool under `livespec-s43svm.2`, re-realized as a hardlink seed made
at volume provisioning under `livespec-lvtu` (livespec plan
`ci-runner-pod-lifecycle-reliability`, research/005), and made private per
volume as a reflink copy on the XFS `ci-workvols` tier under
`livespec-dev-tooling-hmv2bo` (that plan's research/006, option (a)).

## What it is

A fleet-wide warm **uv** cache lower at
`/var/lib/rancher/k3s/storage/.warm/uv`, written by exactly one trusted
writer and reflink-copied into every runner work volume at the moment the
volume is created:

| Path | Role |
|---|---|
| `warm-cache-populate.sh` | The populator. Clones or fast-forwards every routed repository's default branch and runs `uv sync --frozen --all-groups --no-install-project --no-install-workspace` against a fresh hardlink-seeded generation, then publishes it with one atomic symlink rename and prunes all but the newest two; for every repository with a `Cargo.lock` it also runs `cargo fetch --locked` through the crates proxy (`../crates-proxy/`) to pre-warm it, and builds the default branch with sccache as the compilation cache's one writer (`../sccache/`) when the branch or toolchain changed. Never builds or installs a project; only locked third-party dependencies land in the cache. Its header carries the generation/publish design and the per-repository fail-soft rule. |
| `warm-cache-cronjob.yaml` | Namespace `ci-warm-cache` + the `warm-cache-populate` CronJob (every 30 min, `concurrencyPolicy: Forbid`), running the populator in the same fabro sandbox image the fleet's CI jobs execute in (the `python-rust` layer, so `cargo` is present), with the warm root mounted read-WRITE — the only mount of that path in the cluster. |
| `install-warm-cache.sh` | Derives the routed-repository list from `../arc/values-*.yaml` (every per-repo scale set's `githubConfigUrl`) into the `warm-cache-repos` ConfigMap, applies the CronJob, converges its script ConfigMap from the file above, runs one populate immediately and waits for it, then converges `arc-hook-pod-template` via `../arc/converge-hook-pod-template.sh`. Idempotent; re-run after adding a routed repository. |
| `../local-path-provisioner/local-path-provisioner.yaml` | The reader side, in the fleet-owned local-path provisioner's `local-path-config` ConfigMap: its `setup` script runs inside the provisioner's helper pod (`ubuntu:24.04` by digest, for GNU `cp`), as root, on the volume's parent mount, while a work volume is being provisioned; it resolves the `uv` link once, `cp -a --reflink=always`s that generation into `<volume>/_warm/uv` (new inodes sharing the generation's blocks copy-on-write; no data bytes), and opens the new directories to 0777. Its header records the helper-pod facts the script rests on, read from the provisioner's v0.0.36 source. |
| `../arc/hook-pod-template.yaml` | Sets `UV_CACHE_DIR=/__w/_warm/uv` in the job container, pointing uv at that seed. `UV_LINK_MODE` is no longer set: every seeded inode is the job's own, so uv's default link mode into the `.venv` is private (see "The hazard, closed" below). Nothing else for this tier: no host mount and no copy; its `postStart` serves the cargo and compilation tiers, and under the fleet kill switch removes this volume's seed so uv runs cold. |

## Where it lives, and why it moved

The warm root is a hidden sibling of the `pvc-*` directories on the
`ci-workvols` tier — the provisioner's node path,
`/var/lib/rancher/k3s/storage` — and no longer on the `ci-cache` volume it
started on (`/var/cache/ci-runner/warm`, retired). A reflink is legal
only within one filesystem (`FICLONE` across filesystems is `EXDEV`), and
the hardlink seed it grew out of was legal only within one filesystem AND
one mount. So the seed cannot link across tiers, and it runs where the
warm root and the new volume directory are both in reach and no job is:
the provisioner's helper pod hostPath-mounts the node path once, at the
same absolute path (the provisioner manifest's header names the source
lines). Three consequences, each recorded where it bites: the warm
cache moves WITH the work volumes when they move to new media (the phase2
README's "Storage layout"); the boot-time storage sweep keeps it, since it
removes only `pvc-*` entries (`../storage-sweep/`); and the CronJob's
`DirectoryOrCreate` hostPath creates the subtree (0755 root) on its first
run after a rebuild, so until the first populate publishes a generation
every job runs cold, by design.

## Why this shape, and not the podman lane's

The podman lane mounted per-repository `uv`/`cargo`/`target` lowers as the
lower layer of an overlay whose upper was per-job and discarded, so a job
could read the warm cache and never mutate it. Two facts force a different
realization here, both measured on 2026-08-23:

- **uv refuses a read-only cache outright** (`Failed to initialize cache
  ... Permission denied`), so a read-only mount alone serves nothing.
- **An unprivileged workflow pod cannot mount an overlay** to give uv a
  writable upper, and the `ci-runner-workflow` AppArmor profile's
  `deny mount` would refuse it even if the pod had the capability.

So the writable upper is the job's own ephemeral work volume, pre-seeded
with the lower. The first realization (2026-08-23) seeded it by a byte
copy in the job container's `postStart` — 379 MB and 0.8 s when it
shipped, 1.9 GB / 160k files / ~9 s per start by 2026-09-04 (see
"Lesson"). The hardlink seed replaced it under `livespec-lvtu`
(2026-09-04): metadata-only and fast, but its inodes WERE the
generation's, so the trust tiering held by uv's write discipline alone
(see "The hazard, closed"). The reflink seed replaced that under
`livespec-dev-tooling-hmv2bo` (2026-09-06), once the `ci-workvols` tier
became XFS with reflink: `cp -a --reflink=always` gives every file a new
inode of the volume whose data blocks are shared copy-on-write with the
generation's until either side writes. A job owns every inode it sees;
its writes land in its own volume; the generation is reachable from no
pod. The seed's directories are per-volume inodes opened to 0777 so a
non-root reader can add entries, and uv's lock files need no special
handling any more — each volume's lock inode is its own, so `flock()`
never contends across volumes. The generation/symlink publish protocol
exists because seeds copy while the populator may be writing: the seed
resolves the `uv` link once before it starts, the populator keeps the
previous generation for one cycle, and a seeded volume's copies outlive
even a pruned generation (the blocks stay referenced).

What the copy needed that the seed does not: no `initContainers` question
(the copy was a `postStart` precisely because the hook template assigns
`initContainers` wholesale and newer hook releases add their own `fs-init`
init container), no `lifecycle` key at all, no `/bin/sh` + `cp`
requirement on `container:` images, and no hold of the workflow container
in `ContainerCreating`. With `WaitForFirstConsumer` the seed happens
during PVC provisioning — after the runner pod is scheduled and before it
starts — so the runner pod's volume wait absorbs the ~2 s seed and the
workflow container is never held.

**The runner pod's `fsGroup` and the seed.** The runner pod mounts the
same volume with `fsGroup: 1000`, and the kubelet's default policy
(`Always`) would walk the entire volume on that first mount, `chgrp` and
`chmod g+rw` every entry — ~190k inodes per start (under the hardlink seed
this also mutated the inodes every generation shared; under the reflink
seed it is a cost, not a mutation of anything shared). Every
`../arc/values-*.yaml` therefore sets `fsGroupChangePolicy:
OnRootMismatch`, and the setup script leaves the volume root exactly as
`Always` would have (gid 1000, mode 2777), so the kubelet finds no
mismatch and skips the walk (kubelet source, `pkg/volume/local` and
`pkg/volume/volume_linux.go`, v1.36.2). A mismatch is slow, not broken.

**The hazard, closed (2026-09-06).** From 2026-09-04 to 2026-09-06 a
seeded file WAS a generation inode, and the workflow pod's job runs as
root in a user namespace whose work volume is idmapped so that uid 0
inside is uid 0 on the volume: the root-owned generation was writable in
place from every job — a test that patches an installed package, a tool
that rewrites a `.pth`, anything opening a cache file for writing — and a
write would have reached the fleet-wide generation for every later job on
the node until the next populate. The specification's "Runner-pool build
cache tiers" clause (`SPECIFICATION/non-functional-requirements.md`,
"Trust by construction") says a job MUST NOT be able to write any shared
cache. On ext4 with hardlinks no owner satisfies it: uid 0 is writable;
owning every generation as a uid no workflow pod maps (200000) was
applied live on 2026-09-04 and broke every job within a minute — uv's
cache init opens `CACHEDIR.TAG` for writing, and Linux refuses ANY
write-open, unlink or rename-over on an inode whose owner the caller's
user namespace does not map (`inode_permission` and `may_delete`,
`HAS_UNMAPPED_ID`), and refuses creates in a directory with an unmapped
owner; and per-pod id ranges differ, so no fixed non-root host uid is
mapped in every pod. `../isolation/cache-negative-tests.sh` case 1
reported the violation on its six-hourly timer for those two days, red on
purpose. The options and measurements are in the livespec plan
`ci-runner-pod-lifecycle-reliability`, research/006; the maintainer took
its recommendation, option (a):

- **The `ci-workvols` tier is XFS with reflink** (`reflink=1`) since
  2026-09-06 — reformatted live by `../storage-layout/migrate-tier.sh`
  (`switch-live` → `finish-live` → `reclaim`; `.ai/ci-node-storage-tiers.md`),
  the filesystem type decided per role in that script's `role_fstype`.
- **The seed is a reflink copy** (`cp -a --reflink=always`, GNU `cp` from
  the `ubuntu:24.04` helper image): every seeded file is an inode of the
  job's own volume, its data blocks shared copy-on-write with the
  generation until either side writes. A job's write lands in the volume.
  Verified on the node 2026-09-06: a byte appended to a seeded copy changed
  the copy's checksum and left the generation's unchanged.
- **`UV_LINK_MODE=copy` is gone** from the hook template: it existed only
  because a hardlinked venv file would have BEEN a generation inode. uv's
  default link mode (clone on a reflink filesystem) now links into the
  venv privately, and the ~630 MB of venv bytes per job that copy mode
  cost (`livespec-lvtu`'s acceptance run) go away.
- **Case 1 of the negative test asserts the closure** from inside a routed
  job: no inode under the seed has a link outside it (uv's own intra-cache
  hardlinks are preserved within the copy, so the check groups links by
  inode rather than reading a raw link count), the copy's extents are
  shared with the generation (a reflink, not a byte copy), and a new entry
  is still creatable. The negative control (`negative-control-job.yaml`)
  mounts the warm root itself, whose files are hardlinked to the previous
  generation, and goes red on the first of those.

What it costs: the seed is inodes and metadata, not data bytes, but it is
a per-file `FICLONE` plus inode create — measured 2026-09-06 on the live
2.1 GB / 191k-file generation, 13.3 s and 165 MB of metadata against the
hardlink seed's ~3 s and 135–282 MB, paid during PVC provisioning before
the runner pod starts (never on the workflow container). Splitting the
copy across top-level entries in parallel gained only ~25% because 83% of
the files sit in `archive-v0`, so the copy is kept serial; the lever is
the file count, which the from-empty generation build (`livespec-41w4`)
bounds. On a tier without reflink the copy fails and the volume gets no
seed — cold, never a byte copy.

It is fail-soft in every direction, by absence: no warm root or no
published generation (a node before its first populate), or a seed that
failed, leaves NO `_warm/uv`; uv creates a cold cache there and the job
runs. There is deliberately no fallback copy anywhere — not in the
provisioner, not in the hook template.

## What it buys, measured

Against the `livespec` lockfile, same host class:

| Step | Cold | Byte copy (2026-08-23, 379 MB) | Byte copy (2026-09-04, 1,388 MB / 159k files) | Hardlink seed (2026-09-04, same tree) | Reflink seed (2026-09-06, 2.1 GB / 191k files, XFS on NVMe) |
|---|---|---|---|---|---|
| bring the lower into the work volume | — | 0.8 s | 6.8 s, 2,153 MB written, 237k ops (~9 s inside the pod, holding the workflow container in `ContainerCreating`) | 2.3 s, 269 MB of metadata, 69k ops, during PVC provisioning, absorbed by the runner pod's volume wait | 13.3 s, 165 MB of metadata, during PVC provisioning; every inode the job's own |
| `uv sync --all-groups --frozen` | 7.9 s (matches the 7–9 s per job read off live k3s-lane runs) | 0.5 s | 0.5 s | 0.5 s with hardlinks; with `UV_LINK_MODE=copy` the venv's bytes were copied instead | 0.5 s expected; uv clones into the venv (no `UV_LINK_MODE`) — to be measured on the standing `cache.warm-copy` query |

The 2026-09-04 columns are research/005's measurement of `cp -rp` against
`cp -al` on the live generation, on one filesystem, on the same array; the
2026-09-06 column is `cp -a --reflink=always` on the reformatted XFS tier
("The hazard, closed"). A seed's cost scales with the file count, not the
bytes, and the separate generation-trim item under `livespec-ifwnqj`
(`livespec-41w4`) is what brings it down.

About 6.5 s per job on the sync alone, and — the part the wall-clock
number undersells — no PyPI round trip per job, which is the largest
unretried-fetch surface the fleet's workflow comments name. The workflow
files themselves assumed this tier existed: the fleet's `Restore uv cache
(hosted lane only — self-hosted uses ~/.cache/uv)` steps skip
`actions/cache` on the self-hosted lane on the premise of a warm on-host
cache, a premise that was true on the podman lane and false on ephemeral
ARC pods until this tier.

## Cargo: served, not copied

The podman-era tier also warmed `cargo` registry and `target` lowers, and
until 2026-09-04 this lane was uv-only on the strength of a lone-build
benchmark (`cargo clippy` 37 s cold here vs 53 s warm-cached hosted) that the
console's full matrix contradicted (ten concurrent jobs each cold-rebuilding
the same dependency graph: 883 s vs 427 s hosted; `livespec-dev-tooling-9mp`).
The cargo half now exists, but NOT as a lower copied into pods: per-job start
writes are the pool's measured disk knee, and cargo — unlike uv — can be
pointed at a registry URL. So `../crates-proxy/` serves crates.io from the
host, the hook template's `postStart` writes `/.cargo/config.toml` in the job
container to use it, and THIS populator pre-warms it (`cargo fetch --locked`
per routed `Cargo.lock`, through the proxy, into a throwaway `CARGO_HOME`) so
the cold cost lands on this timer and not on a job. The compile-time half of
the Rust problem is the compilation cache (`../sccache/`), whose ONE writer
is also this populator: when the sccache binary is mounted and the writer
credential is projected, it builds each routed Rust repository's default
branch at the job's own checkout path with sccache as the writer, gated by a
marker key in redis so an unchanged branch costs nothing (the populator's
header has the details). Design and the live verification:
`plan/ci-runner-cache-tiers/research/005-a1-crates-proxy-verification.md`.

## Guardrails on the writer build

The compilation-cache writer build compiles a Rust repository for minutes
on the node the jobs use, so v054's populator-guardrails clause bounds it
four ways, all in `warm-cache-cronjob.yaml` and the populator: a CPU limit
on the container (6 cores) with the build at the repository's own
`build.jobs` cap; `nice -n 19 ionice -c 3` under the jobs; an
ADMITTED-JOB GATE — before each build the populator sums Kueue's
ClusterQueue `admittedWorkloads` through the API with its read-only
ServiceAccount and skips the build when the sum is above
`POPULATE_ADMITTED_JOB_THRESHOLD` (16, half the churn-slot cap; the
CronJob's comment carries the derivation), logging the skip and counting it
in the manifest as `sccache_skipped_busy`; and a per-generation MANIFEST
(`populate-manifest.json`) with duration, per-step counts, the admitted
count it read, and the toolchain. An unreadable admitted count is treated
as busy AND recorded as a failed step, so a broken read reaches the
populate-failing trigger instead of silently starving the cache.

## Operating it

- **Install / re-converge**: `KUBECONFIG=/etc/rancher/k3s/k3s.yaml
  ./install-warm-cache.sh` on the host. Re-run after adding a routed
  repository (it re-derives the list) or changing the populator or the
  hook template. Then `../arc/recycle-scale-set-runners.sh <scale-set>` for
  any scale set with idle runners, as after any values change. The seed
  itself is part of the provisioner manifest and is applied by the boot
  converge (`../reconstruct/converge-ci-stack.sh`, step 3); after editing
  the setup script, run the converge or `kubectl apply -f
  ../local-path-provisioner/local-path-provisioner.yaml`. The helper pod
  reads the ConfigMap's `setup` key when it is created, so the next volume
  uses the new script with no provisioner restart.
- **Host gauges**: every run writes `populate-manifest.json` beside the
  generations; `ci-runner/observability/ci-cache-gauges.sh` turns it and the
  current generation's age and size into `livespec.ci_cache.{generation_*,populate.*}`
  every 5 min (as capability-less root, since the warm root sits under the
  provisioner's 0700 storage directory; its unit's header), and the
  `CI warm cache stale` / `CI cache populate failing` triggers in
  `ci-runner/observability/triggers/` read those.
- **Is it live?** `kubectl -n ci-warm-cache get cronjob,jobs` shows the
  schedule and the last runs; `sudo ls -la /var/lib/rancher/k3s/storage/.warm`
  on the host shows the `uv -> uv-generations/<stamp>` link and the
  retained generations. A new work volume shows the seed: `sudo ls -la
  /var/lib/rancher/k3s/storage/pvc-*/_warm/uv`; `stat -c %h` of a file
  there is 1 (its inode is the volume's own) and `filefrag -v` on it shows
  `shared` extents (a reflink of the generation). A workflow pod's
  `kubectl describe pod <runner>-workflow` shows `UV_CACHE_DIR`, no
  `UV_LINK_MODE`, and no warm-cache mount.
- **A repository failed to sync**: the CronJob's last Job is red and its
  log names the repository. The generation still published (fail-soft per
  repository), so the other repositories are still warm.
- **Growth**: a generation is hardlink-seeded from its predecessor, so the
  cache accumulates every locked version ever synced, and the seed's
  per-start cost grows with its file count; when that matters, delete the
  `uv-generations/` directory and the `uv` link on the host and run one
  populate — the next generation starts empty and re-fetches the current
  locks only. Bounding this mechanically is the separate generation-trim
  item under `livespec-ifwnqj`.
- **Bump the image** in lockstep with the fleet's fabro sandbox pin:
  `WARM_CACHE_IMAGE=... ./install-warm-cache.sh`, or edit the CronJob
  manifest.

## Lesson: a per-start byte copy grows silently with the cache

The copy this seed replaced cost 0.8 s per start when it shipped
(2026-08-23, 379 MB) and ~9 s per start twelve days later (1.9 GB, 160k
files), because a hardlink-seeded generation accumulates every version
ever locked and nothing bounded it. By 2026-09-04 one start was writing
2.5 GB and creating 170k inodes, the copy was ~9 s of a 56 s pod lifetime
and held the workflow container in `ContainerCreating` for all of it, and
under a six-start burst it ran at 44 MB/s — costing more than the 7 s of
`uv sync` it saved whenever the pool was busy (research/005 §2, §5). The
failure mode is that nothing FAILS: the copy always exits 0, the cache
"works", and the cost shows up only as a start latency that drifts upward
with the fleet's release cadence. The rule this leaves behind: a per-start
cost must be metadata-only — links, not bytes — and bounded by something
that is checked and alarmed; a byte copy whose size is a free variable of
another process's growth must never ship on the start path again. The
sibling items under `livespec-ifwnqj` bound the generation (every build
from empty), emit its size and the seed cost on every build, and fail on
unreferenced entries.

A second lesson from the switchover (2026-09-04): **a `postStart` whose
failure path can print without bound kills the pod.** For about a minute
a runner pod created before the converge still carried the copying
template while the provisioner already seeded new volumes owned by a uid
the pod did not map; the copy hit ~160k permission errors, the hook's
output exceeded the kubelet's 16 MiB gRPC message limit
(`ResourceExhausted`), the kubelet failed the hook and the pod, and the
job died with "pod failed to come online". The copy always exited 0 and
was "fail-soft" by design; its stderr was not. The current `postStart`
prints nothing on its fail-soft paths.

## Tiers 2 and 3

The other two tiers from the design record are not here: tier 2, a local
GitHub Actions cache service (`livespec-s43svm.3`), and tier 3, a Nix store
and binary cache for homelab's builds (`livespec-s43svm.4`). Each is tracked
on its own work-item.
