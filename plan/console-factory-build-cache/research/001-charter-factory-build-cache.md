# 001 — Charter: factory-sandbox build CACHE for the console (Phase 2 factory leg)

This dev-tooling plan is the CROSS-REPO leg of the console's build-time
optimization programme for the FACTORY environment. Sibling of
`console-factory-build-telemetry` (which delivered the measurement substrate);
this one delivers the optimizations. It owns the livespec-dev-tooling (sandbox
image) and fabro-hosts (hp host services) changes.

## Parent / cross-references

- Console plan: `optimize-console-builds` in `livespec-console-beads-fabro`,
  plan epic `livespec-console-beads-fabro-gqmtwa`; Phase-2 scope event of
  2026-09-02 on that epic.
- Console children this delivers (both `blocked: needs-human`, factory-ineligible
  in the console tenant because the seams live HERE):
  - `livespec-console-beads-fabro-qxjdan` — factory cargo REGISTRY reuse.
  - `livespec-console-beads-fabro-di6fn5` — factory sccache.
- Console research to read for facts: `research/003-factory-hp-xubuntu.md`,
  `research/006-mechanism-options-and-prior-art.md` (factory section),
  `research/007-cold-before-baselines.md` (factory table = the BEFORE),
  `telemetry-attribute-scheme.md` (how factory spans route).

## The binding constraint, measured 2026-09-02

**fabro's docker provider has no volume / bind-mount knob.** The environment
reference (`fabro docs/public/execution/environments.mdx`, and the 0.254.0 server
hp runs) exposes only `image.docker|dockerfile`, `resources.cpu|memory|disk`,
`network.mode`, `labels`, `lifecycle.auto_stop`, `env`, `cwd`. Nothing mounts a
host path into the sandbox. So the shapes the console items were filed with
(bind-mount `/data/cache/cargo`, bind-mount `/data/cache/sccache`) are impossible
without a fabro feature. What the sandbox DOES have:

- the docker bridge: `172.17.0.1` on the host is reachable (the cargo telemetry
  shim POSTs to `172.17.0.1:4318` today — a proven seam);
- the image itself, rebuilt per dev-tooling release and fanned out to the
  console pin automatically (v1.37.x rollouts proved the path);
- `[environments.livespec-ci.env]` in the console workflow.toml for env vars.

## Decided shapes (recommendation recorded; execute unless objected)

1. **Registry (qxjdan) → PRE-WARMED IMAGE.** At image build, `cargo fetch` the
   locked dependency set of every routed Rust repository (start with the console;
   the tier-1 warm-cache populator's `values-*.yaml` routing is the list) into the
   image's `CARGO_HOME` registry. Zero runtime coupling, hermetic, refreshed per
   release. Cost: image size (~+0.3-0.5 GB for the console lockfile). Eviction:
   generations are the image tags; the fleet's existing image-prune (72 h unref)
   bounds them — age-based by construction. Miss cost is unchanged from today (a
   crate not in the baked set downloads as now).
2. **sccache (di6fn5) → host-side backend over the bridge.** Bake `sccache` into
   the python-rust-agent image; set `RUSTC_WRAPPER=sccache`, `CARGO_INCREMENTAL=0`
   and a remote-backend URL in the console `livespec-ci` env pointing at a small
   host service on `172.17.0.1` (webdav via a minimal server, or redis/memcached;
   pick the one fabro-hosts can run as a systemd unit with the least surface).
   The cache directory lives on hp `/data/cache/sccache`. Eviction: sccache's
   backend has no age policy, so fabro-hosts ships an age janitor timer
   (`find -atime +N` over the object store) — decided here, satisfying the
   charter's letter, not just its spirit. Concurrency: content-addressed, safe for
   15 parallel runs.
3. **Deferred:** shared `CARGO_TARGET_DIR` (impossible without a mount, and
   convoying anyway); fabro mount feature request (slowest path; file upstream
   only if 1+2 leave compile dominant).

## BEFORE (from console research/007, v1.37.1 shim, per cargo invocation)

| span | P50 s | P95 s | MAX s |
|---|---|---|---|
| build.cargo-llvm-cov | 9.59 | 29.07 | 61.51 |
| build.cargo-test | 7.82 | 31.86 | 61.67 |
| build.cargo-build | 0.13 | 49.75 | 50.40 |
| on-host pre-push `just check` (2026-07-30) | 251–273 s wall on 4 vCPU | | |

AFTER for each shape: the same Honeycomb query (github-ci, name starts-with
`build.cargo-`, repo = console, P50/P95/MAX) over ≥10 organic dispatches; once
the receiver allowlist fix lands (orchestrator PR, console item -elt9) the same
spans can be filtered by `build.env=factory` and `build.phase`.

## Sequencing

Registry image first (smallest, no new host service), measure; then sccache with
its host backend + janitor, measure against the registry-warm numbers so the two
wins are separable. Each lands with its eviction. Results are recorded on the
console children and roll into the console Phase-3 report.
