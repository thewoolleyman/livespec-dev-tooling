# 001 — Charter: transparent build-cache tiers for every CI job on the runner pool

Opened 2026-09-04 by the maintainer, from the `poweredge-raid-array-maintenance`
storage session in the `livespec` repo (epic `livespec-g52yrb`), after the
question "where is the actual GitHub Actions cache stored?" surfaced that the
fleet's Rust builds were the main reason for moving CI onto `poweredge-xubuntu`
in the first place — huge caches, the unraisable 10 GB per-repo cap on GitHub's
hosted cache, and eviction — and that nothing on the box serves them today.

This plan lives in `livespec-dev-tooling` because the mechanism is the runner
pool's GitOps under `ci-runner/k3s/` (tier 1 already ships from
`ci-runner/k3s/phase2/warm-cache/` and `phase2/arc/hook-pod-template.yaml`),
which this repo owns for every routed repository.

## Maintainer requirements (stated 2026-09-04, verbatim intent)

- The cache applies across ALL repositories and everything that runs CI on
  this box — it is pool infrastructure, not one repository's concern.
- It is TRANSPARENT to each repository's Actions configuration: no per-repo
  `actions/cache` steps or keys to duplicate. "Just like GitHub's CI" in the
  sense that a repository routed to the pool gets caching without opting in.
- It lives on LOCAL DISK on the host (not a network round-trip), so it is
  both unbounded by the 10 GB cap and faster than the hosted service.
- Rust builds are the primary consumer (they were "huge" and were being
  evicted from the hosted cache).

## What already exists, and what the record got wrong

- **Tier 1 (shipped 2026-08-23, `livespec-s43svm.2`)** is exactly the
  transparent shape, for `uv` only: one trusted CronJob populates a warm lower
  under the host's `/var/cache/ci-runner/warm`, every job pod mounts it
  READ-ONLY and copies the current generation into its work volume in
  `postStart`. Measured `uv sync` 7.9 s cold → 0.5 s warm, zero workflow
  changes. Design: `livespec` repo,
  `plan/archive/fleet-ci-runner-pool/research/design.md` §"Cache tiers".
- **`livespec-dev-tooling-9mp` (P1, filed 2026-07-17, OPEN, never started)**
  already specifies the Rust extension: persistent cargo registry + git,
  per-repo `target/` + sccache, uv cache, mounted into every job, TRUST-TIERED
  (PR/untrusted jobs read-only or throwaway-overlay; write-back only from
  post-merge trusted runs; per-repo namespaces). Its measurement is the one
  that matters: the console matrix on the self-hosted lane cold was 883 s
  versus 427 s hosted-with-cache — a 2x regression — because TEN concurrent
  jobs each cold-rebuild the same dependency graph and contend; a lone cold
  `cargo clippy` at 37 s (vs 53 s hosted-warm) was a benchmark with all 18
  cores to itself. It was written for the retired podman-container lane and
  needs re-scoping to k3s/ARC pods (hostPath + `postStart` copy, as tier 1).
- **The later cache-tier-2 design (2026-08-23) and the console's deleted cache
  steps cite the lone-build benchmark and not `9mp`.** That is the
  contradiction this plan resolves: the "cold beats warm" claim is true for
  one job and false for the matrix. The console repo's `.cargo/config.toml`
  cap of `build.jobs = 4` on every cargo invocation is itself evidence the
  contention is real.
- **Tier 2 (`livespec-s43svm.3`, closed 2026-08-29 deferred-by-decision)** is
  a local emulation of GitHub's KEYED `actions/cache` API. It is a different
  product: it serves workflows that keep `actions/cache` steps, and it is NOT
  transparent (every workflow still carries keys). Its recorded cost is that
  `actions/cache` v4 talks to the results endpoint the runner takes from
  GitHub's job message, and the official runner ignores an env override, so
  drop-in servers (falcondev-oss/github-actions-cache-server) require either
  their forked runner image or a hex-patched `Runner.Worker.dll` with
  self-update pinned off. **The maintainer is skeptical of that claim
  (2026-09-04) and it MUST be re-verified against the current runner source
  and the server's current docs before it is repeated** — see the open
  question below. Design: `livespec` repo,
  `plan/archive/fleet-ci-runner-pool/research/cache-tier-2-design.md`.

## Proposed shape (to be confirmed by this plan's first research pass)

Extend tier 1, do not build tier 2 first:

1. **Warm cargo registry + git lower**, populated by the SAME
   `warm-cache-populate` CronJob (`cargo fetch` against every routed repo's
   `Cargo.lock`; the `python-rust` sandbox image carries cargo), published as
   generations exactly like the uv lower, copied into the pod in `postStart`,
   `CARGO_HOME` pointed at the copy.
2. **sccache** — a compilation cache keyed on compiler inputs — served from
   the host, shared by every job pod (over the node IP) AND, if the
   `console-factory-build-cache` plan (`livespec-dev-tooling-3u3gm2`) lands
   its host-backed sccache for fabro sandboxes, the same service. One sccache
   on the host, two consumers. Trust tiering per `9mp`: the untrusted lane
   reads but cannot write, or gets its own throwaway namespace.
3. **Per-repo persistent `target/`** — the largest win for Rust and the
   hardest to trust-tier; scope it explicitly (trusted lane only, or skip in
   favour of sccache) in the first scope event.
4. **Capacity** — the storage plan sizes the array's `ci-cache` LV at 1 TiB
   for this (up from the 500 GiB first proposed), with online growth from
   the VG's free extents when needed.

Acceptance is the one `9mp` already states: the console's self-hosted matrix
wall-clock at or below the hosted warm-cache baseline (~430 s), with the PR
lane proven unable to write the trusted cache — plus, because the maintainer's
requirement is fleet-wide transparency, a second routed repository benefiting
with zero workflow changes.

## Open questions for the first research pass

1. Is the forked-runner cost of tier 2 real TODAY? Read the runner source for
   how `ACTIONS_RESULTS_URL` is set and whether any supported override exists
   (env, `.env` file, ARC `runnerEnv`), and re-read the cache server's current
   docs. If an unpatched path exists, tier 2 becomes cheap and the
   transparent-vs-keyed question is re-opened.
2. Does the maintainer's "transparent" requirement also cover the
   `actions/cache` steps repositories may keep for hosted-lane parity, or is
   the mount tier sufficient? (Today every fleet repo already skips those
   steps on the self-hosted lane.)
3. Can a read-only hostPath + `postStart` copy carry a multi-GB cargo
   `target/` without the copy itself costing more than it saves? Measure
   before choosing between copy, overlay, and sccache-only.

## Cross-references

- `livespec` repo, plan `poweredge-raid-array-maintenance`, epic
  `livespec-g52yrb` — the storage substrate; owes this plan the 1 TiB
  `ci-cache` LV.
- `livespec-dev-tooling` plan `console-factory-build-cache`, epic
  `livespec-dev-tooling-3u3gm2` — the fabro-sandbox consumer of a shared host
  sccache.
- `livespec` repo, `plan/archive/fleet-ci-runner-pool/research/design.md`
  §"Cache tiers" and §"Why uv only, not cargo", and
  `cache-tier-2-design.md` — the prior designs this plan corrects.
