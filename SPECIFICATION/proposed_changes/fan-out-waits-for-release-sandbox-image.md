---
topic: fan-out-waits-for-release-sandbox-image
author: claude:delegated-gate-fleet-rollout
created_at: 2026-10-22T18:11:36Z
---

## Proposal: The dev-tooling release fan-out waits for that release's sandbox image

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

For a livespec-dev-tooling release T, the release fan-out MUST NOT send any sibling-released dispatch until ghcr.io serves a manifest for every semver-tagged livespec-fabro-sandbox layer of T. If any is still absent after a bounded wait, it MUST fail the run with an annotation naming the missing tags. Bump pull requests then never pin, or merge, an image tag that does not yet exist.

### Motivation

Measured 2026-10-22 (coordinator R612, work item livespec-dev-tooling-epcoja). release-dispatch.yml and fabro-sandbox-image.yml both trigger on release:published. v1.125.0 published at 10:38:18Z, consumer bump PRs opened at 10:43Z, and the python-rust-agent-v1.125.0 image was published only at 11:08Z-11:19Z. Console PR #1266's check-arch got a 404 at 10:48Z and needed a manual rerun. livespec-orchestrator-beads-fabro PR #3507 MERGED at 10:52:20Z, putting a sandbox tag on orchestrator master that ghcr did not serve until 11:19Z, so any factory dispatch from that repo in the window would have pulled a missing image. The fabro-sandbox-image workflow publishes six semver tags per release (base, python, python-agent, python-rust, python-rust-agent, python-rust-fuzz). Its recent release builds took about 13 to 41 minutes.

### Proposed Changes

In SPECIFICATION/contracts.md, section 'reusable-release-dispatch.yml', add after the 'Behavior:' paragraph:

Sandbox-image readiness (livespec-dev-tooling releases only): when source_repo is livespec-dev-tooling, the fan-out MUST NOT fire any sibling-released dispatch until ghcr.io serves a manifest for each of the release's semver-tagged livespec-fabro-sandbox layers (base-v<T>, python-v<T>, python-agent-v<T>, python-rust-v<T>, python-rust-agent-v<T>, python-rust-fuzz-v<T>). It MUST poll for them for at most 90 minutes. When any is still absent at that bound, the run MUST fail with an annotation naming each missing tag and MUST dispatch to no sibling, because a bump to a tag that does not exist is not a usable bump; the scheduled pin-freshness sweep remains the safety net once the image publishes. A release of any other source_repo MUST NOT wait.

Add to SPECIFICATION/scenarios.md:

## Scenario: a dev-tooling release fan-out dispatches only after its sandbox image tags are served

Given a livespec-dev-tooling release T whose livespec-fabro-sandbox semver tags are not yet served by ghcr.io

When the release fan-out runs

Then it MUST send no sibling-released dispatch while any of T's tags is absent

And it MUST dispatch to every unexcluded sibling once all of T's tags are served

## Scenario: a dev-tooling release fan-out whose sandbox image never appears fails naming the missing tags

Given a livespec-dev-tooling release T whose livespec-fabro-sandbox tags are not all served after the 90-minute bound

When the release fan-out reaches that bound

Then the run MUST fail with an annotation naming each missing tag

And it MUST send no sibling-released dispatch

The revise MUST co-edit tests/heading-coverage.json with an entry for each new scenario (test TODO owned by livespec-dev-tooling-epcoja) and regenerate the debt register.
