---
proposal: consent-gated-pool-node-disruption.md
decision: modify
revised_at: 2026-10-16T18:20:14Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5:factory-worker-nodes-gitops
---

## Decision and Rationale

Accepted with modifications under the maintainer's delegated authority recorded on livespec-dev-tooling-dfixhe (2026-10-15 ~16:40Z, reaffirmed 2026-10-16 06:29Z), executed for freeze-driver ruling R71. No section stated how a pool node may be deliberately disrupted. Work-item livespec-dev-tooling-raynnh (a consent-gated node-loss drill for livespec-orchestrator-beads-fabro bd-ib-ad6dby assertion 3) needs a governing clause. The existing ansible/reboot-ci-server.yml already conforms to the general rule. An independent read-only Fable review first found a blocker: no carve-out for the bare-metal rebuild recipe. It is fixed, and the re-review returned NO BLOCKERS on these exact bytes.

## Modifications

(1) The Scope paragraph adds: 'Rebuilding a node from empty storage is governed by §"Runner-pool node rebuild recipe", not by this section.' This resolves the reviewer's blocker, because phase0's node-local, device-consented stage would otherwise breach the general rule. (2) 'every host that runs a Fabro server or the factory sandbox plugin' becomes 'every Fabro factory host', the defined term from §"Fabro factory host provisioning". The scenario's Given follows. (3) 'read those hosts from inventory groups' becomes 'identify those hosts from inventory', because the control plane is a host var. (4) 'any other pod' becomes 'any pod'. Heading-coverage TODO rows are owned by raynnh and name the integration tier; the debt register was regenerated mechanically.

## Resulting Changes

- non-functional-requirements.md
- scenarios.md
- ../tests/heading-coverage.json
- ../tests/heading-coverage-debt.json

## Ratification Review

ratification_review: auto-spawn
reviewer_model: fable
reviewer_identity: fable
separate_reviewer: True
read_only: True
reviewed_at: 2026-10-16T18:19:31Z
verdict: NO BLOCKERS
proposal_stem: consent-gated-pool-node-disruption
content_digest: 26368a565f5666985f9f15ec7b48d4cab2f151bd93a89b270a3b4762ad8420ba
