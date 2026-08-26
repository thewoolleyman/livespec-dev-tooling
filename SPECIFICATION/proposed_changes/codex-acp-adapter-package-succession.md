---
topic: codex-acp-adapter-package-succession
author: claude-fable-5
created_at: 2026-08-26T06:37:53Z
---

## Proposal: Codex ACP adapter package succession: the codex-acp pin sources @agentclientprotocol/codex-acp

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The external-source codex-acp Dockerfile `ARG` pin changes WHICH npm package it pins: from the deprecated, terminal `@zed-industries/codex-acp` (last release 0.16.0) to its published successor `@agentclientprotocol/codex-acp`. Every place §"Pin autodiscovery rules" and §"`reusable-pin-freshness.yml`" name the package or its `source_repo` literal moves to the successor, and the section gains the rules a package succession needs that a version bump never did: a transitional co-install line for the predecessor that is not autodiscovered and not bumpable, a deliberate bin-link override because both packages export the same `codex-acp` bin, and resolution by package NAME rather than by the bare bin.

### Motivation

Maintainer commission (relayed by the homelab plan session, 2026-08-26): the factory's review node must run gpt-5.6-terra at xhigh. The fabro-sandbox agent image bakes `@zed-industries/codex-acp@0.16.0`, which vendors Codex rust-v0.137.0 and cannot reach the 5.6 model line ("requires a newer version of Codex", measured 2026-08-22). Measured against npm on 2026-08-26: 0.16.0 is that package's LAST release and the registry marks it deprecated ("This package has been replaced by @agentclientprotocol/codex-acp"); the successor's `latest` is 1.6.2 (published 2026-08-20), bundling `@openai/codex ^0.148.0` (resolves 0.148.0) and exporting the same bin name `codex-acp`. Measured inside `ghcr.io/thewoolleyman/livespec-fabro-sandbox:python-rust-agent-v1.32.1` (node 26.3.0, npm 11.16.0): a plain `npm install -g @agentclientprotocol/codex-acp@1.6.2` alongside the baked predecessor FAILS with `EEXIST: file already exists: .../bin/codex-acp`; with `--force` both packages coexist in the global root, `npx --no-install @agentclientprotocol/codex-acp --version` reports 1.6.2, the bundled `codex --version` reports codex-cli 0.148.0, and the bare `codex-acp` link points at the successor. The ratified text currently names `@zed-industries/codex-acp` as the pinned package and `zed-industries/codex-acp` as the `source_repo` literal in two sections, so the implementation change is spec-tier: the walker's `source_repo`, the freshness scan's `npm view` query, and the factory-gate step conditions all key on that literal. The freshness scan cannot perform a package succession on its own — it only ever compares versions of the package the spec names — which is why this is a deliberate manual change and why the spec must say which package is current.

### Proposed Changes

In §"Pin autodiscovery rules", the **codex-acp Dockerfile `ARG`** bullet is amended as follows.

1. Every occurrence of the package name `@zed-industries/codex-acp` is replaced by `@agentclientprotocol/codex-acp`, and every occurrence of the `source_repo` literal `zed-industries/codex-acp` is replaced by `agentclientprotocol/codex-acp`. The npm query becomes `npm view @agentclientprotocol/codex-acp version`. The record MUST be emitted only when the `--source-repo` filter is absent or equals `agentclientprotocol/codex-acp`; the rule that no fleet release fan-out ever matches it, and that a `sibling-released` bump can never rewrite `CODEX_ACP_VERSION`, is unchanged.

2. The following sentences are appended to that bullet:

> The pinned package's predecessor, `@zed-industries/codex-acp`, is deprecated on npm at its terminal release `0.16.0` and MUST NOT be the autodiscovered source. `CODEX_ACP_VERSION` pins exactly ONE package — the one this bullet names — and changing WHICH package it pins is a package succession, not a version bump: the freshness scan MUST NOT perform it, and it MUST be carried by a deliberate change to this section and to the agent Dockerfile together. During a package-succession cutover the agent Dockerfile MAY additionally bake the predecessor on a TRANSITIONAL install line that carries a literal version, declares no `ARG`, is not walked by autodiscovery, and is never bumped; such a line MUST state the condition for its own removal. Because both packages export the same `codex-acp` bin, a transitional co-install MUST override the global bin link deliberately (`npm install -g --force`) rather than leave the install order to decide which package owns it, and the successor SHOULD own the link. Every consumer of the baked adapter MUST resolve it by package NAME (`npx --no-install <package>`), never by the bare `codex-acp` bin, so that the adapter a dispatch runs is the one its rendered command names regardless of which package owns the link.

