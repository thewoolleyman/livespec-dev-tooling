---
topic: a-bump-to-a-livespec
author: claude-opus-5-5 (ci-runtime-and-cost)
created_at: 2026-11-12T10:34:22Z
---

## Proposal: Every bump to a dev-tooling tag waits until that tag's sandbox image tags are served

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Moves the sandbox-image readiness rule from the release fan-out alone onto every path that opens a bump PR to a livespec-dev-tooling tag. In contracts.md section "Cross-repo coordination automation surface", reusable-bump-pin-from-dispatch.yml gains a readiness paragraph: for source_repo livespec-dev-tooling it MUST NOT open a bump PR until ghcr.io serves all six livespec-fabro-sandbox semver layers of the tag. It polls for at most 90 minutes and, on absence, fails naming each missing tag and opens no PR. reusable-pin-freshness.yml gains the non-waiting form: it MUST NOT open a bump PR to a livespec-dev-tooling tag whose layers are not all served, and it leaves that bump to a later sweep. Two scenarios are added to scenarios.md. The fan-out's own wait in reusable-release-dispatch.yml is unchanged.

### Motivation

On 2026-11-12 the ci-runtime-and-cost seat sent a direct sibling-released repository_dispatch for livespec-dev-tooling v1.200.0 to livespec-console-beads-fabro at 09:54:55Z. The release fan-out's "await sandbox image tags" job did not finish until 10:08:54Z. The direct dispatch had nothing to wait on, because the readiness rule (v087, livespec-dev-tooling-3e3tlw and livespec-dev-tooling-epcoja) lives only in reusable-release-dispatch.yml. Bump PR livespec-console-beads-fabro#1356 opened at once, and its CI run 43195744727 failed 6 jobs on ErrImagePull NotFound for livespec-fabro-sandbox:python-rust-v1.200.0 and python-rust-fuzz-v1.200.0. Kueue admitted every runner pod within 1 s, so the cause was the missing image, not capacity. The same race is open to reusable-pin-freshness.yml, which reuses the bump machinery and can run between a release's publication and its image push. A bump to a tag whose image does not exist is not a usable bump on any trigger path. So the readiness rule belongs in the workflow that opens the PR, where every path passes, and not only in one caller of it. legacy-coordinator-agent agreed this fix route on 2026-11-12.

### Proposed Changes

In SPECIFICATION/contracts.md, section "## Cross-repo coordination automation surface", subsection "#### `reusable-bump-pin-from-dispatch.yml`", insert the following paragraph after the paragraph that begins "Behavior: clones the consumer repository":

Sandbox-image readiness (livespec-dev-tooling tags only): when `source_repo` is livespec-dev-tooling, the workflow MUST NOT open or update a bump PR until ghcr.io serves a manifest for each of the tag's semver-tagged livespec-fabro-sandbox layers (base-v<T>, python-v<T>, python-agent-v<T>, python-rust-v<T>, python-rust-agent-v<T>, python-rust-fuzz-v<T>), whichever path dispatched it: the release fan-out, a direct sibling-released dispatch, or a manual re-dispatch. It MUST poll for them for at most 90 minutes. When any is still absent at that bound, the run MUST fail with an annotation naming each missing tag, and it MUST NOT open a bump PR. A bump for any other `source_repo` MUST NOT wait.

In the same section, subsection "#### `reusable-pin-freshness.yml`", append the following sentence to the paragraph that begins "Behavior: runs the pin-autodiscovery walk":

The sweep MUST NOT open a bump PR to a livespec-dev-tooling tag unless ghcr.io serves a manifest for each of that tag's six semver-tagged livespec-fabro-sandbox layers. It MUST NOT wait for them. It MUST annotate each missing tag and leave that bump to a later sweep.

In SPECIFICATION/scenarios.md, append the following two scenarios after "## Scenario: a dev-tooling release fan-out whose sandbox image never appears fails naming the missing tags":

## Scenario: a direct sibling-released dispatch opens its dev-tooling bump PR only after the sandbox image tags are served

Given a livespec-dev-tooling release T whose livespec-fabro-sandbox semver tags are not yet served by ghcr.io

And a consumer that pins livespec-dev-tooling

When a sibling-released dispatch for T reaches that consumer directly, without the release fan-out

Then the consumer's bump workflow MUST open no bump PR while any of T's tags is absent

And it MUST open the bump PR to T once all of T's tags are served

## Scenario: a pin-freshness sweep opens no bump to a dev-tooling release whose sandbox image tags are not served

Given a livespec-dev-tooling release T that is the latest release, and whose python-rust-v<T> sandbox image tag is not served by ghcr.io

And a consumer whose livespec-dev-tooling pin is behind T

When the consumer's pin-freshness sweep runs

Then it MUST open no bump PR to T

And it MUST annotate the missing python-rust-v<T> tag
