---
topic: the-publish-flake-retries-action
author: claude-opus-5-5
created_at: 2026-11-08T02:35:00Z
---

## Proposal: The publish-flake-retries composite Action's wire contract

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Codify the input/output contract of the `publish-flake-retries` composite Action in "## Composite Actions wire contract", as `spec.md` requires of every composite Action the library ships, and count it among the Actions the library MUST ship.

### Motivation

v156's "Flake-retry record delivery" bullet in `constraints.md` requires livespec, livespec-overseer and livespec-orchestrator-beads-fabro to publish their coverage job's `tmp/flake-retries/` records through this repository's shared `.github/actions/publish-flake-retries` composite Action at a released tag. livespec-dev-tooling-ljea46 lands that Action. `spec.md` says each composite Action's input/output contract MUST be codified in `contracts.md`, and "## Composite Actions wire contract" lists only `setup`, `run-check` and `github-rate-budget-token`. Without this entry the Action ships with no stated contract, and a consumer pinning it has nothing to hold a later change against.

The contract carries the artifact name, path and retention because v156 places them in the Action precisely so the host-side reader and its producers cannot drift. It also states which conditions stay with the caller: a composite step cannot read the caller's `needs` context, and the caller's own status check decides whether the Action runs at all.

### Proposed Changes

In `SPECIFICATION/contracts.md`, "## Composite Actions wire contract", replace this sentence:

The library MUST ship at minimum three composite Actions:

with this sentence:

The library MUST ship at minimum four composite Actions:

and add this bullet after the `github-rate-budget-token` bullet:

- **`publish-flake-retries`**. Inputs: `suffix` (optional, default `""`). Outputs: none. Permissions: none beyond the job's default artifact upload. Performs: one `actions/upload-artifact@v4` step that publishes `tmp/flake-retries/` with 7-day retention, as an artifact named `flake-retries` when `suffix` is empty and `flake-retries-<suffix>` otherwise. A job that runs more than once in one CI run MUST pass a `suffix` unique to that instance, because a workflow run cannot repeat an artifact name. The step MUST use `if-no-files-found: ignore`, so a job that re-ran no test uploads nothing and the Action does not fail the job. The CALLER's step MUST carry `!cancelled()`, so the Action publishes after the pytest step whether that step passed or failed, plus any expedited-incident omission guard its job uses. A composite step cannot read the caller's `needs` context or override the caller's own status check, so neither condition lives inside the Action. Consumers reference it as `uses: thewoolleyman/livespec-dev-tooling/.github/actions/publish-flake-retries@vX.Y.Z`. "Flake-retry record delivery" in `constraints.md` names the repositories that MUST use it.

No other sentence of the section changes, and no heading is added or removed, so `tests/heading-coverage.json` needs no co-edit.
