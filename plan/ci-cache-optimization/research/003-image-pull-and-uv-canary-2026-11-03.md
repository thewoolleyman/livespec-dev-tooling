# 003: levers 3 and 6 measured — image pulls and the uv warm/cold gap (2026-11-03)

Measured read-only on 2026-11-03, 15:20-16:00Z, by a helper of the ci-cache-optimization seat. Nothing on any host,
cluster or ledger was changed.

## Lever 3: sandbox image pulls ("Initialize containers") — DROPPED

Sources: the kubelet events (`sudo -n k3s kubectl get events -A --field-selector reason=Pulled -o json`, last hour
only), and the containerd logs from each node. The logs were `Pulled image ... in Xs` lines and `CreateContainer
name:"job"` lines, read from `/var/lib/rancher/k3s/agent/containerd/` on poweredge and gmktec, and from
`/srv/sandbox-storage/k3s/agent/containerd/` on hp.

| Node | Window | Job containers/day | First pulls of a new tag/day | First-pull median / p90 / max |
|---|---|---:|---:|---|
| poweredge | 16.8 h | 7,628 | 157 (2.1%) | 0.54 s / 9.3 s / 22.2 s |
| gmktec | 29.7 h | 3,633 | 285 (7.9%) | 0.74 s / 3.1 s / 14.0 s |
| hp | 7.0 h | 1,852 | 110 (5.9%) | 1.40 s / 10.3 s / 13.1 s |

- Almost every pull call is a manifest check of 0.4-1.3 s on an image already present.
- A real layer download happens once per release tag per node.
- A perfect pre-pull would save about 860 s/day, about **1.7 job-hours/week**. That is too small to carry.
- The rest of the 5 s "Initialize containers" median is container create, not pull.
- The registry mirror is configured only on poweredge (`/etc/rancher/k3s/registries.yaml`). gmktec and hp pull from
  ghcr directly. That matters for a cattle rebuild, not for steady-state job time.

## Lever 6: uv warm/cold gap — the seed works; hp has no seed

The cold canary is live (`CI_CACHE_CANARY_N=20` in the `arc-hook-pod-template` ConfigMap). Over 7 days, Honeycomb
dataset `github-ci`, spans `name = cache.job-summary`, broken down by `host.name` and `build.cache.kill_switch`: 1,327
canary of 26,654 jobs (4.98%).

uv step ("Install Python dev deps via uv", k3s only), 11-01T15Z..11-03T15Z. Canary jobs were joined to GitHub job
records by runner pod name:

| | n | median | p90 |
|---|---:|---:|---:|
| warm | 1,667 | 6 s | 12 s |
| canary (cold) | 187 | 13 s | 21 s |

A paired comparison (each canary job against the warm jobs of the same run) gives a median gap of +6.0 s, a mean of
+6.2 s, a p10 of +1 s and a p90 of +12 s.

- The seed saves about 6 s per job. It is working where it is present.
- A warm job still spends a median 6 s in the step. That is the ceiling for any further uv-side work, about 44 h/wk on
  poweredge's volume. Nothing measured says how much of those 6 s a different mechanism would recover, so no carrier is
  filed for it.
- **hp-xubuntu has no warm uv seed.** `kubectl get nodes -L ci-runner.io/warm-uv-cache` shows `true` on gmktec and
  poweredge and is empty on hp. That is the spec's `runner-only` posture: host-served caches over the node network,
  plus a cold start in place of a seeded tree. hp has run real CI load since 2026-11-03 15:08Z, at about 1,850 job
  containers/day. At the measured ~6 s gap that is about 3 job-hours/day, ~21 h/wk, spent cold.
  - Candidate lever 6b: give hp jobs a HOST-SERVED uv source over the node network. Today the pool's PyPI files proxy
    (`warm-cache/pypi-proxy/`, on poweredge) is read only by the populator.
  - Measure hp's own warm/cold numbers before filing.
- **Cache telemetry covers poweredge only.** Every `cache.*` span in the 7 days has `host.name = poweredge-xubuntu`.
  gmktec's ~1,400 and hp's ~520 job containers in 11-03 08:30-15:20Z emitted none. The spec's §"Runner-pool cache
  telemetry" says every tier MUST emit for every job, so this is a conformance gap. It is not mine to fix: I'm routing
  it to the pool's owner. Until it is fixed, gmktec's and hp's cache behaviour cannot be read from Honeycomb.

## Ranking after this note

1. Nonroot prep (bd-ib-uuatg4), about 46 h.
2. Git mirror for checkout, about 25 h (est.). It still needs a breakdown of where checkout time goes.
3. hp host-served uv (6b), about 21 h (est.).
4. Nonroot legs onto the warm seed (bd-ib-rpit5z), about 7 h.
5. Action archive cache (livespec-dev-tooling-a35sa4), about 7 h plus the 429 failures.
6. Image pre-pull: dropped (1.7 h).

Scratch artifacts (parsers, queries and joined rows) were kept in the measuring session's scratchpad and are not
committed.
