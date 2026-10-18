---
proposal: fabro-factory-registry.md
decision: accept
revised_at: 2026-10-18T17:02:08Z
author_human: Chad Woolley <thewoolleyman@gmail.com>
author_llm: claude-opus-5-5
---

## Decision and Rationale

Accepted under the delegated revise_decision_mode of this repository's .livespec.jsonc spec_governance, by a fork of session petri-factory-on-gmktec under the maintainer's binding ruling recorded on plan epic bd-ib-fyozyd (livespec-orchestrator-beads-fabro ledger) at 2026-10-17T21:55Z: a spec proposal that fixes a measured defect blocking plan work is session-ratifiable after an independent review. It is the provisioning half of plan Definition of Done item 4 and the source of the registry that livespec-orchestrator-beads-fabro contracts v161 section 'Factory addresses resolved from a host registry' reads. The configured ratification reviewer, Fable (claude-fable-5-1) in separately started read-only headless sessions, reviewed it in five rounds: round 1 BLOCKERS (the sandbox_hosts source group excluded the vps instances; it proposed the simpler name-keyed inventory mapping now adopted), round 2 BLOCKERS (owner work-item not yet filed), round 3 NO BLOCKERS on the proposal, round 4 BLOCKERS on the resulting bytes (the scenario coverage reason did not name the integration tier), and round 5 NO BLOCKERS on these exact resulting-file bytes with an independently reproduced digest and a passing debt ratchet and armed heading-coverage check in a throwaway clone. The Scenario and section coverage entries are TODOs owned by livespec-dev-tooling-txadim, with debt rows produced by just generate-heading-coverage-debt-register.

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
reviewed_at: 2026-10-18T16:27:19Z
verdict: NO BLOCKERS
proposal_stem: fabro-factory-registry
content_digest: 162d4a3326e07e99f96540aa4243473d2755285caba8a9232a5c3869a0e3b49c
