# Warm uv cache — tier 1 of the cache tiers, on the k3s/ARC lane

Tier 1 of the three cache tiers in the livespec repo's
`plan/fleet-ci-runner-pool/research/design.md` ("Cache tiers, and the
volume that holds them"; maintainer-directed 2026-08-13: local caching of
the runner cache is in scope), re-scoped from the deleted podman lane to
this pool under `livespec-s43svm.2`, re-realized as a hardlink seed made
at volume provisioning under `livespec-lvtu` (livespec plan
`ci-runner-pod-lifecycle-reliability`, research/005), made private per
volume as a reflink copy on the XFS `ci-workvols` tier under
`livespec-dev-tooling-hmv2bo` (that plan's research/006, option (a)), and —
since `livespec-41w4` (Carriers F2/F3/F4a of the same plan) — built FROM
EMPTY on every lock change through a host-served PyPI files proxy, verified
against the routed lockfiles, refused over a fixed budget, and measured on
every run.

## What it is

A fleet-wide warm **uv** cache lower at
`/var/lib/rancher/k3s/storage/.warm/uv`, written by exactly one trusted
writer and reflink-copied into every runner work volume at the moment the
volume is created:

| Path | Role |
|---|---|
| `warm-cache-populate.sh` | The populator. Clones or fast-forwards every routed repository's default branch, hashes its `uv.lock`, and — when any lock changed, the published generation no longer verifies, or it is older than 24 h — builds a NEW generation from an EMPTY directory: per repository it rewrites the file-host prefix in its own clone's lock to the PyPI files proxy and runs `uv sync --frozen --all-groups --no-install-project --no-install-workspace` with that generation as `UV_CACHE_DIR`; runs the verifier; checks the budget; writes the generation's manifest; publishes with one atomic symlink rename; prunes to the newest two. A run with nothing changed verifies the live generation and records `rebuilt=0`. Every run writes `last-run.json` for the host sweep. For every repository with a `Cargo.lock` it also runs `cargo fetch --locked` through the crates proxy (`../crates-proxy/`) and builds the default branch with sccache as the compilation cache's one writer (`../sccache/`) when the branch or toolchain changed. Its header carries the whole control flow and the exit codes. |
| `verify-uv-cache.py`, `uv_cache_layout.py` | The verifier (stdlib Python, both files shipped in the populator's ConfigMap and mounted together at `/scripts`): maps every entry of a uv 0.9.x cache back to a `(name, version)` and fails on any entry no routed lock references. The layout module holds the bucket table and the scanners; the CLI holds the lock union, the build-dependency closure and the report — split at the repo's per-file LLOC ceiling. "Verifier" below. |
| `warm-cache-cronjob.yaml` | Namespace `ci-warm-cache`, the `warm-cache-budget` ConfigMap (the two budget numbers and their derivation), and the `warm-cache-populate` CronJob (every 30 min, `concurrencyPolicy: Forbid`), running the populator in the same fabro sandbox image the fleet's CI jobs execute in (the `python-rust` layer, so `cargo` is present), with the warm root mounted read-WRITE — the only mount of that path in the cluster — and the proxy's store mounted read-only for the hit-ratio count. |
| `pypi-proxy/` | The PyPI FILES proxy every rebuild fetches through: one nginx `proxy_cache` in front of `files.pythonhosted.org` on the `ci-cache` tier, read only by the populator. "The PyPI files proxy" below and its own README. |
| `converge-warm-cache.sh` | The idempotent converge of every cluster object here: the proxy (with a bounded rollout wait), the budget ConfigMap + CronJob, the `warm-cache-repos` ConfigMap derived from `../arc/values-*.yaml`, and the script ConfigMap from the populator AND the verifier. Run by the boot converge and by `install-warm-cache.sh`. |
| `install-warm-cache.sh` | The attended superset: the converge, one populate Job run immediately and waited for, then `arc-hook-pod-template` converged via `../arc/converge-hook-pod-template.sh`. Idempotent; re-run after adding a routed repository. |
| `../local-path-provisioner/local-path-provisioner.yaml` | The reader side, in the fleet-owned local-path provisioner's `local-path-config` ConfigMap: its `setup` script runs inside the provisioner's helper pod (`ubuntu:24.04` by digest, for GNU `cp`), as root, on the volume's parent mount, while a work volume is being provisioned; it resolves the `uv` link once, `cp -a --reflink=always`s that generation into `<volume>/_warm/uv` (new inodes sharing the generation's blocks copy-on-write; no data bytes), and opens the new directories to 0777. Its header records the helper-pod facts the script rests on, read from the provisioner's v0.0.36 source. |
| `../arc/hook-pod-template.yaml` | Sets `UV_CACHE_DIR=/__w/_warm/uv` in the job container, pointing uv at that seed. `UV_LINK_MODE` is no longer set: every seeded inode is the job's own, so uv's default link mode into the `.venv` is private (see "The hazard, closed" below). Nothing else for this tier: no host mount and no copy; its `postStart` serves the cargo and compilation tiers, and under the fleet kill switch removes this volume's seed so uv runs cold. |
| `../runner-pod-lifecycle/scan-runner-pod-lifecycle.sh` | The emitter of this tier's build metrics: reads `last-run.json` on its 5-minute sweep and posts `livespec.ci_warm.*` once per new run. "Metrics" below. |

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
every job runs cold, by design. The populator builds wherever the seed
reads: `WARM_ROOT` is the one path both sides share.

## Every generation is built from empty

Until 2026-09-06 a new generation was hardlink-seeded from its predecessor
(`cp -al`) and nothing pruned it, so the cache accumulated every version
ever locked: 379 MB / 8,070 files on 2026-08-23, 1,388 MB / 159,409 files
on 2026-09-04 (research/005 §5), and the per-start seed cost grew with the
file count. The only remedy was a manual delete. The maintainer's
2026-09-04 amendment to `livespec-ifwnqj` — "there should be metrics on the
trimming and checks to ensure there's not useless stuff in it" — is what
this section realizes, as four rules the populator enforces mechanically:

1. **From empty.** A rebuild starts as an empty directory and holds only
   what `uv sync --frozen` of the routed repositories' CURRENT lockfiles put
   there. The published generation is the union of current locks BY
   CONSTRUCTION — no trim step, no pruning heuristic, nothing to drift.
2. **Verified before publish.** `verify-uv-cache.py` maps every entry back
   to a `(name, version)` and fails the publish on any entry no routed lock
   references (the entries are named in the Job log, the directory is kept
   as `<stamp>.unverified` for one cycle, the symlink is untouched, exit 1).
3. **Refused over budget.** Bytes and regular files are each checked
   against a fixed budget; over either, the directory is renamed
   `<stamp>.refused`, the previous generation stays live, exit 3.
4. **Measured.** Every run writes `last-run.json` (rebuilt / refused /
   verified, sizes, the trim against the previous generation, the proxy hit
   ratio) and the host sweep emits it as `livespec.ci_warm.*`.

A run that changes nothing builds nothing: every routed `uv.lock` is
sha256-hashed against the published generation's manifest
(`<generation>/.warm-manifest.json`, which names only the locks that
synced successfully — a failed repository forces the next rebuild), and
when every lock is unchanged AND the live generation still verifies AND it
is younger than `WARM_FORCE_REBUILD_SECONDS` (86,400 s), the run records
`rebuilt=0` and touches the generation directory's mtime, so
`ci-cache-gauges.sh`'s `generation_age_s` reads "last published or
verified current" — what the `CI warm cache stale` trigger asks. The
forced rebuild past 24 h keeps the from-empty path exercised whether or
not the fleet's locks move.

Fail-soft per repository is kept, with one change of meaning: a repository
whose sync fails is skipped and the generation still publishes (if it
verifies and fits), but under from-empty its packages are simply ABSENT
from the new generation — its jobs run cold for one tick, and the next
tick rebuilds because its lock is missing from the manifest. When NOTHING
synced and something failed (a forge or PyPI outage), the new generation
is discarded and the published one stays; an empty generation must never
replace a good one.

## The PyPI files proxy

**An index proxy caches nothing for `uv sync --frozen`.** uv downloads
every locked distribution from the absolute `files.pythonhosted.org` URL in
`uv.lock`; `UV_DEFAULT_INDEX` / `UV_INDEX_URL` serve only unlocked build
dependencies. Measured 2026-09-04 (uv 0.9.26, the same uv the fabro sandbox
image carries): a `--frozen` sync with
`UV_DEFAULT_INDEX=http://127.0.0.1:9/bogus/` succeeded; pointed at a
running proxpi it left the store unchanged (17 → 17 files).

**What works: rewrite the file host in the populator's own clone of each
`uv.lock`** (`https://files.pythonhosted.org/packages/` →
`http://pypi-proxy.ci-warm-cache.svc.cluster.local:8081/packages/`),
`source = { registry = … }` untouched. Tested: the wheels come through the
proxy, the lock's hashes are still enforced (a tampered proxied wheel fails
with `Failed to download idna==3.19`), the cache lands under
`wheels-v5/pypi/…` exactly as a job's ORIGINAL lock expects, and that
original lock syncs `--offline` from the generation. No `UV_DEFAULT_INDEX`
is set, so build dependencies stay in the `pypi` bucket too. The clone is
reset to the fetched tip on the next run, so the rewrite never leaks; the
lock is hashed BEFORE the rewrite.

