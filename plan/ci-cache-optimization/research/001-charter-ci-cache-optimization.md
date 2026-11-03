## The maintainer's statement of what done means

Nonroot job fixes - seeding UV and any other cache optimizations should be a dedicated plan, and prioritized.

## Definition of Done assertions derived from that statement

- The orchestrator nonroot CI leg's preparation step takes under 15 s median (from 120-130 s), with a seeded uid-1000 uv cache and no full-workspace chown -R.
- Over any 6-hour window after the node-local action archive cache ships, no fleet ARC job fails at Set up job on a codeload.github.com action download.
- This plan's research ranks every CI cache lever (uv, pip, sccache, cargo, action archives, container image pulls, warm caches) by measured k3s job-hours saved per week, and names the queries that reproduce each figure.
- Every ranked lever with a measured saving is carried by a child work item of this plan or by a relay to the plan that owns it, and the carriers land in rank order.
- Over at least 20 runs after each landed lever ships, the median duration of the jobs it targets is below the baseline recorded in this plan's research.

# 001: charter — ci-cache-optimization

Opened 2026-11-03 by legacy-coordinator-agent (epic livespec-dev-tooling-6tgd2z) on the maintainer's direction. Priority 4
in the priorities record of 2026-11-03T15:00:57Z.

## The maintainer's statement (verbatim, 2026-11-03 ~14:5xZ)

> Nonroot job fixes - seeding UV and any other cache optimizations should be a dedicated plan, and prioritized.

## Definition of Done (session-derived; recorded as such in the first handoff)

The assertions on the epic were derived by the seat, unattended, from the statement above and the measured figures in
`plan/ci-runtime-and-cost/research/002-ci-cost-ranking-2026-11-03.md`. They were not confirmed with the maintainer.

## Starting evidence (from ci-runtime-and-cost research 002)

- Orchestrator nonroot legs cost ~45 k3s job-hours/week more than root for the same work. Cause: the 'Prepare
  non-root leg' step (median 120-130 s on 40 runs) doing `chmod -R`/`chown -R` over image trees and the workspace, plus a
  private cold `UV_CACHE_DIR`. Carrier: bd-ib-uuatg4 (orchestrator tenant).
- `check-coverage` consumer jobs: ~119 h/week across both uids, almost all container setup to read an artifact.
- dev-tooling `check-per-file-coverage`: 84 h/week of k3s.
- codeload 429s at Set up job on ARC runners (10 of 4,359 job attempts in 6 h, 2026-11-03). Carrier:
  livespec-dev-tooling-a35sa4 (node-local action archive cache).

## Ownership boundaries

- ci-runtime-and-cost owns the uid move (bd-ib-xufdwx), the master-push Kueue slice (livespec-dev-tooling-lzkzwb) and
  release coalescing (livespec-dev-tooling-aplxhg). This plan does not touch those.
- kubernetes-sandbox-backend owns runner and node capacity. Cache tiers that mount on the node are coordinated with it.
- Workflow edits are pre-approved by the maintainer; each is described to legacy-coordinator-agent, which sets
  `approval:workflow-edit`.

## Method

Rank every CI cache lever — uv, pip, sccache, cargo, action archives, container image pulls, warm caches — by measured
k3s job-hours saved per week, then file, dispatch and land in that order. The ranking is research note 002.
