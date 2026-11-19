---
topic: workflow-scope-authorization-for-expedited-repair
author: claude-sonnet-5-5
created_at: 2026-11-19T19:11:43Z
---

## Proposal: workflow-scope-authorization-for-expedited-repair

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In section "Expedited incident execution", the sentence "A workflow incident MUST have scoped host authorization" is replaced by a stated authorization model: an attempt's canonical authority record MAY carry an optional list of exact workflow paths, written only by a maintainer-attested receipt, and the incident commit hook admits a changed path under .github/workflows/ only when that path is listed exactly and the attestation is current for the attempt generation. One scenario states the behavior.

### Motivation

The incident commit hook (incident_hook_scope.py validate_scope) refuses every changed path under .github/workflows/ in expedited-repair mode, because no authority record can carry such a scope. Measured 2026-11-17 on incident livespec-dev-tooling-ypvfll (master red at 00cc04ba1): the expedited-repair commit was refused with "incident-hook-refused: workflow publication requires separately scoped canonical authorization". The contract only says a workflow incident MUST have scoped host authorization, and does not say who may write that scope or what the hook checks, so the hook cannot enforce it. The coordinator ruled option A of research note plan/expedited-incident-response-flag/research/008-workflow-repair-authorization-options.md on 2026-11-19, as the already-ruled workflow-edit tiering: an edit that removes or reduces gates stays the maintainer's. A mechanical gate-reduction detector (option B) MAY later be added only as an extra refusal, never as a grant. Work item livespec-dev-tooling-jtuxzn carries the hook change and stays un-ticketed until a revise names a heading that states the field.

### Proposed Changes

(1) In SPECIFICATION/contracts.md section "Expedited incident execution", replace the sentence "A workflow incident MUST have scoped host authorization; the flag grants no credential and factory workers gain no workflow write scope." with: "A workflow incident MUST have scoped host authorization; the flag grants no credential and factory workers gain no workflow write scope. An attempt's canonical authority record MAY carry a list of exact workflow paths, each a path under `.github/workflows/`. Only a maintainer-attested record (a `human_attested` receipt) MAY write that list. The incident commit hook MUST admit a changed path under `.github/workflows/` only when that exact path is in the list and the attestation is current for the attempt generation the commit binds. A changed workflow path that is not listed, or whose attestation is not current, MUST be refused with a refusal naming the missing workflow-scoped authorization and the path. No flag, environment variable, label, commit subject or agent-written record counts as that attestation. A later check MAY add a refusal for a workflow diff that reduces a gate, but MUST NOT grant a path the attested list does not carry." (2) In SPECIFICATION/scenarios.md add a scenario "## Scenario: an expedited repair publishes a workflow path only under a maintainer-attested scope" with Given an authorized incident item whose attempt generation carries a maintainer-attested workflow path list naming exactly one workflow file; When an expedited-repair commit changes that file, Then the incident commit hook admits it; And when the same commit also changes a second workflow file the list does not name, the hook refuses it naming the missing workflow-scoped authorization and that path; And when the attestation is not current for the attempt generation, the hook refuses the listed path too. (3) tests/heading-coverage.json gains an entry for the new scenario heading, with a spec-first TODO row owned by livespec-dev-tooling-jtuxzn, in the revise commit.
