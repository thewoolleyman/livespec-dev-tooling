---
topic: cite-the-core-heading-for-the-master
author: claude-opus-5-5 (master-green-external-outage plan seat)
created_at: 2026-11-16T17:04:02Z
---

## Proposal: cite the core heading for the master-green gate

### Target specification files

- SPECIFICATION/contracts.md

### Summary

The opening sentence of '## Master-green gate and external red' cites livespec core by a bold paragraph label, which the doctor's no-cross-spec-reference check cannot resolve; cite the enclosing core heading instead and name the paragraph in prose.

### Motivation

The pre-step doctor (doctor-no-cross-spec-reference, core build fa8c81e29579) fails on master at contracts.md:1173 because the cited text is a bold paragraph label at livespec non-functional-requirements.md:1324 (ratified by livespec#3260, v250), not an ATX heading. An allowlist entry does not help: the doctor drops any allowlisted entry whose heading is not an ATX heading in the cited repo's local clone (_validated_external_references). The enclosing core heading is '### CI as a merge gate (branch protection)', which is already allowlisted in .livespec.jsonc. The failing doctor blocks every livespec-dev-tooling revise.

### Proposed Changes

In SPECIFICATION/contracts.md, section '## Master-green gate and external red', replace the opening sentence with: 'This section realizes, for the shared check `master_ci_green` and the shared `ci.yml` aggregate, the paragraph named "The master-green gate tolerates an external red, on evidence and for at most one day" of livespec core `non-functional-requirements.md` §"CI as a merge gate (branch protection)".' No heading is added, renamed or removed, so tests/heading-coverage.json is unchanged.