In §"`reusable-pin-freshness.yml`", the Behavior paragraph's parenthetical `npm view @zed-industries/codex-acp version` becomes `npm view @agentclientprotocol/codex-acp version`; the rest of the sentence is unchanged.

No other section changes. In particular §"codex-acp factory gate" keeps its version-bump gate exactly as ratified; the proof a package succession owes while that gate's receiver is disabled is the subject of the companion proposal in this file.

## Proposal: Equivalent proof for a deliberate adapter package succession while the live golden-master receiver is disabled

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

§"codex-acp factory gate" today says the baked adapter MUST NOT change until a live Codex-provider factory run proves it, records that the live receiver is administratively disabled, and defers to "a later spec revision" to define an equivalent proof. This proposal is that revision for exactly one case: a deliberate package succession (a manual PR, not a freshness-scan bump, that changes which package `CODEX_ACP_VERSION` pins). It defines a three-part equivalent proof — the predecessor stays baked and unchanged on the cutover release, the successor is verified inside a build of the agent layer at the PR head, and the predecessor is removed only after a real factory dispatch has run on the successor — and adds the scenario that states it.

### Motivation

The factory-gate section was written for version bumps of one package, which the freshness scan opens and the orchestrator's live golden-master proves. Two facts make it unable to cover this change: the golden-master receiver is administratively disabled (already ratified in this section and in the scenario "a codex-acp bump remains parked while the live receiver is disabled"), and the orchestrator's golden-master pin step hardcodes the OLD package name, so even a green run before the orchestrator's own cutover would be evidence about the wrong package (confirmed by the orchestrator session on 2026-08-26, which owns that repoint as its E2 criterion 7). Without an equivalent proof the section's literal reading is that the baked adapter can never change, which would leave the factory permanently unable to reach the Codex 5.6 line the maintainer commissioned. The proof below is what this change actually does and can be checked from the PRs alone: the cutover release keeps 0.16.0 baked so every existing dispatch keeps resolving the last verified version (the section's own guarantee), the successor is verified in-image at the PR head (`npx --no-install @agentclientprotocol/codex-acp --version` = 1.6.2; bundled codex-cli 0.148.0, measured 2026-08-26), and the predecessor is removed only after the orchestrator confirms a real dispatch on hp or vps ran on the successor, cited by run id. Behavior-bearing clauses need a scenario per the authoring discipline; the existing codex-acp scenario in scenarios.md is followed as the placement precedent.

### Proposed Changes

In §"codex-acp factory gate", immediately after the paragraph beginning "While the privileged host-only golden-master receiver workflow remains administratively disabled", insert:

> A deliberate **package succession** — a change to WHICH npm package `CODEX_ACP_VERSION` pins (§"Pin autodiscovery rules"), carried by a manual PR rather than opened by the freshness scan — is not a version bump: it receives no `codex-acp-golden-master` dispatch and cannot be proven by a gate whose pin step names the predecessor package. While the live receiver is disabled, the following is the equivalent proof for a package succession, and each part MUST be recorded on the PR that carries it: (1) the cutover release MUST keep the last verified predecessor version baked and unchanged on a transitional line, so every dispatch that still resolves the predecessor by name keeps running the last verified adapter; (2) the successor MUST be verified inside a build of the agent layer at the PR head, by resolving it by package name (`npx --no-install <successor> --version` MUST report the value `CODEX_ACP_VERSION` pins) and by the bundled Codex binary reporting at least the version the succession was undertaken to reach; (3) the predecessor MUST NOT be removed from the image until a real Codex-provider factory dispatch has run on the successor on a factory host, and the removal PR MUST cite that run. A succession that skips any part is the unverified adapter change this section exists to prevent, and MUST NOT merge.

In `scenarios.md`, immediately after the scenario "a codex-acp bump remains parked while the live receiver is disabled" and in the same form (a `Scenario:` line with Given/When/Then), add:

Scenario: a codex-acp package succession proves itself without the live receiver

Given the codex-acp pin's package is succeeded by a deliberate manual PR rather than a freshness-scan bump

And the privileged host-only golden-master receiver workflow is administratively disabled

When the cutover release is built

Then the predecessor package remains baked and unchanged on a transitional line

And the successor resolves by package name inside a build of the agent layer at the PR head, reporting the pinned version and a bundled Codex binary at least as new as the succession requires

And the predecessor is removed only by a later PR that cites a real Codex-provider factory dispatch that ran on the successor

And a succession that skips any of those parts MUST NOT merge.
