---
topic: codex-acp-factory-gate
author: claude-opus-4-8
created_at: 2026-07-13T09:30:00Z
---

## Proposal: codex-acp external-source pin + factory-gated bump

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Contracts the cross-repo machinery that keeps the baked Codex ACP adapter
version (`CODEX_ACP_VERSION` in `docker/fabro-sandbox/base/Dockerfile`)
self-updating and safe. Adds a sixth pin-autodiscovery format — the FIRST
whose source is EXTERNAL to the fleet (the npm package
`@zed-industries/codex-acp`, queried via `npm view`, not a livespec release
tag) — and defines the live Codex-provider factory gate that MUST pass before
a codex-acp bump PR may merge. The gate is realized as a second
`repository_dispatch` event type (`codex-acp-golden-master`) plus a
`statuses: write` commit-status callback from the orchestrator, keeping the
version here and the credential test there (No-Circular-Dependency). Seven
verbatim replace-targets: four additions (the sixth pin format, the second
dispatch event type, `statuses: write`, and the gate subsection) plus three
neighbouring drift sweeps. It adds only an H3 subsection
(`### codex-acp factory gate`), so no `tests/heading-coverage.json` co-edit is
required — dev-tooling's heading-coverage check tracks H2 headings only.

### Motivation

Epic `livespec-3lev.4` (Phase 1, fabro-ci-image-factoring), design at
`livespec/plan/codex-acp-auto-bump/design.md`. The codex-acp version was
previously duplicated by hand across two repos (the image `ARG` and the
orchestrator's `@0.16.0` adapter pin). The orchestrator now drops its pin and
consumes the baked global fetch-free (`npx --no-install`), making the image
`ARG` the single source of truth. To keep that single pin fresh WITHOUT
silently advancing to an unverified version — the exact credential-projection
drift the pin guards against (`bd-ib-ss7rkr`) — the pin becomes self-updating
via a scheduled bump PR that is GATED by a real Codex-provider golden-master
run. This proposal is the dev-tooling contract for that machinery; the
orchestrator-side gate workflow (dispatch handler + status callback) is
already implemented and consumes this contract.

### Proposed Changes

Seven verbatim replace-targets in `SPECIFICATION/contracts.md` (each FIND
block exists once in the live file; re-verify against origin/master before
applying). Four are the additions; three are neighbouring drift sweeps the
additions would otherwise falsify.

=== Replace-target A (REQUIRED — sixth pin-autodiscovery format) ===
Insert a new bullet after the fabro-sandbox docker bullet, before the
tolerance paragraph.

FIND (verbatim):
```
The record is emitted only when the `--source-repo` filter is absent or equals `livespec-dev-tooling`, per the standard source-repo-filter semantics.

The walk MUST be tolerant of missing files
```

REPLACE WITH:
```
The record is emitted only when the `--source-repo` filter is absent or equals `livespec-dev-tooling`, per the standard source-repo-filter semantics.
- **codex-acp Dockerfile `ARG`** — the `ARG CODEX_ACP_VERSION=<version>` line in `docker/fabro-sandbox/base/Dockerfile`. `pin_key` is `CODEX_ACP_VERSION`; `current_value` is the bare npm semver `<version>` (no `v` prefix). Unlike every other format, this pin's source is EXTERNAL to the fleet: the npm package `@zed-industries/codex-acp` — the Codex ACP adapter baked into the fabro-sandbox image and run by the orchestrator's implementer nodes. Its latest version is therefore queried from the npm registry (`npm view @zed-industries/codex-acp version` — the `latest` dist-tag published to the same npm package the base Dockerfile's `npm install -g` bakes from), NOT from a fleet release tag, and it is bumped whenever the npm `latest` differs from `current_value` (the `staleness_threshold_releases` ordinal-distance measure does not apply to a non-fleet source). The record is emitted only when the `--source-repo` filter is absent (the freshness scan) or equals its external source `zed-industries/codex-acp`; no fleet release fan-out (`--source-repo <fleet-repo>`) ever matches it, so a `sibling-released` bump can never rewrite `CODEX_ACP_VERSION`. Because a bump changes the baked Codex adapter, the resulting bump PR is gated by a live Codex-provider factory run — see §"codex-acp factory gate".

The walk MUST be tolerant of missing files
```

=== Replace-target B (REQUIRED — dispatch intro drift sweep) ===
The §"`repository_dispatch` payload contract" intro claims EVERY event carries
the sibling-released shape; the gate adds a second shape, falsifying it.

FIND (verbatim):
```
Every `repository_dispatch` event fired by the coordination surface MUST carry the following shape:
```

REPLACE WITH:
```
The release fan-out fires `repository_dispatch` events carrying the following shape:
```

=== Replace-target C (REQUIRED — second event type) ===
FIND (verbatim):
```
The `event_type` value is fixed at the literal `"sibling-released"`. The `client_payload` shape is the semver-stable contract; adding new fields is a MINOR bump, removing or renaming existing fields is a MAJOR bump.
```

REPLACE WITH:
```
The release fan-out's `event_type` value is fixed at the literal `"sibling-released"`. The `client_payload` shape is the semver-stable contract; adding new fields is a MINOR bump, removing or renaming existing fields is a MAJOR bump.

The coordination surface fires exactly ONE additional `repository_dispatch` event type — `"codex-acp-golden-master"` — which triggers the live Codex-provider factory gate for a codex-acp version bump (see §"codex-acp factory gate"). Its `client_payload` shape is:

    {
      "event_type": "codex-acp-golden-master",
      "client_payload": {
        "codex_acp_version": "<bare npm semver, e.g. 0.17.0>",
        "head_sha": "<the codex-acp bump PR head commit SHA>",
        "pr_number": <int>,
        "source_repo": "livespec-dev-tooling"
      }
    }

The same semver-stable field-shape discipline applies (adding fields MINOR, removing or renaming MAJOR). These two are the only event types the coordination surface fires.
```

=== Replace-target D (REQUIRED — App gains statuses: write) ===
FIND (verbatim):
```
- `metadata: read` — to read repository metadata for sibling discovery.
```

REPLACE WITH:
```
- `metadata: read` — to read repository metadata for sibling discovery.
- `statuses: write` — to post the codex-acp factory-gate commit-status callback (context `codex-acp-golden-master`) onto the codex-acp bump PR's head commit in this repository (see §"codex-acp factory gate"). The orchestrator's gate workflow mints a `livespec-dev-tooling`-scoped installation token to post it.
```

=== Replace-target E (RECOMMENDED — freshness-threshold drift sweep) ===
The threshold-defaults paragraph describes ordinal distance over release
tags, inapplicable to the external npm source.

FIND (verbatim):
```
The `staleness_threshold_releases` input to `reusable-pin-freshness.yml` defaults to `1` — any pin one or more releases behind the latest tag triggers a bump PR. A consumer MAY override via the input on its `pin-freshness.yml` shim if its cadence demands higher tolerance for drift.
```

REPLACE WITH:
```
The `staleness_threshold_releases` input to `reusable-pin-freshness.yml` defaults to `1` — any fleet-release pin one or more releases behind the latest tag triggers a bump PR. A consumer MAY override via the input on its `pin-freshness.yml` shim if its cadence demands higher tolerance for drift. The ordinal-distance measure applies only to fleet-release-tag sources; the external-source codex-acp Dockerfile `ARG` pin (§"Pin autodiscovery rules") is bumped on any npm `latest` version difference and is not governed by `staleness_threshold_releases`.
```

=== Replace-target F (REQUIRED — new §"codex-acp factory gate" subsection) ===
Insert a new subsection immediately after the §"Fallback to known-good pin"
section (which governs required-check gating on bump PRs) and before
§"Retry semantics (rerun vs fresh dispatch)".

FIND (verbatim):
```
The `bump-pin` workflow MUST NOT silently force-push past a failing check. The auto-merge label is the consumer's standard auto-merge label (configurable per consumer via repo settings); the workflow only attaches the label, it does not bypass branch-protection gates.

### Retry semantics (rerun vs fresh dispatch)
```

REPLACE WITH:
```
The `bump-pin` workflow MUST NOT silently force-push past a failing check. The auto-merge label is the consumer's standard auto-merge label (configurable per consumer via repo settings); the workflow only attaches the label, it does not bypass branch-protection gates.

### codex-acp factory gate

The codex-acp Dockerfile `ARG` pin (§"Pin autodiscovery rules") bakes the Codex ACP adapter version the orchestrator's implementer nodes run on. Because a bump changes the agent runtime that authenticates via the non-rotatable credential-projection snapshot, a codex-acp bump PR MUST NOT merge until a real Codex-provider factory run has proven the new version still works end-to-end. That live run IS the credential-projection re-verification the pin exists to guarantee; a merged-then-unverified bump is exactly the silent drift the pin guards against.

The gate is realized cross-repo as an event dispatch plus a commit-status callback — NEVER a code read from this library into the orchestrator. The version lives here; the credential test lives in `livespec-orchestrator-beads-fabro`; the orchestrator consuming this library's baked image is a consumer→producer relationship. This keeps the coupling cycle-free per the No-Circular-Dependency directive.

- **Dispatch.** After the pin-freshness surface opens a codex-acp bump PR, it fires a `repository_dispatch` event of type `"codex-acp-golden-master"` (payload per §"`repository_dispatch` payload contract") at `livespec-orchestrator-beads-fabro`, carrying the new version and the bump PR's head SHA and number.
- **Gate run.** The orchestrator runs its live golden-master acceptance tier with the Codex implementer adapter against the new version, exercising the real credential projection end-to-end. The orchestrator's implementer adapter MUST resolve the baked codex-acp global VERSION-LESS (`npx --no-install`) for the gate to be evidence about the new version; a version-pinned adapter command would shadow the overlaid version and render the gate vacuous.
- **Callback.** The gate posts a commit status back to the bump PR's head SHA in this repository with context `"codex-acp-golden-master"` and state `success` or `failure`, authenticated by the App's `statuses: write` permission (§"GitHub App auth model").
- **Merge gate (fail-closed, no required status check).** The codex-acp bump PR is opened WITHOUT auto-merge (unlike fleet-release bump PRs), so it cannot merge on its own. On a `success` gate run the orchestrator enables the bump PR's auto-merge (via the App's `contents: write` + `pull-requests: write`), and it then merges once this repository's normal required checks (`ci-green`) pass; on a `failure` run the gate leaves auto-merge disabled and the PR open for a human (per §"Fallback to known-good pin"). The cross-repo status is deliberately NOT wired as a GitHub required status check: GitHub scopes required checks to the base branch, so requiring this context would block every unrelated PR that never receives it, AND it would violate §"`branch_protection_alignment` check" (a required check with no matching `ci.yml` job fails alignment). The fail-closed "auto-merge is enabled only by a green gate" mechanism gates the bump without a required check — if the gate never runs, the bump never merges. The last verified codex-acp version stays baked until a green run.

The gate is specific to the codex-acp external-source pin; fleet-release bump PRs (`sibling-released`) are unaffected.

### Retry semantics (rerun vs fresh dispatch)
```

=== Replace-target G (REQUIRED — freshness-workflow Behavior drift sweep) ===
The §"`reusable-pin-freshness.yml`" Behavior paragraph describes gh-release /
ordinal-distance querying, false for the npm-sourced codex-acp record.

FIND (verbatim):
```
Behavior: runs the pin-autodiscovery walk per §"Pin autodiscovery rules", queries each discovered source repository's latest release tag via `gh release view --json tagName`, and opens a bump PR per `(source_repo, current_pin, latest_tag)` triple where the latest tag is at least `staleness_threshold_releases` ahead of the current pin. Reuses the bump-PR-opening machinery from `reusable-bump-pin-from-dispatch.yml`.
```

REPLACE WITH:
```
Behavior: runs the pin-autodiscovery walk per §"Pin autodiscovery rules", queries each discovered FLEET source repository's latest release tag via `gh release view --json tagName`, and opens a bump PR per `(source_repo, current_pin, latest_tag)` triple where the latest tag is at least `staleness_threshold_releases` ahead of the current pin. The external-source codex-acp Dockerfile `ARG` record has no fleet source repository: its latest version is queried from the npm registry (`npm view @zed-industries/codex-acp version`) and it opens a bump PR on any difference from `current_value` (per §"Pin autodiscovery rules"), which is then factory-gated (per §"codex-acp factory gate"). Reuses the bump-PR-opening machinery from `reusable-bump-pin-from-dispatch.yml` (for the codex-acp record, opened WITHOUT auto-merge, per §"codex-acp factory gate").
```
