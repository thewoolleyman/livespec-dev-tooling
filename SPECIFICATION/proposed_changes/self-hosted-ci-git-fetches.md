---
topic: self-hosted-ci-git-fetches
author: claude-opus-5-5 (ci-runtime-and-cost)
created_at: 2026-11-12T14:00:53Z
---

## Proposal: A self-hosted CI job answers GitHub's 401 on a git fetch with its own GITHUB_TOKEN through a 401-only credential helper

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds a paragraph to non-functional-requirements.md section "Hooks and CI". Every gating CI workflow of a fleet repository MUST give its jobs a git credential helper for https://github.com that answers with username x-access-token and the job's own GITHUB_TOKEN. Git consults that helper only when GitHub answers 401, so fetches stay anonymous until GitHub refuses one. The workflow MUST NOT rewrite remote URLs to embed a token, which would also rewrite pushes and replace an App token, and MUST NOT introduce a new token or widen a token's scope. Adds one scenario.

### Motivation

Since ~13:20Z on 2026-11-12 GitHub has intermittently answered ANONYMOUS git fetches from the homelab NAT egress (73.231.243.71) with 401, which git prints as "could not read Username for 'https://github.com'". On the self-hosted ARC pool that failed uv's git-source fetch of livespec-dev-tooling and the sibling clones: livespec master CI went red on 8d5c466a9 and 65cc0e6e4 and needed a re-run to go green. Work item livespec-dev-tooling-fc4dzb carries the fix (the stop-the-line routed by legacy-coordinator-agent). Its filing judgement holds it at spec-change tier, verdict unstated, on this topic under "## Hooks and CI": no ratified clause says how self-hosted CI authenticates its git fetches. The fleet rule the coordinator set is NO NEW CREDENTIAL anywhere. Gates read from the in-cluster git mirror (livespec-dev-tooling-reuqym) with a bounded forge retry as fallback, and CI uses the token every job already holds. A credential helper is chosen over url.insteadOf, because insteadOf also rewrites pushes and would silently swap a bump or release job's GitHub App token for GITHUB_TOKEN.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Hooks and CI", append the following paragraph after the paragraph that begins "**Reuse outcomes are recorded and fallbacks reach the maintainer.**":

**Self-hosted CI answers GitHub's 401 on a git fetch with the job's own token.** Every gating CI workflow of a fleet repository MUST give its jobs a git credential helper for `https://github.com` that answers with username `x-access-token` and that job's own `GITHUB_TOKEN`, so that a git fetch GitHub refuses anonymously with 401 is retried authenticated rather than failing. The helper MUST reach every system-git caller in the job, uv git sources and sibling clones included. Configuring it MUST write no file, and it MUST neither override nor be overridden by another writer's git configuration. The configured value MUST NOT contain the token: the helper reads the token from the environment when git calls it. For example, the workflow can set the helper through its `GIT_CONFIG_PARAMETERS` environment variable, which git reads after any `GIT_CONFIG_COUNT` set. A fork pull request's `GITHUB_TOKEN` is read-only, which is enough for public fetches, so the rule holds for fork runs too. The workflow MUST NOT rewrite remote URLs to embed a token, because such a rewrite applies to pushes too and would replace a push's explicit credential. It MUST NOT introduce a new token or widen any token's scope.

In SPECIFICATION/scenarios.md, insert the following scenario immediately after "## Scenario: a stale detector reaches the maintainer":

## Scenario: a self-hosted CI git fetch that GitHub refuses anonymously completes with the job's own token

Given a gating CI job of a fleet repository on the self-hosted pool

And GitHub answers that job's anonymous git fetch of https://github.com/thewoolleyman/livespec-dev-tooling.git with 401

When git asks for credentials for https://github.com

Then the job's credential helper MUST answer with username x-access-token and the job's own GITHUB_TOKEN

And the fetch MUST complete without "could not read Username for 'https://github.com'"

And a push in that job made with an explicit GitHub App credential MUST still authenticate as the App
