# 001 — Charter: factory-sandbox build-time telemetry (build.env=factory)

This dev-tooling plan is the CROSS-REPO leg of the console's build-time
optimization programme. It owns the livespec-dev-tooling changes that make each
fabro console run emit measured cargo build/check/test spans to Honeycomb, so the
console plan can capture its FACTORY before/after baselines.

## Parent / cross-references

- Console plan: `optimize-console-builds` in `livespec-console-beads-fabro`,
  plan epic `livespec-console-beads-fabro-gqmtwa`.
- The specific console child this delivers: `livespec-console-beads-fabro-2er6nc`
  ("Phase 1 telemetry: factory sandbox cargo build/check spans, build.env=factory")
  — factory-ineligible in the console tenant because the emission seam lives HERE
  (the fabro-sandbox image + its prepare.* span path). That child stays open in
  the console ledger tracking this cross-repo work; close/annotate it when this
  plan lands.
- Console research (read for facts): notes 003 (factory/hp-xubuntu), 005
  (Honeycomb telemetry gap), 006 (mechanism options) under
  `livespec-console-beads-fabro:plan/optimize-console-builds/research/`.

## Goal

Emit cargo build / check / test PHASE spans, tagged `build.env=factory`, for each
fabro console run — extending the EXISTING fabro-sandbox `prepare.*` emission seam
to the cargo phases, reusing its Honeycomb key path, and conforming to the shared
attribute scheme the console side already shipped.

## Measured facts (from console note 003, verified 2026-08-30)

- Factory host `hp-xubuntu`; fabro 0.254.0; one Docker sandbox container per run;
  image `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-agent-v1.36.0`;
  the `livespec-ci` env gets 4 CPU / 8 GB; no sccache in the image; each console
  run pays a cold crates.io download + full cold `target/` build (2–7 GB) thrown
  away with the container.
- The **fabro-sandbox Honeycomb dataset already receives `prepare.*` spans**
  (`prepare.mise-install`, `prepare.uv-sync`, `prepare.fetch-unshallow`,
  `prepare.commit-refuse-install`, …) — so a working span-emission seam and a
  Honeycomb key-delivery path ALREADY EXIST in the sandbox prepare path. This
  plan extends that seam to the cargo build/check/test phases; it does NOT need a
  new secret channel.

## Shared attribute scheme (already merged on the console side)

Conform to `livespec-console-beads-fabro`'s merged
`.github/telemetry-attribute-scheme.md` + `.github/scripts/emit-build-telemetry.sh`
(PR #893). Spans carry: `build.env` (here always `factory`), `build.phase`
(compile | test | …), `repo`, `git.commit.sha`, toolchain version.

## Scope boundary

- THIS plan owns: the livespec-dev-tooling changes — locating the `prepare.*`
  emitter + its key path in the fabro-sandbox image build, and extending it to
  wrap the cargo build/check/test phases of a console run with `build.env=factory`
  spans.
- The console plan owns: consuming the resulting factory spans into its Phase-1
  cold-baseline note (`livespec-console-beads-fabro-fhdzka`), and any downstream
  factory build OPTIMIZATIONS (shared registry mount, sccache, pre-warmed image)
  which are separately scoped under the console plan's Phase 2.

## Phasing / first steps

1. Locate the `prepare.*` span emitter and its Honeycomb key delivery in the
   fabro-sandbox image build (this repo; the image Dockerfile / sandbox prepare
   scripts).
2. Extend it to emit `build.env=factory` spans around the cargo build / check /
   test phases of a console run, conforming to the shared scheme.
3. Verify: a real fabro console run emits the new cargo-phase spans to the
   `fabro-sandbox` dataset (query in Honeycomb).
4. Report back on the console plan epic (`livespec-console-beads-fabro-gqmtwa`)
   so `fhdzka` can capture the factory cold BEFORE baseline, and dispose the
   `2er6nc` cross-repo child.

## Binding context inherited from the console programme

The console programme has three maintainer-set requirements: (1) Honeycomb
before/after measurement proves every improvement; (2) every cache tier ships
WITH bounded age/staleness eviction; (3) a final raw+% report is human-approved
before archive. This plan delivers requirement (1)'s FACTORY measurement leg —
without it, factory build optimizations cannot be measured before/after.

## Decision & implementation (2026-08-31, as shipped)

Two open questions in the framing above are RESOLVED here, from live probing of
the factory host `hp-xubuntu` and the merged console scheme; both supersede the
earlier "reuse the prepare.* KEY path" / "fabro-sandbox dataset" wording.

- **Dataset & transport — reuse the KEYLESS prepare.* seam, route to
  `github-ci`.** The `prepare.*` spans do NOT reach Honeycomb via a key in the
  sandbox; they POST to the host OTel receiver (`otel-receiver.service`, bound
  `172.17.0.1:4318`), which derives the Honeycomb dataset from the span's
  `service.name` resource attribute (`_otel_enrich_export.honeycomb_dataset_for`)
  and forwards with the host-held general fleet key `HONEYCOMB_INGEST_KEY_LIVESPEC`.
  So the factory build spans reach the merged scheme's `github-ci` dataset simply
  by carrying `service.name=github-ci` — NO `HONEYCOMB_BUILD_INGEST_KEY` need
  enter the sandbox (the scheme table's "family env wrapper injection" for the
  factory row is satisfied more directly by the receiver). Verified live: the
  receiver returns HTTP 200 for a `build.env=factory` / `service.name=github-ci`
  span, and the real emitter module POSTs successfully against it. This
  supersedes step 3's "fabro-sandbox dataset".
- **Wrap point — the image, not the workflow.** The console
  `.fabro/workflows/implement-work-item/workflow.toml` runs cargo via its AGENT
  and its git hooks (checkpoint pre-commit, final pre-push `just check`), NOT via
  a wrappable prepare step, and it deliberately does not invoke `livespec-step-timer`.
  The only console-change-free wrap point is therefore the fabro-sandbox IMAGE.
  Shipped as: `livespec_dev_tooling/otel_cargo_phase.py` baked as
  `/usr/local/bin/livespec-cargo-phase-timer`, plus a `cargo` shim on PATH ahead
  of the rustup cargo (python-rust layer) that runs the real cargo unchanged and
  best-effort emits one `build.env=factory` span per measured phase
  (compile/test/fuzz/fetch). The stopwatch is strictly non-fatal.
- **Failure contract.** The scheme's factory row ("emission failures surface
  immediately in the run log") is honored as LOUD-to-stderr-but-non-fatal: a
  telemetry failure prints a visible line to the run log but never changes
  cargo's exit code, because the shim sits in the console's build critical path
  and breaking every console build to satisfy telemetry is the wrong trade.
