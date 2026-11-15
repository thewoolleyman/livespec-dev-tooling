---
topic: a-shared-surface-release-claim-cites-any-adopter-s-proving-incid
author: claude-opus-5-5
created_at: 2026-11-15T07:49:49Z
spec_commitments:
  impl_followups:
    - id_hint: fleet-audit-shared-surface-cited-claims
      description: |
        Implement the shared-surface cited-claim rule in the incident fleet audit: record per surface in committed audit configuration whether the surface is fully determined by its shared gate-readers, templates or driver-hooks build, held by a test against the surface's exact file set and the inputs its reader reads; let an implemented release-keyed claim on such a surface cite the authenticated incident that proved the same release in another adopter, named by adopter repository, incident item and release build; leave the row unclassified, with findings naming the reason, when the surface reads adopter configuration, the cited record does not authenticate or proved another release, or the serving version differs from the cited release; teach the committed-claim checks to accept a citing claim and refuse one missing the repository, item or release build; replace the scenario's heading-coverage TODO row with the integration test; and mirror the rule in docs/incident-fleet-audit.md.
---

## Proposal: a release-keyed claim on a shared surface may cite the incident that proved the same release in any adopter

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

In the incident fleet audit's readiness contract, an implemented, release-keyed claim on a row served by a shared gate-readers, templates or driver-hooks build MAY cite the incident that proved that same release in any adopter, but only where the shared build fully determines the surface and no adopter configuration is read. The citing row names the proving incident by repository, item and release build, and stays release-keyed.

### Motivation

Today every implemented claim must carry an incident item, normal factory proof and scope digest from an incident in its own consumer. For a surface whose behaviour is fully determined by a shared build, a second adopter's incident at the same release proves nothing the first did not, because the bytes that run and the inputs they read are identical. Requiring one incident per adopter for such rows delays readiness without adding evidence. A surface that reads adopter configuration (the focused-selection scope, the delegated-gate settings, copier answers) can behave differently per adopter at the same release, so it still needs the adopter's own incident or a justified not-applicable. legacy-coordinator-agent ruled this under R301 (2026-11-15) and reported it to the maintainer for objection. The rule needs a stated test for "fully determined", a naming rule for the citation, and the release-key that keeps a moved serving version from inheriting the proof, so that it cannot widen into accepting one adopter's incident for another's differently configured behaviour.

### Proposed Changes

In SPECIFICATION/contracts.md §"Expedited incident execution", insert the following paragraph immediately after the paragraph that begins "An adopter whose manifest profile is exactly `["instruction-only"]`" and before the paragraph that begins "The fleet audit MUST be runnable":

An `implemented` claim on a row whose capability is served by a shared build, the gate-readers, templates or driver-hooks build, names the release of that build it is judged against, so it is release-keyed. Such a claim MAY carry, in place of an incident in its own consumer, the incident item, normal factory proof and cumulative scope digest of the incident that proved that same release in any adopter, but ONLY when the row's surface is fully determined by the shared build. A surface is fully determined by the shared build at a release exactly when its code path and every input on that path lie entirely within that release of the shared build, and no file or setting of the adopter's repository is read on that path. A surface that reads adopter configuration, such as the focused-selection scope, the delegated-gate settings, copier answers, the adopter's `.livespec.jsonc` or its `[tool.livespec_dev_tooling]` table, is not fully determined. Whether a surface is fully determined MUST be recorded once per surface in the audit's committed configuration and held by a test against that surface's exact file set and the inputs its reader reads. It MUST NOT be asserted by the claim. A row whose surface is not fully determined still needs that adopter's own incident evidence or a `not-applicable` claim with its recorded reason. A claim on such a row that cites another adopter's incident MUST leave the row `unclassified`, and the findings MUST name the consumer, the surface and the adopter configuration the surface reads. A citing claim MUST name the proving incident by the adopter repository it ran in, its incident item and the release build it proved, and that build MUST equal the release the claim names. The proving incident's record MUST authenticate as it would for a claim of its own adopter; a citation of a record that does not authenticate, or that proved another release, MUST leave the row `unclassified`. A citing claim stays release-keyed. Its row classifies only while the consumer's serving version of that capability is the claimed release, or, for a row read from the consumer's own source, while every file of the row's surface is byte-identical to that release's. Any other serving version MUST leave the row `unclassified`, with the findings naming the release the claim cited and the serving version read. This qualifies the requirement, in the paragraph beginning "An adopter whose manifest profile", that the claim checks refuse an `implemented` claim lacking its incident item, normal factory proof or scope digest: a citing claim carries the proving incident's. Those checks MUST NOT refuse a citing claim that this paragraph lets the audit classify, and MUST refuse a citing claim that omits the proving incident's repository, item or release build.

In SPECIFICATION/scenarios.md, insert the following scenario immediately after "## Scenario: a consumer ruled deliberately-normal classifies from claims citing the ruling, with no installation serving it" and before "## Scenario: the incident fleet audit command refuses enablement for a consumer without verified serving evidence":

## Scenario: a shared-surface claim cites another adopter's proving incident only where the shared build fully determines the surface

Given an incident in one adopter whose authenticated record proves gate-readers release vX.Y.Z, with its incident item, normal factory proof and cumulative scope digest
And a second consumer whose gate readers serve vX.Y.Z, with an `implemented` claim on a gate-reader surface that the audit's committed configuration records as fully determined by the shared build, citing that incident by its adopter repository, incident item and release build vX.Y.Z
And an `implemented` claim of the same consumer on the `Focused test selection` surface, which reads that consumer's focused-selection scope, citing the same incident
When the fleet audit runs
Then the first row MUST read implemented
And the second row MUST read unclassified, and the findings MUST name the consumer, the surface and the adopter configuration it reads
And when the consumer's gate readers serve a later release, or the cited record proved another release, the first row MUST read unclassified, and the findings MUST name the cited release and the serving version read

Heading-coverage consequence: the revise adds one `## Scenario:` heading to scenarios.md and changes no other `## ` heading. It MUST co-edit tests/heading-coverage.json in the same commit with a row for that heading, whose `"test": "TODO"` reason names the integration tier as the tier of the owed test, carries a `work_item` key naming the open implementation item that owes the test (the impl follow-up `fleet-audit-shared-surface-cited-claims` declared with this proposal), and is registered by `just generate-heading-coverage-debt-register`. docs/incident-fleet-audit.md §"The ready list and enablement" and §"Release-keyed rows: a consumer that serves from its own source" mirror this rule and are updated by that implementation item, not by the revise.
