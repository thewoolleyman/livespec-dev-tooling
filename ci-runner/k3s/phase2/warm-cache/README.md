# Warm uv cache — tier 1 of the cache tiers, on the k3s/ARC lane

Tier 1 of the three cache tiers in the livespec repo's
`plan/fleet-ci-runner-pool/research/design.md` ("Cache tiers, and the
volume that holds them"; maintainer-directed 2026-08-13: local caching of
the runner cache is in scope), re-scoped from the deleted podman lane to
this pool under `livespec-s43svm.2`, and re-realized as a hardlink seed
made at volume provisioning under `livespec-lvtu` (livespec plan
`ci-runner-pod-lifecycle-reliability`, research/005).

## What it is

A fleet-wide warm **uv** cache lower at
`/var/lib/rancher/k3s/storage/.warm/uv`, written by exactly one trusted
writer and hardlinked into every runner work volume at the moment the
volume is created:

| Path | Role |
|---|---|
| `warm-cache-populate.sh` | The populator. Clones or fast-forwards every routed repository's default branch and runs `uv sync --frozen --all-groups --no-install-project --no-install-workspace` against a fresh hardlink-seeded generation, then publishes it with one atomic symlink rename and prunes all but the newest two; for every repository with a `Cargo.lock` it also runs `cargo fetch --locked` through the crates proxy (`../crates-proxy/`) to pre-warm it, and builds the default branch with sccache as the compilation cache's one writer (`../sccache/`) when the branch or toolchain changed. Never builds or installs a project; only locked third-party dependencies land in the cache. Its header carries the generation/publish design and the per-repository fail-soft rule. |
| `warm-cache-cronjob.yaml` | Namespace `ci-warm-cache` + the `warm-cache-populate` CronJob (every 30 min, `concurrencyPolicy: Forbid`), running the populator in the same fabro sandbox image the fleet's CI jobs execute in (the `python-rust` layer, so `cargo` is present), with the warm root mounted read-WRITE — the only mount of that path in the cluster. |
| `install-warm-cache.sh` | Derives the routed-repository list from `../arc/values-*.yaml` (every per-repo scale set's `githubConfigUrl`) into the `warm-cache-repos` ConfigMap, applies the CronJob, converges its script ConfigMap from the file above, runs one populate immediately and waits for it, then converges `arc-hook-pod-template` via `../arc/converge-hook-pod-template.sh`. Idempotent; re-run after adding a routed repository. |
| `../local-path-provisioner/local-path-provisioner.yaml` | The reader side, in the fleet-owned local-path provisioner's `local-path-config` ConfigMap: its `setup` script runs inside the provisioner's busybox helper pod, as root, on the volume's parent mount, while a work volume is being provisioned; it resolves the `uv` link once, `cp -al`s that generation into `<volume>/_warm/uv` (hardlinks, not bytes), and opens the new directories to 0777. Its header records the helper-pod facts the script rests on, read from the provisioner's v0.0.36 source. |
| `../arc/hook-pod-template.yaml` | Sets `UV_CACHE_DIR=/__w/_warm/uv` in the job container, pointing uv at that seed, and `UV_LINK_MODE=copy` so uv copies rather than hardlinks a read-only shared inode into the job's `.venv` (see the hazard note below). Nothing else for this tier: no host mount and no copy; its `postStart` serves the cargo and compilation tiers, and under the fleet kill switch removes this volume's seed so uv runs cold. |

## Where it lives, and why it moved

The warm root is a hidden sibling of the `pvc-*` directories on the
`ci-workvols` tier — the provisioner's node path,
`/var/lib/rancher/k3s/storage` — and no longer on the `ci-cache` volume it
started on (`/var/cache/ci-runner/warm`, retired). A hardlink is legal only
within one filesystem AND one mount: `link()` across two bind mounts of
even the same filesystem fails with `EXDEV`. So the seed can neither run
inside a pod, which sees the warm root and its work volume as two mounts,
nor link across tiers. The provisioner's helper pod hostPath-mounts the
node path once, at the same absolute path, and sees the warm root and the
new volume directory under that ONE mount — the only place in the system
where the link is possible (the provisioner manifest's header names the
source lines). Three consequences, each recorded where it bites: the warm
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
"Lesson"). The hardlink seed replaced it under `livespec-lvtu`: the same
trust tiering in intent — a job reads the lower and never writes it — but,
as of 2026-09-04, NOT enforced (see "The hazard" below). uv never needs to
write a shared inode: it writes a new cache entry to a temporary path and
renames it into place, never rewriting an existing entry, so a job's `uv
sync` leaves every shared inode exactly as it found it (verified locally
in research/005; the populator has relied on the same property between
its own generations since the tier shipped). The seed's directories are
fresh per-volume inodes (0777, so the job can add and rename entries) and
so are uv's lock files (the only world-writable files in a generation;
re-created empty per volume, because `flock()` locks the inode and a
hardlinked lock file would make every job's cache locks contend with
every other job's and the populator's). The
generation/symlink publish protocol exists
because seeds link while the populator may be writing: the seed resolves
the `uv` link once before it starts linking, the populator keeps the
previous generation for one cycle, and a seeded volume's links outlive
even a pruned generation.

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
`chmod g+rw` every entry — ~160k hardlinks per start, and a mutation of
the inodes every generation and every other seeded volume share. Every
`../arc/values-*.yaml` therefore sets `fsGroupChangePolicy:
OnRootMismatch`, and the setup script leaves the volume root exactly as
`Always` would have (gid 1000, mode 2777), so the kubelet finds no
mismatch and skips the walk (kubelet source, `pkg/volume/local` and
`pkg/volume/volume_linux.go`, v1.36.2). A mismatch is slow, not broken.

**The hazard, and the open decision.** A seeded file IS a generation
inode, and the workflow pod's job runs as root in a user namespace whose
work volume is idmapped so that uid 0 inside is uid 0 on the volume: the
root-owned generation is writable in place from every job — a test that
patches an installed package, a tool that rewrites a `.pth`, anything
opening a cache file for writing — and a write would reach the fleet-wide
generation for every later job on the node until the next populate. The
specification's "Runner-pool build cache tiers" clause
(`SPECIFICATION/non-functional-requirements.md`, "Trust by construction")
says a job MUST NOT be able to write any shared cache. Two mechanisms are
in place and one is missing:

- **`UV_LINK_MODE=copy`** in the hook template, beside `UV_CACHE_DIR`:
  uv's default link mode hardlinks cache files into the job's `.venv`, so
  the one place a job routinely writes installed files would otherwise be
  the generation itself. Copy mode gives the venv private copies. Its cost
  is the venv's own bytes per job; `livespec-lvtu`'s acceptance run wrote
  ~630 MB per job after the seed (checkout and venv together).
- **Per-volume lock files** (above), so no job's `flock()` lands on a
  shared inode.
- **Missing: the seeded inodes themselves are writable.** Owning every
  generation as a uid no workflow pod maps (200000) was implemented and
  applied live on 2026-09-04 and broke every job within a minute: uv's
  cache init opens `CACHEDIR.TAG` for writing, and Linux refuses ANY
  write-open, unlink or rename-over on an inode whose owner the caller's
  user namespace does not map (`inode_permission` and `may_delete`,
  `HAS_UNMAPPED_ID`), and refuses creates in a directory with an unmapped
  owner. Making it work would mean per-volume copies of every file uv
  rewrites at init, per-volume ownership of every seeded directory, and
  accepting that any uv operation that must replace or remove a seeded
  entry (an index-metadata refresh on re-resolution, a `git fetch` into a
  seeded bare repository) fails hard rather than degrading. The clean
  alternative is a filesystem with reflinks (XFS or btrfs) on the
  `ci-workvols` tier, where the seed becomes a copy-on-write copy: the job
  owns every inode it sees, writes never reach the generation, and
  `UV_LINK_MODE=copy` becomes unnecessary — at the cost of reformatting
  that tier and a per-start cost that scales with the file count like the
  hardlink seed does. Which of these (or a re-based clause) the fleet
  adopts is the maintainer's decision, recorded with the measurements in
  the livespec plan `ci-runner-pod-lifecycle-reliability`, research/006.
  Until it lands, `../isolation/cache-negative-tests.sh` case 1 reports
  the violation on its six-hourly timer and stays red on purpose.

It is fail-soft in every direction, by absence: no warm root or no
published generation (a node before its first populate), or a seed that
failed, leaves NO `_warm/uv`; uv creates a cold cache there and the job
runs. There is deliberately no fallback copy anywhere — not in the
provisioner, not in the hook template.

## What it buys, measured

Against the `livespec` lockfile, same host class:

| Step | Cold | Byte copy (2026-08-23, 379 MB) | Byte copy (2026-09-04, 1,388 MB / 159k files) | Hardlink seed (2026-09-04, same tree) |
|---|---|---|---|---|
| bring the lower into the work volume | — | 0.8 s | 6.8 s, 2,153 MB written, 237k ops (~9 s inside the pod, holding the workflow container in `ContainerCreating`) | 2.3 s, 269 MB of metadata, 69k ops, during PVC provisioning, absorbed by the runner pod's volume wait |
| `uv sync --all-groups --frozen` | 7.9 s (matches the 7–9 s per job read off live k3s-lane runs) | 0.5 s | 0.5 s | 0.5 s with hardlinks; with `UV_LINK_MODE=copy` the venv's bytes are copied instead — to be measured |

The 2026-09-04 columns are research/005's measurement of `cp -rp` against
`cp -al` on the live generation, on one filesystem, on the same array. The
seed's cost scales with the file count, not the bytes, and the separate
generation-trim item under `livespec-ifwnqj` targets under 1 s and under
100 MB per start.

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
  /var/lib/rancher/k3s/storage/pvc-*/_warm/uv`, and `stat -c %h` of any
  file there is 2 or more (its inode is the generation's). A workflow
  pod's `kubectl describe pod <runner>-workflow`
  shows `UV_CACHE_DIR` and `UV_LINK_MODE` and no warm-cache mount.
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
