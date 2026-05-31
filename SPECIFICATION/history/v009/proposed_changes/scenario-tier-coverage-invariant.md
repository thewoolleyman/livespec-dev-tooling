---
topic: scenario-tier-coverage-invariant
author: livespec-orchestrate-dispatch
created_at: 2026-05-31T21:04:13Z
---

## Proposal: Scenario-tier coverage invariant

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Restate the scenario-tier coverage invariant in this library's OWN non-functional-requirements.md so dev-tooling does not inherit the rule by reference from any sibling repo. Add a new `### Scenario-tier coverage` sub-section under the existing §"Testing approach" (the "Pyramid layers" area), binding every `## Scenario:` heading in `SPECIFICATION/scenarios.md` to a granular `tests/heading-coverage.json` entry whose mapped test sits at the integration tier or above. The library enforces this on itself via its own `heading_coverage` check (self-application).

### Motivation

Epic li-scetier Wave 5. The scenario-tier coverage invariant is enforced by this library's `heading_coverage` check (Wave 1 wired the `scenario_tiers` allowlist and the integration-tier enforcement; PR #77 registered the seven scenario TODO entries). The invariant must be stated independently in this library's own SPECIFICATION — a sibling repo's SPECIFICATION cannot be inherited by reference — so the rule the check enforces has a normative home here. Added as a `###` sub-section (not a new `##` H2) so no `tests/heading-coverage.json` co-edit is required.

### Proposed Changes

Under §"Testing approach", immediately after the existing `**Pyramid layers.**`, `**Coverage gate.**`, and `**Import-Linter.**` bullets, add a new `### Scenario-tier coverage` sub-section:

```markdown
### Scenario-tier coverage

Every `## Scenario:` heading in `SPECIFICATION/scenarios.md` MUST have its own entry in `tests/heading-coverage.json`. Scenarios are tracked granularly — one entry per scenario — and several scenarios MAY map to the same test (many-to-one is expected). Each mapped test MUST sit at the **integration tier or above**: a consumer-style check-runner test that imports a check from `livespec_dev_tooling.checks.*` and runs it against a fixture mini-project under `tmp_path` with deliberately-injected violations, asserting that the expected diagnostic fires — never a unit-tier helper test, since a scenario describes consumer-observable behavior. A scenario entry is compliant when EITHER (a) its test node-id path component begins with an integration-tier prefix declared in this repo's `pyproject.toml` `[tool.livespec_dev_tooling].scenario_tiers` allowlist, OR (b) the resolved test carries an explicit `pytest.mark.integration` (or stronger) marker. A `TODO` entry is permitted during transition provided its `reason` explicitly acknowledges this tier requirement. The library enforces this invariant on itself via its own `heading_coverage` check (self-application per `constraints.md` §"Self-application").
```

This preserves every normative clause of the cross-family scenario-tier rule while stating it in this library's own voice. No `## ` H2 is added, so `tests/heading-coverage.json` requires no co-edit; the seven scenario TODO entries registered by PR #77 already acknowledge the integration-tier requirement in their `reason` fields and are left in place (their real integration-tier tests land under epic li-scetdt / Wave 6).
