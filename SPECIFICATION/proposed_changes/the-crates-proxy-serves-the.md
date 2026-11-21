---
topic: the-crates-proxy-serves-the
author: claude-opus-5-5
created_at: 2026-11-08T10:41:16Z
---

## Proposal: The crates proxy serves the pool's pinned GitHub release assets from a committed manifest

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a host-served release-asset tier to the runner pool's build cache tiers: the crates proxy serves every GitHub release asset a committed url+sha256 manifest names, fetched through the releases API asset route, cached with stale serving, manifest-gated, pre-warmed and checked by the populator, and reachable from jobs through CI_RELEASE_ASSET_PROXY, so CI no longer depends on a live release download.

### Motivation

On 2026-11-08 from about 09:40Z to 10:39Z GitHub's releases/download route answered HTTP 504, on the pool and on GitHub-hosted runners alike, while the releases API asset route kept serving the same bytes. livespec-orchestrator-beads-fabro's install-ci-fabro step failed, its master and pull-request CI went red, and the expedited incident track's first arm was held. The orchestrator-side fallback is bd-ib-ukevod; this is the durable pool-side cache, work item livespec-dev-tooling-hnynfm, whose spec-change tier names this section as the generalization target. The section already prefers a host-served realization over a seeded tree wherever the consumer can read one, and curl can.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, section "## Runner-pool build cache tiers", add this paragraph after the "**Tiers.**" paragraph:

**Release assets.** The pool MUST serve, HOST-SERVED from the crates proxy, every GitHub release asset named in one committed manifest (`ci-runner/k3s/phase2/crates-proxy/release-assets.json`), each entry naming the asset's owner, repository, tag, asset name, release asset id and sha256. A job reaches the proxy at the base URL its container environment carries as `CI_RELEASE_ASSET_PROXY`. The proxy MUST fetch a manifest asset through the GitHub releases API asset route, MUST keep serving a cached asset while that upstream fails, MUST answer a release-asset path the manifest does not name with 404 and no upstream request, and MUST carry no credential. Its served set MUST be rendered from the manifest by the proxy's converge, so that adding an entry needs no hand edit of the proxy's configuration. The populator MUST pre-warm every manifest asset through the proxy and MUST name, in its run's failed list, an asset whose fetch fails or whose served bytes do not match the manifest sha256. A consumer MUST verify the pinned sha256 itself; the proxy is a cache, never a trust root. A proxy fault MUST degrade a consumer to its own live download, per "**Fail-soft and kill switch.**" below, and the fleet-wide kill switch and the cold canary MUST each leave a job without `CI_RELEASE_ASSET_PROXY`, so that job downloads the asset itself. As a cache tier it falls under §"Runner-pool cache telemetry": the host MUST emit the proxy's release-asset hits, misses and upstream failures, and the populator's per-asset pre-warm outcome, on the existing liveness path.

In `SPECIFICATION/scenarios.md`, at the end of the file, add:

## Scenario: a routed job reads a pinned release asset from the pool while the release download route fails

Given the committed release-asset manifest names a GitHub release asset with its asset id and sha256

And the populator has pre-warmed that asset through the crates proxy

When a routed job requests that asset at `$CI_RELEASE_ASSET_PROXY/github-release-assets/<owner>/<repo>/<asset id>` while the release download route answers HTTP 504

Then the proxy MUST return bytes whose sha256 is the manifest's

And a repeated request for that asset MUST be answered from the proxy's cache with no upstream request

And a request for a release-asset path the manifest does not name MUST return 404 with no upstream request