The swap is a pure prefix, so the proxy needs only `location /packages/`
on a caching reverse proxy — which decided the choice (measured
2026-09-04; image digests pinned in the manifests):

| | devpi-server 6.20.3 (PyPI 2026-06-30) | proxpi 1.3.0 (2026-05-12) | nginx 1.28.3 `proxy_cache` |
|---|---|---|---|
| PEP 691 JSON + PEP 503 HTML, keyless | yes (`root/pypi` mirror index) | yes — verified `Accept: application/vnd.pypi.simple.v1+json` → `api-version 1.0`; HTML too | not needed on the rewrite route (only `/packages/` is proxied) |
| File-cache bound | **none** — `devpi-server --help` offers only `--mirror-cache-expiry SECS` (metadata TTL) | `PROXPI_CACHE_SIZE` bytes (default 5 GB), **LFU** eviction (`_cache.py` `_evict_lfu` by `n_hits`), store persists across restarts | `proxy_cache_path … max_size=8g min_free=1g inactive=30d`; the cache manager "removes the least recently used data" (nginx.org `ngx_http_proxy_module`) |
| Container image | no official image; would need our own build | `docker.io/epicwink/proxpi:1.3.0@sha256:0748b92ddf75405d9d83fbd1705517f951e67e0540af86e0a9bf4de388ba86c0` (Python 3.14, gunicorn, root) | `docker.io/library/nginx:1.28.3-alpine@sha256:a8b39bd9cf0f83869a2162827a0caf6137ddf759d50a171451b335cecc87d236` |
| Footprint | sqlite + pyramid + background threads (heaviest) | 60 MiB RSS idle, **230 MiB** after serving the union; CPU idle | **5 MiB** idle, 107 MiB after serving (64 MB keys zone + buffers) |
| Hit/miss surface | HTTP API, no cache stats | counters exist (`_CacheStats`) but no route/log exposes them (`/health` only) | `cache=HIT|MISS` per request in the access log, `X-Cache-Status` header |
| Pointing uv at it | index URL only — useless under `--frozen` | index URL (useless under `--frozen`) or lock rewrite to `/index/<pkg>/<file>` (per-package rewrite; cold run 18.4 s, each file GET first lists the package) | lock rewrite is a plain prefix swap; cold 14.8 s |

