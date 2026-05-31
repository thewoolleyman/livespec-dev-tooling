# livespec_dev_tooling/testing/

The single canonical CLI end-to-end test harness (per
`livespec/SPECIFICATION/contracts.md` §"CLI end-to-end harness contract").
`cli_e2e` exports the importable `test_workflow_full_round_trip` entry point
plus its discovery / fixtures / coverage-gate / orchestration components.
Consumers import it and wire it into their own `tests/e2e-cli/` collection.

Local constraints for an agent editing this directory:

- The harness drives the `claude` CLI binary itself — it MUST NOT reach
  around to wrapper Python files and MUST NOT depend on cache layout.
- The one mocked boundary is the `claude -p` subprocess (the `CliRunner`
  seam); discovery, fixture loading, the coverage gate, and orchestration
  always run for real.
- Tier selection rides the family-wide `LIVESPEC_E2E_HARNESS=mock|real`
  selector — do NOT invent a new env-var dialect.
- These are library helpers consumed via import, NOT `python -m`-invocable
  checks.
