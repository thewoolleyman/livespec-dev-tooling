---
proposal: ci-job-spans-runner-and-shared-exporter.md
decision: modify
revised_at: 2026-11-11T23:21:34Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:ci-runtime-and-cost
---

## Decision and Rationale

Ratified with one citation repair. Every ci.job.<name> span carries ci.runner_name from the GitHub jobs API, so a CI job joins to k8s.pod.name and then k8s.node.name, and CI job time can be read per node. The CI run-telemetry exporter becomes one livespec-dev-tooling module every member runs through its pin. Measured 2026-11-11 (plan ci-runtime-and-cost, epic livespec-dev-tooling-ib3oe3): no github-ci job span carries a runner or node, so the poweredge budget trial's revert leg fell back to a fleet-wide p95 stand-in; the nine members' export-ci-telemetry.sh copies have drifted into 8 distinct hashes. The heading-coverage TODO rows are owned by livespec-dev-tooling-wnwwsl and livespec-dev-tooling-5ua57h and name the integration tier or above. The independent review found the exporter is not a node-telemetry emitter under the section's Failure contract, because it reads GitHub job rows, not kubelet data.

## Modifications

One change from the proposal: the citation §"Pod attribution" becomes "the **Pod attribution** paragraph above", because Pod attribution is a bold paragraph label in this section, not a heading, and the post-step doctor (doctor-no-cross-spec-reference) refused the unresolvable citation. The independent re-review confirmed the phrase names that one paragraph unambiguously.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-11T23:20:54Z
verdict: NO BLOCKERS
proposal_stem: ci-job-spans-runner-and-shared-exporter
content_digest: 6e94438e949a43c3a3f93d2e6b844828d6ef6fcfa7ba7c2cd6986b8e8b79d397