**nginx**, then: one static `nginx.conf` in `pypi-proxy/pypi-proxy.yaml`,
store on `ci-cache` at `/var/cache/ci-runner/pypi-proxy`, a `Deployment` +
`ClusterIP Service` `pypi-proxy` in the `ci-warm-cache` namespace, applied
by `converge-warm-cache.sh` so it survives the tmpfs-datastore reboot.
Bound: 8 GB is ~75 rebuild-unions; `inactive=30d` ages out versions the
fleet has moved past; `min_free=1g` protects the tier; wheel URLs are
immutable, so 30-day validity is safe. Upstream TLS is verified and
anything but `GET`/`HEAD` is refused, as on the crates proxy. Two things
the manifest's header explains that the memo's tested config did not have:
the store is FLAT (no `levels=`), because nginx's level subdirectories are
0700 and the capability-less populator could not count them; and
`readOnlyRootFilesystem` holds because nginx's pid and temp paths point at
emptyDirs. Workflow pods never use the proxy (their locks are untouched),
so there is no hostPort and no NetworkPolicy change. An unreachable proxy
degrades a rebuild to a direct PyPI build and records
`proxy_unavailable=1`; it never fails the run.

## Verifier

Cache layout observed (uv 0.9.26, from-empty builds), and how each entry
maps back to a `(name, version)`:

