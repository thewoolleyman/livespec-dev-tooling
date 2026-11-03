# 002: CI cache levers, ranked by k3s job-hours saved (2026-11-03)

Measured 2026-11-03 ~15:05Z by the ci-cache-optimization seat. This note carries plan assertion 3.

## Method (reproducible)

- Window: completed runs created 2026-11-01T15:00Z to 2026-11-03T15:00Z, all seven fleet repositories.
- Runs: `gh api --cache 6h --paginate "repos/thewoolleyman/<repo>/actions/runs?created=<a>..<a+1d>&per_page=100"`, one query
  per day. Counts: orchestrator 1,000 (the per-query cap, so its weight is a lower bound), dev-tooling 1,585, overseer
  466, livespec 867, driver-claude 307, driver-codex 418, runtime 151.
- Jobs: up to 30 runs sampled per (repository, workflow) with `random.seed(1)`, then
  `gh api --cache 6h --paginate "repos/thewoolleyman/<repo>/actions/runs/<id>/jobs?filter=latest&per_page=100"`. 1,051
  runs, 4,602 jobs. Each run is weighted by (runs of its workflow in the window / runs sampled).
- k3s only: a job whose labels include `ubuntu-*` is hosted (free) and excluded. Skipped jobs and skipped steps are
  excluded. Step time is `completed_at - started_at` from the job's `steps[]`.
- Scaling: hours per 48 h × 3.5 = "raw h/wk". The sample totals 3,244 raw k3s h/wk against research 002 of
  ci-runtime-and-cost (966 h over 10-27..11-03). The 11-02/03 contention (that note's "Why CI felt slow") inflates every
  figure here by about 3.4×, so "≈" below is raw ÷ 3.4. Ranks do not change under that division.

## Ranking

| # | Lever | Step(s) measured | raw h/wk | ≈ h/wk | median / p90 | Est. saving ≈ h/wk | Carrier |
|---|---|---|---:|---:|---|---:|---|
| 1 | Nonroot leg recursive `chmod -R` / `chown -R` | orchestrator `Prepare non-root leg` | 156.6 | 46 | 50 s / 146 s | ~45 | bd-ib-uuatg4 |
| 2 | Checkout from a node-local git mirror | `Checkout` + `Post Checkout`, all repos | 179.0 | 53 | 6-10 s / 12-24 s | ~25 (est.) | to file (pool tier; spec first) |
| 3 | Sandbox image pull tail after a tag bump | `Initialize containers`, all repos | 139.4 | 41 | 5 s / 11-12 s | ~10 (est.; measure pulls first) | measurement first |
| 4 | Nonroot private cold `UV_CACHE_DIR` → warm seed | nonroot minus root, same targets | 22.4 | 7 | +30 s on batched python checks | ~7 | to file (orchestrator ci.yml) |
| 5 | Node-local action archive cache | `Set up job`, all repos | 44.6 | 13 | 2 s / 4 s | ~7, plus the codeload 429 failures | livespec-dev-tooling-a35sa4 |
| 6 | uv install beyond the existing seed | `Install Python dev deps via uv` | 120.8 | 36 | 5-8 s / 9-13 s | unknown | Honeycomb cold-canary query first |
| 7 | mise | `mise trust + install` | 30.2 | 9 | 1-2 s | ~0 (already near-no-op) | none |
| 8 | sccache / cargo | no CI step in the window | 0 | 0 | — | 0 | none (factory-side only) |
| 9 | pip | no k3s step uses pip | 0 | 0 | — | 0 | none |

Order of work: 1, 4 (same file, small), 5 (already filed, spec proposal owed), 2, 3, 6. Lever 4 rides behind lever 1
because both edit the same nonroot steps of orchestrator `.github/workflows/ci.yml`.

## Notes per lever

1. The step's 50 s median sits below the 120-130 s that ci-runtime-and-cost measured on 40 runs because this sample spans
   both quiet and contended hours. Its p90 of 146 s matches that figure. Root jobs have no such step.
2. `actions/checkout` fetches over the network on every job. The pool's spec (§"Runner-pool build cache tiers") requires
   caching with zero workflow changes, so the realization is a host-served mirror that the hook pod template redirects
   to (git `url.<mirror>.insteadOf`). That is a new tier, so it is spec-change tier and needs a propose-change first.
   kubernetes-sandbox-backend, 2026-11-03 ~15:15Z: hp-xubuntu is a `runner-only` node with no ci-cache tier
   (`/srv/sandbox-storage/runner-workvols`, cold starts) and has carried real CI load since 15:08Z. Under the spec, a
   runner-only node reads host-served caches over the pool's node network, so the proposal must serve hp from a
   ci-cache node over the network rather than exclude it.
3. The 5 s median is container create on an image already present. Only pulls of a NEW sandbox tag (every release
   bumps it) are a cache lever. `registry-mirror/` and `sandbox-image-prune/` already exist. Pull counts come next, from
   kubelet `Pulling`/`Pulled` events. The CI job image (`python-v*`) is a different image set from the factory sandbox
   image (`python-agent-v*`), which the `sandbox_image_warm` role pre-pulls on factory nodes only (bd-ib-kogktm). Any
   CI-image pre-pull must not fight `sandbox_image_prune` over the current tag.
4. The override's 2026-09-04 reason was a root-owned hardlink seed ("Failed to initialize cache"). Since
   livespec-dev-tooling-hmv2bo the seed is a private reflink copy whose directories are opened 0777 by the provisioner's
   setup script, so uid 1000 can initialize it.
5. The 2 s median is mostly the action download. The larger value is reliability: 10 `Set up job` failures in 6 h on
   2026-11-03, every one a codeload download. The item is spec-change tier, and its linked proposal
   `fleet-arc-runners-set-up` is not on master. This plan files it.
6. The seed is already live, so whatever remains is linking into `.venv` plus resolution. Do not file a lever until the
   pool's cold-canary warm/cold gap is read from Honeycomb.

Not cache levers, so they stay with ci-runtime-and-cost: the `check-coverage` consumer fold-in, dev-tooling
`Run the batched metadata checks` (137 s median), and dev-tooling `check-per-file-coverage` (the suite itself).

Scripts: `steps.py` (fetch) and `agg2.py` (aggregate) were run from the session scratchpad. Their queries are the ones
stated above.
