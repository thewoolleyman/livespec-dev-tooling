---
topic: the-incident-fleet-audit-cannot
author: claude:expedited-incident-response-flag
created_at: 2026-11-09T22:45:54Z
---

## Proposal: A runnable incident fleet audit command gates incident enablement on its ready list

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Amend contracts.md §"Expedited incident execution" so the fleet audit it already requires is a runnable, operator-invoked command over livespec core's committed fleet manifest. The command prints one row per incident surface and consumer with a disposition of implemented, deliberately-normal or not-applicable, exits non-zero naming the surface and consumer of every unclassified row, and handles an unauthenticated manifest by reporting it, listing zero ready repositories and exiting non-zero. Its ready list leaves out every consumer lacking verified serving-version evidence for gate readers, templates, driver hooks, recovery authorization or the independent controller, and names that consumer in its findings. Incident use for a repository is enabled only through one enablement step, which reads that ready list and refuses a missing repository by name, naming the missing evidence. Add one scenario stating the command and the enablement refusal.

### Motivation

Work item livespec-dev-tooling-3wcldx (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm) reopens in substance livespec-dev-tooling-wlrlt2, which the accept valve closed on 2026-11-04 with 0 assertions graded. On master, livespec_dev_tooling/incident_fleet_audit.py defines audit_incident_fleet, but nothing imports it: there is no CLI, no recipe, and no workflow or timer that calls it; its verify_manifest and verify_evidence callables have no production implementation; and nothing reads ready_repositories, so no enablement step consults the audit. The item's 2026-11-07 filing verdict was spec-change tier ('partial', generalization target ## Expedited incident execution, linked proposal topic the-incident-fleet-audit-cannot). Its rationale: the ratified text requires a fleet audit that expands the committed manifest and gives every surface and consumer an implemented, deliberately-normal or not-applicable disposition, and requires serving-version evidence for gate readers, templates, driver hooks, recovery authorization and the controller before incident use is enabled; it does NOT state a command with per-row printed output, non-zero exits for unclassified rows or an unauthenticated manifest, a ready-repository list, or an enablement step that reads that list and refuses a missing repository. legacy-coordinator-agent ruled on 2026-11-09 (~22:45Z) that plan assertion 13 ('the installed fleet tooling preserves incident context...') is read fleet-wide, so 3wcldx stays a carrier in this plan and must land, and directed this propose-change into the revise queue. This proposal adds only what the ratified text lacks; the 37-row inventory, the three dispositions, the serving-version requirement, and the 'ship, release, adopt, prove, only then enable' ordering are unchanged. The audit and enablement step are a wire contract an operator and other repositories call by name, so the clause goes in contracts.md beside the audit sentence it elaborates. The feature rollout itself remains normal and unexpedited.

### Proposed Changes

1. In SPECIFICATION/contracts.md §"Expedited incident execution", add the following paragraph at the end of the section, after the paragraph that begins "The fleet audit MUST expand core's committed manifest". That paragraph is unchanged.

> The fleet audit MUST be runnable: this repository's justfile MUST ship an operator-invoked recipe, `just incident-fleet-audit`, that reads livespec core's committed `.livespec-fleet-manifest.jsonc` as §"Sibling discovery" reads it and expands every `fleet` member and `adopters` entry into a consumer. It is a local-vantage surface, NOT a CI check, and it carries no run lever. The command MUST print one row per incident surface and consumer, naming the consumer repository, the surface, and its disposition: `implemented`, `deliberately-normal` or `not-applicable` when authenticated evidence classifies the row, and `unclassified` otherwise. A row whose evidence is missing, contradictory, stale, bound to another manifest identity, or not authenticated by the command's evidence readers MUST be `unclassified`. Those readers MUST read serving versions from the installed consumers and the running independent controller; they MUST NOT accept a release name, a candidate label, a caller-supplied receipt or a source test result as serving evidence, and an authoritative read that is unavailable MUST count as unverified. A row carrying serving-version evidence MUST print the serving version that was read. The command MUST exit non-zero when any row is unclassified, and MUST name the surface and consumer of every unclassified row in its findings. When the command cannot authenticate the manifest's membership and committed identity against livespec core's master, including when that read is unavailable, it MUST report that finding, MUST list zero ready repositories and MUST exit non-zero. The command MUST print a ready list of the repositories whose incident use may be enabled. It MUST NOT list a consumer that lacks verified serving-version evidence for any of its gate readers, templates, driver hooks, recovery authorization or the independent controller, and its findings MUST name each such consumer with the evidence it lacks. The command MUST NOT enable, mutate or credential any consumer. Incident use for a repository MUST be enabled only through one enablement step. That step MUST read the ready list of a fleet audit run against the current committed manifest identity; it MUST NOT accept a ready list supplied by its caller, read from a cache, or computed against another manifest identity. When the repository is missing from that ready list, the step MUST refuse, exit non-zero and enable nothing, naming the repository and the missing evidence the audit's findings record for it.

2. In SPECIFICATION/scenarios.md, add after "## Scenario: incident enablement follows complete installed-fleet capability proof" (which is unchanged):

## Scenario: the incident fleet audit command refuses enablement for a consumer without verified serving evidence

```gherkin
Given livespec core's committed fleet manifest, authenticated against core's master
And one manifest consumer whose running independent controller's serving version cannot be read
When the operator runs `just incident-fleet-audit`
Then it MUST print one row per incident surface and manifest consumer, each naming the consumer, the surface and a disposition of implemented, deliberately-normal, not-applicable or unclassified
And that consumer's controller row MUST be unclassified
And the command MUST exit non-zero, naming the surface and consumer of every unclassified row
And its ready list MUST NOT include that consumer, and its findings MUST name that consumer and the missing controller serving-version evidence
And the incident enablement step run for that consumer MUST refuse, exit non-zero and enable nothing, naming the consumer and the missing evidence
And the same command run against a manifest whose committed identity cannot be authenticated MUST report that finding, list zero ready repositories and exit non-zero.
```

3. In tests/heading-coverage.json, add an entry for the new scenario heading (spec_file scenarios.md) with test "TODO", work_item livespec-dev-tooling-3wcldx, and a reason naming the tier: "A real test at the integration tier or above is owed for this heading: the incident-fleet-audit recipe must be run as a child process against a fixture manifest and fake serving-version readers, and the enablement step must refuse a repository missing from its ready list; livespec-dev-tooling-3wcldx owns it." Regenerate tests/heading-coverage-debt.json with `just generate-heading-coverage-debt-register`. No existing heading is removed or renamed.