| bucket | entry shape | (name, version) from |
|---|---|---|
| `wheels-v5/pypi/<name>/<ver>-<tags>` (symlink), `…-<tags>.http`, `….msgpack` | pointer to `archive-v0/<id>`; a non-PyPI index is one level deeper: `wheels-v5/index/<urlhash>/<name>/…`; long tag sets are hashed (`3.5.1-16ed840a51de88b3`) | dir name + first `-` field of the stem |
| `archive-v0/<id>/` | unpacked wheel; **the pointer symlink is ABSOLUTE** but uv re-roots by `<id>`: a copy moved elsewhere with all 85 links dangling synced `--offline` in 0.59 s | `<Name>-<Version>.dist-info` inside (normalize `_`→`-`, lowercase) |
| `sdists-v9/pypi/<name>/<ver>/<id>/` (built wheel + `src/`), `revision.http` | | path |
| `sdists-v9/git/<urlhash>/<sha16>/<wheelstem>{,.whl}`, `metadata.msgpack` | | wheel filename; `<sha16>` must prefix a lock `source.git` fragment SHA |
| `git-v0/db/<urlhash>/.git`, `checkouts/<urlhash>/<sha7>`, `locks/` | | `git cat-file -e <lock sha>` in the db; `<sha7>` prefix of a lock SHA |
| `simple-v18/pypi/<name>.rkyv` | index metadata, name only | name ∈ lock names or build-dep closure |
| `interpreter-v4`, `builds-v0` (empty after builds), `.lock`, `.gitignore`, `CACHEDIR.TAG`, `.warm-manifest.json` | not packages | counted in totals only; anything else at top level is UNKNOWN and fails the publish |

Build dependencies are the one legitimate class outside every lock
(hatchling, setuptools, packaging 26.3 — not the locked 26.2 — tomlkit,
trove-classifiers; 3–5 MB). The verifier derives them from
`[build-system].requires` of every `src/` and git checkout in the cache
(PEP 517 default `setuptools`+`wheel` when absent), closed over
`Requires-Dist` of the unpacked wheels; no allowlist, reported as their own
class. They are fetched DIRECT from PyPI (the index URL is not rewritten),
which is why they do not count as proxied downloads.

Results (`verify-uv-cache.py --cache DIR LOCK…`, exit 1 on any unreferenced
or unknown entry, `--json` for the manifest): two locks (driver-claude +
overseer): 77.9 MB, 3,196 files, 75 referenced entries → exit 0; after
`uv sync` of a third project (requests, attrs) into the same cache → six
`UNREFERENCED archive-v0/… -> (requests, 2.32.5)` … (attrs, urllib3,
charset-normalizer, certifi, idna) → exit 1. Nine locks on the nginx-built
generation: 101 (name, version) pairs, 309 referenced, 20 build-dep entries
→ exit 0; against livespec's lock alone the same generation reports 51
entries from the other repositories. The shipped script is the tested one
restructured for this repo's lint rules; its output was diffed byte-for-byte
against the original on the clean and the injected case (2026-09-06).

**`uv cache prune` / `uv cache clean` MUST NOT be run against
`uv-generations/`, from the host or anywhere else.** `prune` ("Prune all
unreachable objects") removes `builds-v0` and archives no pointer references
— a no-op on a from-empty generation; `clean <pkg>` removes that NAME at
every version. Neither knows about lockfiles, so neither enforces "nothing
unreferenced". Two hard gotchas, measured 2026-09-04: on a COPY at another
path, `prune` deleted every archive (5,073 files, 329 MiB — the absolute
links point elsewhere), and `clean ruff` followed the absolute link and
deleted the ruff archive out of the ORIGINAL. Both are safe only at the
exact build path; the populator calls neither (from-empty leaves no
orphans). `prune --ci` removes pre-built wheels — the opposite of what the
tier is for.

The verifier's own totals count every path (a hardlinked inode twice, a
pointer symlink once); the budget and the metrics use `du -sb` and
`find -type f`, which count an inode once and no symlinks — the smaller
numbers, and the ones `ci-cache-gauges.sh` reports.

## From-empty build cost

Measured on the VPS the design memo was written on (uv 0.9.26,
2026-09-04); wall time is dominated by unpack + hardlink CPU on that uplink,
and the CI host's gain depends on its own. The proxy buys ~105 MB of PyPI
transfer per rebuild regardless (48 rebuilds a day at the CronJob cadence
would be 5 GB/day direct — the no-rebuild rule makes most ticks free).

