---
proposal: arc-secret-reinjection-projects-the.md
decision: accept
revised_at: 2026-11-15T15:26:39Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5 (h5r75q seat)
---

## Decision and Rationale

Accepted as filed and as graded PASS by legacy-coordinator-agent on livespec-dev-tooling#4798; the substance is not reworded. The proposal carries the behaviour livespec-dev-tooling-h5r75q's Definition of Done names (step (b) of livespec-dev-tooling-xyi5vu, plan stale-base-merge-options, epic livespec-dev-tooling-xowhol): the CI node's ARC secret reinjection projects the livespec-ai-arc GitHub App credential, from the homelab shared-credentials launcher's environment, into its own Secret arc-github-app-installation-livespec-ai, running as a non-root user limited to that Secret, leaves arc-github-app-installation unchanged, and refuses with the missing variable named and no value printed. It lands as one paragraph under the existing non-functional-requirements.md section 'Runner-pool node rebuild recipe' (no new H2 there) and two scenarios in scenarios.md, which the authoring discipline requires for new behaviour. Doctor LLM phase on the pending proposal: one objective low finding, the term 'homelab shared-credentials launcher' (and its 'runtime manifest consumer') is not defined in SPECIFICATION; dismissed, because it names an external homelab component by its consumer id and environment contract, the way the spec names other external systems, and tenant-fleet-credentials owns that component's definition. One subjective low observation, that the paragraph does not say when the organization projection runs relative to the boot converge; deferred to xyi5vu step (c), which owns how organization scale sets reference the Secret. No contradiction with the surrounding paragraphs; the independent sonnet review reported NO BLOCKERS on these exact bytes.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md

## Ratification Review

ratification_review: auto-spawn
reviewer_model: sonnet
reviewer_identity: sonnet
separate_reviewer: True
read_only: True
reviewed_at: 2026-11-15T15:25:50Z
verdict: NO BLOCKERS
proposal_stem: arc-secret-reinjection-projects-the
content_digest: ab6ffc40e07eb4661a2e76488cfe4c1b7e449122bb220594b493501b4f94e6dd
