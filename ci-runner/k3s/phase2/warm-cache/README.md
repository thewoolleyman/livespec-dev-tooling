# Warm uv cache — tier 1 of the cache tiers, on the k3s/ARC lane

Tier 1 of the three cache tiers in the livespec repo's
`plan/fleet-ci-runner-pool/research/design.md` ("Cache tiers, and the
volume that holds them"; maintainer-directed 2026-08-13: local caching of
the runner cache is in scope), rooted on the dedicated
`/var/cache/ci-runner` volume, re-scoped from the deleted podman lane to
this pool under `livespec-s43svm.2`.

## What it is

A fleet-wide warm **uv** cache lower at `/var/cache/ci-runner/warm/uv`,
written by exactly one trusted writer and read by every workflow pod:

| Path | Role |
|---|---|
| `warm-cache-populate.sh` | The populator. Clones or fast-forwards every routed repository's default branch and runs `uv sync --frozen --all-groups --no-install-project --no-install-workspace` against a fresh hardlink-seeded generation, then publishes it with one atomic symlink rename and prunes all but the newest two; for every repository with a `Cargo.lock` it also runs `cargo fetch --locked` through the crates proxy (`../crates-proxy/`) to pre-warm it. Never builds or installs a project; only locked third-party dependencies land in the cache. Its header carries the generation/publish design and the per-repository fail-soft rule. |
| `warm-cache-cronjob.yaml` | Namespace `ci-warm-cache` + the `warm-cache-populate` CronJob (every 30 min, `concurrencyPolicy: Forbid`), running the populator in the same fabro sandbox image the fleet's CI jobs execute in (the `python-rust` layer, so `cargo` is present), with `/var/cache/ci-runner/warm` mounted read-WRITE — the only read-write mount of that path in the cluster. |
| `install-warm-cache.sh` | Derives the routed-repository list from `../arc/values-*.yaml` (every per-repo scale set's `githubConfigUrl`) into the `warm-cache-repos` ConfigMap, applies the CronJob, converges its script ConfigMap from the file above, runs one populate immediately and waits for it, then converges `arc-hook-pod-template` via `../arc/converge-hook-pod-template.sh`. Idempotent; re-run after adding a routed repository. |
| `../arc/hook-pod-template.yaml` | The reader side, in the one file every workflow pod already reads: mounts the warm root READ-ONLY into the job container, copies the current generation into the pod's ephemeral work volume in a `postStart` hook, and sets `UV_CACHE_DIR` to that copy. |

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

So the writable upper is a **copy**: the job container's `postStart`
copies the current generation from the read-only mount into `/__w/_warm/uv`
on its own work volume (so uv's hardlink install into the job's `.venv`
stays on one filesystem), and `UV_CACHE_DIR` points there. The trust
tiering is the same as before — a job reads the lower and can never write
it — enforced by the read-only bind mount plus `deny mount`, rather than
by an overlay. The generation/symlink publish protocol exists because
readers copy while the populator may be writing; see the populator's
header.

The copy is the hook's `postStart` rather than an `initContainers` entry
because the hook template assigns `initContainers` WHOLESALE and the
hook's newer releases add their own `fs-init` init container: a template
init container would silently replace it on a runner-image bump (the image
is pinned by tag+digest — see the k3s README's "Pinned versions" — exactly
so that bump is a reviewed change) and break every job. `postStart` is a
key the hook never sets. The
kubelet holds the container out of Running until `postStart` returns and
the hook waits for Running before exec'ing any step — verified live on
this cluster (a 12 s `postStart` held the pod Pending 12 s) — so the copy
is complete before the first step runs.

It is fail-soft in every direction: a node without the warm root mounts an
empty directory (`DirectoryOrCreate`), a missing or failed copy leaves no
cache and uv resolves cold (today's behaviour), and the `postStart` always
exits 0 so a cache fault can never fail a job. One constraint it imposes:
every `container:` image routed to this pool must carry `/bin/sh` and
`cp`, because a `postStart` exec that cannot start kills the container.
Every fleet `container:` is the fabro sandbox image, which does.

## What it buys, measured

Against the `livespec` lockfile, same host class, 2026-08-23:

| Step | Cold (today on this lane) | With the warm lower |
|---|---|---|
| copy the lower into the work volume | — | 0.8 s (379 MB, the union of all nine routed repositories' locked trees) |
| `uv sync --all-groups --frozen` | 7.9 s (matches the 7–9 s per job read off live k3s-lane runs) | 0.5 s |

About 6.5 s per job, and — the part the wall-clock number undersells — no
PyPI round trip per job, which is the largest unretried-fetch surface the
fleet's workflow comments name. The workflow files themselves assumed this
tier existed: the fleet's `Restore uv cache (hosted lane only — self-hosted
uses ~/.cache/uv)` steps skip `actions/cache` on the self-hosted lane on
the premise of a warm on-host cache, a premise that was true on the podman
lane and false on ephemeral ARC pods until this tier.

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
the Rust problem is the compilation cache (B1 of plan
`ci-runner-cache-tiers`), not this tier. Design and the live verification:
`plan/ci-runner-cache-tiers/research/005-a1-crates-proxy-verification.md`.

## Operating it

- **Install / re-converge**: `KUBECONFIG=/etc/rancher/k3s/k3s.yaml
  ./install-warm-cache.sh` on the host. Re-run after adding a routed
  repository (it re-derives the list) or changing the populator or the
  hook template. Then `../arc/recycle-scale-set-runners.sh <scale-set>` for
  any scale set with idle runners, as after any values change.
- **Is it live?** `kubectl -n ci-warm-cache get cronjob,jobs` shows the
  schedule and the last runs; `ls -la /var/cache/ci-runner/warm` on the
  host shows the `uv -> uv-generations/<stamp>` link and the retained
  generations. A workflow pod's `kubectl describe pod <runner>-workflow`
  shows the `warm-cache` mount and the `postStart`.
- **A repository failed to sync**: the CronJob's last Job is red and its
  log names the repository. The generation still published (fail-soft per
  repository), so the other repositories are still warm.
- **Growth**: a generation is hardlink-seeded from its predecessor, so the
  cache accumulates every locked version ever synced. The volume is 658 GB
  and the fleet-wide union is 379 MB; when that matters, delete the
  `uv-generations/` directory and the `uv` link on the host and run one
  populate — the next generation starts empty and re-fetches the current
  locks only.
- **Bump the image** in lockstep with the fleet's fabro sandbox pin:
  `WARM_CACHE_IMAGE=... ./install-warm-cache.sh`, or edit the CronJob
  manifest.

## Tiers 2 and 3

The other two tiers from the design record are not here: tier 2, a local
GitHub Actions cache service (`livespec-s43svm.3`), and tier 3, a Nix store
and binary cache for homelab's builds (`livespec-s43svm.4`). Each is tracked
on its own work-item.