| build | wall | cache | note |
|---|---|---|---|
| livespec lock alone, cold from PyPI | 7.16 s | 354 MB / 6,084 files | claude-agent-sdk unpack is 227 MB of it |
| same cache, warm re-sync | 0.34 s | | job-side steady state |
| relocated copy, dangling links, `--offline` | 0.59 s | | proves relocation |
| nine locks, from empty, direct PyPI | 18.62 s | 379 MB / 8,070 files | matches the 2026-08-23 union |
| nine locks, from empty, nginx cold | 14.82 s | 379 MB / 8,070 | 94 MISS, 2 HIT; store 105 MB / 94 objects |
| nine locks, from empty, nginx warm | 13.52 s | 379 MB / 8,070 | 94 HIT / 0 new MISS |
| nine locks, proxpi cold / warm (lock rewrite) | 18.37 s / 12.78 s | | per-file index listing on the cold path |

## Budget

`generation_bytes` (`du -sb`) and `generation_files` (regular files) must
each be at or under the budget, else the generation is renamed
`<stamp>.refused`, the symlink stays, `last-run.json` records `refused=1`
with both numbers, and the job exits 3. Fixed numbers, not a multiple of
the last build: a ratchet is self-referential, and the point is an alarm
when the union drifts; re-deriving it is a reviewed commit against the
cost table above. Values: **1,000,000,000 bytes and 20,000 files** (union
379 MB / 8,070 files; the runaway generation was 1,388 MB / 159,409 files,
so both axes trip well before that shape recurs). Home: the
`warm-cache-budget` ConfigMap (`bytes`, `files`) in
`warm-cache-cronjob.yaml`, injected as `WARM_BUDGET_BYTES` /
`WARM_BUDGET_FILES` via `configMapKeyRef`; the populator refuses to start
without them, records the values in effect in every generation's manifest
and in `last-run.json`, and the sweep emits them as
`livespec.ci_warm.budget_*` so a chart can draw the line.

## Metrics

The CronJob has no `hostNetwork` and the host collector's OTLP receiver
listens on `127.0.0.1:4319` only (`otel-collector`
`config.ci-runner-host.yaml`, the loopback `otlp` receiver). Do not add
`hostNetwork` — the pod runs PyPI build backends. So the populator writes
and the host sweep emits:

- The populator writes `<generation>/.warm-manifest.json` (the generation's
  own record: lock hashes, sizes, budget in effect, the verifier's summary,
  proxy counts) and `$WARM_ROOT/last-run.json` (one document per run:
  `run_id` = the run's stamp, `rebuilt` / `refused` / `verified` 0|1,
  `published_generation`, `generation_bytes` / `_files`, the previous
  generation's, `trimmed_bytes` / `_files` = previous minus new,
  `populate_seconds` for the uv phase, `repos_synced` / `repos_failed`,
  the budget, `proxy_unavailable`, `proxied_downloads`, `proxy_hit_ratio`,
  `unreferenced_entries`, `uv_exit`, `rebuild_reason`). Refused and
  rejected runs are written too (before the non-zero exit).
- `../runner-pod-lifecycle/scan-runner-pod-lifecycle.sh` (5-minute timer,
  already the `livespec.ci_lifecycle.*` emitter) reads `last-run.json`;
  when `run_id` differs from the one in its state file
  (`/var/lib/ci-runner-k3s/warm-cache-last-emitted-run`) it adds the
  `livespec.ci_warm.*` gauges to its POST and records the id after the POST
  succeeds. Absent or unparseable input omits the family, never a false
  zero. The gauges: `generation_bytes`, `generation_files`, `trimmed_bytes`,
  `trimmed_files`, `populate_seconds`, `repos_synced`, `repos_failed`,
  `rebuilt`, `refused`, `verified`, `unreferenced_entries`,
  `budget_bytes`, `budget_files`, `proxied_downloads`, `proxy_hit_ratio`
  (only when derivable), `run_epoch` (the join key to the Job log). Same
  resource attributes as the lifecycle gauges (`service.name =
  ci-runner-lifecycle`, `host.name`), `metrics` dataset of the `livespec`
  environment. The phase2 README's "What every sweep emits to Honeycomb"
  carries the rows and the saved-query recipe.
- `proxy_hit_ratio` is derived without log parsing: the populator mounts the
  proxy store read-only, counts its objects (one regular file each — the
  store is flat) before and after the build, and divides by the number of
  uv `.http` pointer files in the new generation that name the proxy URL
  (exactly the distributions fetched through it; build dependencies fetched
  direct are excluded): `hit_ratio = 1 − new_objects / proxied_downloads`.
  Verified 2026-09-06 in the populator image: 23 proxied downloads, 5 new
  objects, `0.7826`; a second build of the same locks `1.0`; a one-package
  lock bump `0.9583` (23/24).

