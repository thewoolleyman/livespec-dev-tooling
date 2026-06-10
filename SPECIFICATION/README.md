# livespec-dev-tooling — SPECIFICATION

This directory is the live specification for the `livespec-dev-tooling` library. Every change to spec content lands through livespec's propose-change / revise loop per the contracts in `livespec/SPECIFICATION/contracts.md`.

## Files

- `spec.md` — project intent, architecture, Definition of Done, non-goals.
- `contracts.md` — wire-level and CLI-level interfaces (the semver-stable surface).
- `constraints.md` — architecture-level invariants (runtime, dependencies, semver discipline, CLI shape, no-network-I/O, self-application).
- `non-functional-requirements.md` — contributor-facing invariants (TDD discipline, lint/type rule sets, coverage gate, hooks, CI shape, commit discipline).
- `scenarios.md` — acceptance scenarios in Gherkin form.

## History

The `history/v001/` directory holds the snapshot ratified at seed time. Subsequent `vNNN/` snapshots accrete as each revise pass lands.

## Governance

The active implementation plugin (`livespec-impl-beads` per this repo's `.livespec.jsonc`) tracks work items and memos in this repo's per-repo beads Dolt tenant (tenant name `livespec-dev-tooling`). The `compat` block under the `livespec-dev-tooling` top-level key in `.livespec.jsonc` declares the supported livespec semver range and the currently-pinned livespec release tag per `livespec/SPECIFICATION/contracts.md` §"Cross-repo coordination — pin-and-bump".
