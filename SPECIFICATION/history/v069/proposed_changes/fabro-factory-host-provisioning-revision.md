---
proposal: fabro-factory-host-provisioning.md
decision: modify
revised_at: 2026-10-10T23:46:04Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

No H2 of this repository's SPECIFICATION/ tree governs ansible/fabro-hosts.yml or its roles, so the factory's Definition-of-Done gate cannot accept a governing reference for livespec-dev-tooling-finosf or livespec-dev-tooling-ig5iwg. The proposal codifies the play as it is applied today (one fabro_server instance per host_vars mapping, uniqueness preflight, drift read before apply from vps) and adds the two obligations those items deliver: optional per-instance binary and home axes that leave existing units unchanged, and a sandbox-container envelope that never restarts dockerd outside a drained window. Placement in non-functional-requirements.md follows the precedent of the runner-pool node rebuild recipe. Coverage rows are spec-first TODO debt owned by the two delivering items.

## Modifications

Four changes from the independent ratification review, all narrowing the text to what the tree does today. (1) Per-host values are documented in the owning role's HOST_VARS.md, from which host_vars is generated; there is no inventory-level HOST_VARS.md. (2) The play clause covers only the Fabro factory services this repository provisions (Fabro server instances and sandbox-bounding controls), not every service on the host, since vps also runs dev-host.yml and docker and tailscaled are installed by no role; the control node is named as vps. (3) HOST_VARS.md documents every per-host variable a role reads, with its default where it has one; shared defaults stay in defaults/main.yml. (4) The first scenario requires the uniqueness preflight to refuse a repeated value, without requiring it to name the value, matching the current refusal and finosf's Definition of Done.

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
reviewed_at: 2026-10-10T23:44:50Z
verdict: NO BLOCKERS
proposal_stem: fabro-factory-host-provisioning
content_digest: f760bf58b554d24dd0219de667a8bf8c57c225f60b6fff55462e16287cd3cf51