**The saved query** (`metrics` dataset, `host.name = poweredge-xubuntu`,
granularity 1800 s — the CronJob's cadence — over the trailing week; one
row per emitted run): `MAX(livespec.ci_warm.generation_bytes)`,
`MAX(livespec.ci_warm.trimmed_bytes)`, `MAX(livespec.ci_warm.generation_files)`,
`MAX(livespec.ci_warm.populate_seconds)`, `MAX(livespec.ci_warm.proxy_hit_ratio)`,
`MAX(livespec.ci_warm.refused)`, `MAX(livespec.ci_warm.rebuilt)`,
`MAX(livespec.ci_warm.repos_failed)`, `MAX(livespec.ci_warm.budget_bytes)`,
filtered to rows where `livespec.ci_warm.run_epoch` exists. The first
rebuild after this ships reads `trimmed_bytes` ≈ 1,388 MB − the new size.
The `run_query` spec is in the phase2 README beside the lifecycle recipe.

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
the file count, which the from-empty generation build ("Every generation
is built from empty" above) bounds. On a tier without reflink the copy
fails and the volume gets no seed — cold, never a byte copy.

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
bytes — which is what the from-empty rebuild bounds: the union is ~8k
files, not 191k, so the per-file `FICLONE` cost of the reflink seed falls
by the same factor.

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
header has the details). The writer build runs behind its OWN sccache server
(`SCCACHE_WRITER_PORT`, default 4227), started under the writer credential
and proven `ReadWrite` from the server's own startup log before anything
compiles; a server that is not `ReadWrite` refuses the build
(`<repo>:sccache-readonly` in the failure list). The pod's default port 4226
is not safe to share: the image's cargo shim runs `sccache --zero-stats`
before every measured cargo subcommand, `cargo fetch` included, and that
client starts a server from the pod environment, without the writer
credential, which fails its write check and comes up ReadOnly; every put
behind it is dropped with misses counted and zero errors (2026-09-06, three
writer builds and no objects; `livespec-dev-tooling-efqeip.4`). Design and
the live verification:
`plan/ci-runner-cache-tiers/research/005-a1-crates-proxy-verification.md`.
The cargo and sccache steps run after the uv phase on every tick, whether
or not the uv generation was rebuilt.

## Target generations: the warmed ASAN fuzz tree

The compile shape sccache reaches least is the console's `check-fuzz` job:
`cargo +nightly fuzz build` compiles the workspace with
`-Zsanitizer=address`, nothing else in the fleet produces those objects, and
the job is every console PR's critical path (323–337 s, the longest in its
matrix; ~80 s of it that compile phase). So the populator also publishes a
**warmed `target/` tree** per `(repository, key)` — one key so far,
`asan-fuzz`, for every routed repository with a `fuzz/Cargo.toml` — and the
provisioner seeds it into each work volume beside the uv seed
(console plan `optimize-console-builds`, `livespec-console-beads-fabro-ydlant`;
sized by that plan's research/010 on this node, 2026-09-06: 253 MB, cold
33–41 s at 12 jobs, 0 % sccache hits; Fresh in ~0.1 s once seeded).

| Path | Role |
|---|---|
| `.warm/target-generations/<repo>/<key>/<stamp>/tree` | the `fuzz/target` tree, built at the job's own checkout path `/__w/<repo>/<repo>` (cargo fingerprints embed the SOURCE path) with the job's own wrapper (sccache, as the writer here, so the sanitized objects also land in the compilation cache) |
| `…/<stamp>/.target-manifest.json` | `source_sha`, `toolchain` (nightly rustc + cargo-fuzz), sizes, build seconds — the generation KEY; a consumer that does not match `toolchain` builds cold |
| `.warm/target/<repo>/<key>` | the published link, swapped atomically; pruned to `KEEP_GENERATIONS` like the uv tier, the live one never pruned |
| `<volume>/_warm/target/<repo>/<key>/{tree,.target-manifest.json,.generation}` | the provisioner's reflink copy (job-owned inodes; no shared inode exists to write through), made by the same `setup` script as the uv seed |

