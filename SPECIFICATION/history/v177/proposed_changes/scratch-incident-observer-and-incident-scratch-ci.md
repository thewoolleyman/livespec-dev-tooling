---
topic: scratch-incident-observer-and-incident-scratch-ci
author: claude:expedited-incident-response-flag
created_at: 2026-11-10T01:54:25Z
---

## Proposal: A scratch-branch incident drill installation runs beside production and binds a full master-equivalent CI run

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/constraints.md
- SPECIFICATION/scenarios.md

### Summary

Add two clauses so a drill or proof of incident recovery can run against a scratch branch on the real observer host and the real forge without touching production. In contracts.md §"Expedited incident execution", a scratch-target installation runs side by side with production through the committed observer role, with its own configuration, manifest naming that configuration, state, reference clone, port and units, publishes no public ingress, never alters production's rendered or running installation, is removed by a committed teardown, and is never counted as master recovery capability. In constraints.md §"CI matrix shape", ci.yml's push trigger also matches incident-scratch/**, a push there runs the same complete master job graph and policy as a master push, master-only side effects (release, master-health reconciliation, deploy, telemetry export) do not fire on it, and pushes to other non-master branches run nothing. One scenario states both together.

### Motivation

Plan expedited-incident-response-flag (epic livespec-dev-tooling-bqnzcm). Intake classed two P1 children spec-change tier with verdict-kind partial at spec v175: livespec-dev-tooling-32qdja (generalization target ## Expedited incident execution: the section states that a principal may target a scratch branch and must not count as master capability, but not a second side-by-side observer installation, production staying byte-identical, or a committed teardown) and livespec-dev-tooling-7w757z (generalization target ## CI matrix shape: nothing states that ci.yml's push trigger matches incident-scratch/**, or that such a push gets the master graph, routing and empty omitted output). Both enable the host proof of livespec-dev-tooling-thhgeg and the plan's second-rehearsal preconditions: thhgeg's Host-captured bullets need a recovery principal configured for a scratch branch on the real observer host vps while production stays on master, and the observer's MergedRunVerifier binds only a push-event run of ci.yml whose head_branch is the registration's branch. Today the incident_observer role converges exactly one installation with no teardown path, its manifest's principal argv names the production controller.json, and ci.yml pushes run only on master. v173 (livespec-dev-tooling#3922) admitted a non-master target branch only to prove or drill recovery; these clauses state how such an installation and its CI run coexist with production. The export-telemetry job in ci.yml currently runs on every push event, so the side-effect clause requires it not to run on a scratch push. One proposal covers both items because they are the two halves of the same scratch proof.

### Proposed Changes

1. In SPECIFICATION/contracts.md §"Expedited incident execution", insert the following as a new paragraph immediately after the rollback paragraph (the paragraph that ends "Ordinary non-incident reconciler policy remains unchanged."):

> A drill or proof installation whose configuration names a scratch target branch MUST run side by side with the production installation, never in its place, and MUST be installed, converged and removed through the same committed observer role that converges production, not by hand host writes. It MUST have its own installation configuration naming its scratch target branch, and its own released-installation manifest whose recovery-principal invocation names that scratch configuration rather than production's. Its state directory, reference clone, listener port, observer service unit and reference-fetch units MUST each be its own, distinct from production's. Public ingress the role publishes MUST remain production's alone, and a scratch listener MUST be reachable only from its host. Installing, running or tearing down a scratch installation MUST NOT alter production's rendered installation: production's configuration, manifest and units MUST keep their bytes and its running observer MUST NOT be restarted, and a role run that declares no scratch installation MUST render production byte-identical to the role's output without the scratch capability. The repository MUST commit a teardown that stops and disables the scratch observer and its reference-fetch units and removes their unit files, the scratch configuration and the scratch manifest; the teardown MAY retain the scratch state directory as evidence. A scratch installation MUST NOT be counted as recovery capability for `master`: its receipts MUST NOT satisfy the durable observer receipt an incident merge into `master` requires, and the fleet audit MUST NOT read it as the running independent controller.

The rollback paragraph, including the v173 configured-target-branch sentences, is unchanged.

2. In SPECIFICATION/constraints.md §"CI matrix shape", insert the following as a new paragraph immediately after the first paragraph (the per-event matrix shape and the incident repair-PR exception):

> This repository's `ci.yml` push trigger MUST match `master` and branches under `incident-scratch/**`, and no other branch, so that a drill or proof incident installation configured for a scratch branch (`contracts.md` §"Expedited incident execution") can bind a real push run of the gating workflow; its `pull_request` trigger is unchanged. A push to an `incident-scratch/**` branch MUST run the same complete gating job graph as a `master` push (the required aggregate and every job it needs), under the same job conditions, the same `runs-on` routing and the same policy: both incident flags absent, no member omitted or deferred, and every check executed. Master-only side effects MUST NOT fire on a scratch push: a scratch push MUST NOT trigger release, master-health reconciliation, deploy or image publication, or CI telemetry export, and a scratch push run MUST NOT be read as master-health evidence or as recovery capability for `master`. A push to any other non-`master` branch MUST start no `ci.yml` run.

The routing paragraphs that follow are unchanged; a scratch push is a `push` event and so reads `CI_RUNNER_LABELS_MASTER` and its priority term exactly as a `master` push does.

3. In SPECIFICATION/scenarios.md, add after "## Scenario: an incident recovery principal configured for a scratch branch recovers only that branch":

## Scenario: a scratch-branch incident drill runs beside production on the full master CI graph

```gherkin
Given a production incident observer installation targeting master, whose configuration, manifest and units are read back and whose observer is running
When the committed observer role installs a second installation whose configuration names an incident-scratch/** branch as its target branch
Then the scratch installation MUST have its own configuration, its own manifest whose recovery-principal invocation names that configuration, and its own state directory, reference clone, listener port and units
And production's configuration, manifest and units MUST keep their bytes, and its running observer MUST NOT restart
And a push to the scratch branch MUST start a ci.yml push run of the complete master job graph with both incident flags absent and every check executed
And that push run MUST NOT release, reconcile master health, deploy or export CI telemetry
And a push to any other non-master branch MUST start no ci.yml run
And the committed teardown MUST remove the scratch installation's units, configuration and manifest while production keeps its bytes and its running observer
And the scratch installation MUST NOT be counted as recovery capability for master.
```

4. In tests/heading-coverage.json, add an entry for the new scenario heading (spec_file scenarios.md) with test "TODO", work_item livespec-dev-tooling-32qdja, and a reason naming the tier: "A real test at the integration tier or above is owed for this heading: the incident_observer role's scratch instance must render beside an unchanged production installation and tear down cleanly, and a push to an incident-scratch/** branch must run ci.yml's complete master job graph with no master-only side effect; livespec-dev-tooling-32qdja owns it, with livespec-dev-tooling-7w757z owning the ci.yml trigger." Regenerate tests/heading-coverage-debt.json with `just generate-heading-coverage-debt-register`. The two edited H2 sections already carry heading-coverage entries and keep their headings, so no other row changes.