Rebuilt only when the default-branch commit or the fuzz toolchain changed,
under the same admitted-job gate and `nice`/`ionice` as the writer build,
and only on the `python-rust-fuzz` image (the CronJob's pin): on any other
image every repository logs "fuzz toolchain absent" and is skipped.

**The consuming job does two things** (the console's `check-fuzz` "Phase:
compile" step): it moves `_warm/target/<repo>/asan-fuzz/tree` to `fuzz/target`
(a rename within the volume), then **restores source mtimes** for files
unchanged vs `source_sha` (`git diff --name-only <source_sha>` names the
exceptions). Without that restore the tree saves only the sanitized
dependencies (~12 s of 33–41 s): a fresh checkout stamps every source with
clone time, and cargo's local-crate fingerprints are mtime-based, so the
console's own three fuzz-graph crates would recompile. Measured on this node
(research/010): fresh clone + seed + restore = 0 `Compiling`, ~90 ms; a PR
editing a domain crate = 3 crates, 28.5 s vs 41.2 s cold.

Telemetry: the hook's `postStart` records a `target` row in `warm-copy.tsv`
(hit = the seed is present, generation = its stamp), so `ci-cache-span`
emits the same `cache.warm-copy` span as the uv tier; the populate manifest
carries `target_built` / `target_skipped` / `target_skipped_busy` and the
`fuzz_toolchain` it built with.

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
  repository (it re-derives the list) or changing the populator, the
  verifier, the proxy manifest or the hook template; also re-run
  `../reconstruct/install-converge-unit.sh` so the boot copy under
  `/usr/local/lib/ci-runner-k3s/warm-cache/` matches. Then
  `../arc/recycle-scale-set-runners.sh <scale-set>` for any scale set with
  idle runners, as after any values change. The seed itself is part of the
  provisioner manifest and is applied by the boot converge
  (`../reconstruct/converge-ci-stack.sh`, step 3).
- **Exit codes** of a populate Job: 0 every step ok (rebuilt, or verified
  unchanged); 1 a repository step failed or the verifier rejected the new
  generation; 2 a preflight failed (nothing built — the log's first lines
  say which: uv, git, python3 ≥ 3.11, the verifier, the repos file, the
  budget env, or a `WARM_INJECT_TEST` path with no project in it); 3 the
  new generation was over budget and refused.
- **Is it live?** `kubectl -n ci-warm-cache get cronjob,jobs,deploy,svc`
  shows the schedule, the last runs and the proxy; `sudo ls -la
  /var/lib/rancher/k3s/storage/.warm` on the host shows the `uv ->
  uv-generations/<stamp>` link, the retained generations (plus any
  `<stamp>.refused` / `<stamp>.unverified` kept for one cycle), and
  `last-run.json`; `sudo cat …/.warm/last-run.json` is the run's verdict
  in one document; `sudo cat …/.warm/uv-generations/<stamp>/.warm-manifest.json`
  the generation's. A new work volume shows the seed: `sudo ls -la
  /var/lib/rancher/k3s/storage/pvc-*/_warm/uv`; `stat -c %h` of a file
  there is 1 (its inode is the volume's own) and `filefrag -v` on it shows
  `shared` extents (a reflink of the generation). A workflow pod's
  `kubectl describe pod <runner>-workflow` shows `UV_CACHE_DIR`, no
  `UV_LINK_MODE`, and no warm-cache mount.
- **Host gauges**: `ci-runner/observability/ci-cache-gauges.sh` still turns
  `populate-manifest.json` and the live generation's age and size into
  `livespec.ci_cache.{generation_*,populate.*}` every 5 min (the
  `CI warm cache stale` / `CI cache populate failing` triggers read
  those); the build metrics are the sweep's `livespec.ci_warm.*`
  ("Metrics" above).
- **A repository failed to sync**: the Job is red (exit 1) and its log
  names the repository. The generation still published (fail-soft per
  repository) WITHOUT that repository's packages; the next tick rebuilds.
- **The verifier rejected a generation**: exit 1, `REJECTED: …` in the log
  with every `UNREFERENCED` / `UNKNOWN` entry named; the previous
  generation is still live; the rejected directory is
  `uv-generations/<stamp>.unverified` until the next run prunes it.
  Unreferenced entries mean something synced into the generation that no
  routed lock names (a `WARM_INJECT_TEST` left set on the CronJob?);
  UNKNOWN entries mean a uv bump changed the cache layout — update the
  verifier's table.
- **A generation was refused**: exit 3, `REFUSED: … OVER BUDGET` in the
  log with both numbers; previous generation live; the directory is
  `<stamp>.refused` for one cycle. Either the union really grew (a new
  routed repository, a heavy new dependency) and the budget is re-derived
  in a reviewed commit to `warm-cache-cronjob.yaml`, or something is wrong
  with a lock.
- **Growth** is no longer a manual chore: a generation cannot exceed the
  budget, and it never holds a version the current locks do not name.
- **Bump the image** in lockstep with the fleet's fabro sandbox pin:
  `WARM_CACHE_IMAGE=... ./install-warm-cache.sh`, or edit the CronJob
  manifest. Bump the proxy's nginx digest in `pypi-proxy/pypi-proxy.yaml`.
- **Flush the proxy**: `pypi-proxy/README.md`.

### Acceptance recipe (the attended, host-side leg)

The evidence `livespec-41w4` journals, in the order it is cheapest to
produce; every step reads the live host, nothing is assumed from this
README.

- (a) **Three consecutive Job logs.** After `install-warm-cache.sh`, the
  first populate's log shows `REBUILD: published generation … has no
  manifest` (or `no published generation`), `starting generation … EMPTY`,
  `proxy: N distributions fetched through it, store 0 -> N objects,
  hit_ratio=0.0`, `published generation …`, and
  `kubectl -n ci-warm-cache logs deploy/pypi-proxy` is all `cache=MISS`.
  Bump one routed lock (any merge that changes a `uv.lock`) and create a
  Job: `REBUILD: lock changed: <repo>` and `hit_ratio` ≥ 0.9. Create a
  Job with nothing changed: `every routed uv.lock unchanged and generation
  … verifies; no rebuild (rebuilt=0)`, exit 0.
  `kubectl -n ci-warm-cache create job populate-now --from=cronjob/warm-cache-populate`
  is the manual Job; `kubectl -n ci-warm-cache logs job/populate-now` the log.
- (b) **The live generation's size**: `last-run.json`'s
  `generation_bytes` within ~10 % of 379,000,000 (hundreds of MB, not
  1.4 GB) and `generation_files` near 8,070; `sudo du -sb` of the symlink
  target agrees.
- (c) **The verifier refuses an injected entry.** On the host, make an
  UNROUTED uv project under the warm root:
  `sudo mkdir -p /var/lib/rancher/k3s/storage/.warm/inject-test && cd $_ &&
  sudo uv init --name injected --no-workspace && sudo uv add attrs cattrs --no-sync`
  (any packages no routed lock names; the directory needs only
  `pyproject.toml` + `uv.lock`). Create a Job from the CronJob with
  `WARM_INJECT_TEST=/warm/inject-test` added to the container env
  (`kubectl create job … --from=cronjob/… --dry-run=client -o yaml`, add
  the env, apply). Expect `NEGATIVE TEST: …`, `UNREFERENCED archive-v0/… ->
  (attrs, …)` lines, `REJECTED: …`, exit 1, `readlink …/.warm/uv`
  unchanged, a `<stamp>.unverified` directory. Remove `inject-test`
  afterwards.
- (d) **The budget refuses.** `kubectl -n ci-warm-cache patch configmap
  warm-cache-budget -p '{"data":{"bytes":"100000000"}}'`, create a Job
  with `WARM_FORCE_REBUILD_SECONDS=0` in its env (so it rebuilds without
  a lock change): `REFUSED: … OVER BUDGET`, exit 3, symlink unchanged,
  `<stamp>.refused` present, `last-run.json` `refused: 1`. Restore the
  ConfigMap (`converge-warm-cache.sh` re-applies the committed values).
- (e) **Honeycomb rows** for every `livespec.ci_warm.*` gauge with
  `host.name=poweredge-xubuntu` after the sweep's next tick (the sweep's
  journal says `emit: … livespec.ci_warm.*(run <stamp>)`); on the first
  rebuild `trimmed_bytes` ≈ 1,388 MB − the new size. The saved query is
  under "Metrics".
- (f) **A real job hits the seed**: a routed job's `uv sync` step shows no
  `Downloading` lines and completes in under a second; the pod's
  `_warm/.uv-generation` names the generation `readlink` shows on the host.

All of (a)–(d) were exercised on 2026-09-06 in the populator's own image
(`livespec-fabro-sandbox:python-rust-v1.40.1`, root with every capability
dropped) against two file-routed repositories and a local instance of the
proxy manifest's nginx config, with the store bind-mounted read-only:
rebuilt=1 then rebuilt=0, `REJECTED` naming six `attrs`/`cattrs` entries
with the symlink unchanged, `REFUSED` at a 10 MB budget with exit 3, a
lock bump rebuilding at `hit_ratio=0.9583`, and the rejected directories
pruned on the following run. What only the host can show is (e) and (f).

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
another process's growth must never ship on the start path again. "Every
generation is built from empty" above is that bound: the generation is
the union of current locks by construction, refused over a fixed budget,
and its size and trim are emitted on every build.

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
