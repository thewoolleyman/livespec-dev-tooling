---
topic: the-scratch-incident-observer-shares
author: claude-opus-5-5
created_at: 2026-11-13T02:26:59Z
---

## Proposal: A scratch incident observer installation has its own Python environment and release instead of sharing production's

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

A scratch incident observer installation gets its own Python environment and installed release, named by its own role variable that defaults to production's release, instead of sharing production's. Production installations still share the installed release among themselves. Every existing scratch guarantee is kept (production's bytes unchanged, no production restart, a host-only scratch listener, the committed teardown), and two are added: a scratch apply or teardown never writes, upgrades or removes a production environment or release, and the preflight refuses any scratch path, the environment included, that is, contains or sits inside a production-owned path. One scenario covers a scratch installation running a release production does not serve yet.

### Motivation

Measured on 2026-11-13 (plan expedited-incident-response-flag, epic livespec-dev-tooling-bqnzcm). The 52die6 fix (livespec-dev-tooling#4341, merged as 092df309) ships in release v1.202.0, while the committed observer pin (`ansible/roles/incident_observer/defaults/main.yml:18`) is `incident_observer_release: v1.195.0`. Its host-captured proof must run on a scratch installation. That proved impossible before production rolls:

- the scratch installation runs from `/opt/livespec-incident/venv`, the same environment as every production installation; its playbook writes no environment or release of its own, and refuses unless production already serves the pinned release (`ansible/roles/incident_observer/README.md`, "It also refuses when the shared venv does not already serve `incident_observer_release` (converge production first)");
- the ratified text says the same: production installations share the installed release "as a scratch installation shares production's".

So the production roll (livespec-dev-tooling#4426, v1.195.0 to v1.202.0) has to be applied before any scratch proof can run on v1.202.0. legacy-coordinator-agent ruled that the fleet audit's "Emergency revert and merge authority" claim must be re-proved on the new release rather than re-pointed, which leaves that claim reading not-implemented for a bounded gap after the production apply. A scratch installation with its own environment and release lets every later roll be proved on scratch BEFORE production changes, which is what a scratch installation is for. Work item livespec-dev-tooling-whzwtw implements it; the launch screen holds that item at spec-change tier until this topic ratifies. The coordinator ruled the content (2026-11-13 ~02:3xZ): add the environment and release to what the scratch installation owns, keep production sharing among itself, keep every existing guarantee, forbid any scratch write to production's environment, and add the environment to the preflight's path check.

### Proposed Changes

In `SPECIFICATION/contracts.md`, section "Expedited incident execution", make the four edits below. No heading is added, removed or renamed in that file.

**Edit 1.** In the paragraph that begins "A drill or proof installation whose configuration names a scratch target branch MUST run side by side with the production installation", replace the sentence

> Its state directory, reference clone, listener port, observer service unit and reference-fetch units MUST each be its own, distinct from production's.

with

> Its state directory, reference clone, listener port, observer service unit and reference-fetch units MUST each be its own, distinct from production's. Its Python environment and the release installed in it MUST also be its own, at a path distinct from every production installation's environment; the release it installs MUST be named by its own role variable, which defaults to production's committed release pin, the role variable `incident_observer_release` in `ansible/roles/incident_observer/defaults/main.yml`, so a scratch installation MAY run a release that no production installation serves yet.

**Edit 2.** In the same paragraph, after the sentence that ends "and its running observer MUST NOT be restarted, and a role run that declares no scratch installation MUST render production byte-identical to the role's output without the scratch capability.", insert

> Installing, converging or tearing down a scratch installation MUST NOT write, upgrade or remove any production installation's Python environment or the release installed in it, and its apply MUST NOT require that production already serves the scratch installation's release. Before a scratch apply or teardown writes, stops or removes anything, the role MUST compare each scratch path (the scratch installation's root, state directory, reference clone, configuration, manifest, unit files and Python environment) against the production set, which is every path any production installation owns, including `/opt/livespec-incident` and its Python environment, each after `realpath` normalization. When any scratch path is, contains or sits inside a path in the production set, the role MUST refuse, naming the conflicting scratch path and production path and stating that nothing was written, stopped or removed. Production's home and configuration directory remain parents a scratch path MAY sit inside, never be or contain.

**Edit 3.** In the same paragraph, replace the teardown sentence's list "stops and disables the scratch observer and its reference-fetch units and removes their unit files, the scratch configuration and the scratch manifest" with "stops and disables the scratch observer and its reference-fetch units and removes their unit files, the scratch configuration, the scratch manifest, and the scratch Python environment with its release". The rest of that sentence, which lets the teardown retain the scratch state directory as evidence, is unchanged.

**Edit 4.** In the paragraph that begins "This repository MUST commit one inventory of production observer installations", replace the sentence

> Production installations MAY share the controller account, the installed release, the canonical reader clone, the webhook, control and query secrets and the recovery App credential, read-only, as a scratch installation shares production's.

with

> Production installations MAY share the controller account, the installed release, the canonical reader clone, the webhook, control and query secrets and the recovery App credential, read-only. A scratch installation MAY share the same values read-only except the installed release and its Python environment, which are its own.

In `SPECIFICATION/scenarios.md`, insert the following scenario after the scenario "the observer role renders one production installation per declared repository beside livespec-dev-tooling's", and before the scenario "a recorded scratch-branch drill ends in drill-closed and a master incident is refused". Alignment: the pending proposal `test-incident-observer-role-py` inserts a scenario in the same region; when that proposal has ratified first, place this scenario after the scenario it inserts, and in every case before the drill-closed scenario:

```gherkin
## Scenario: a scratch incident observer installs a release production does not serve yet

Given a production incident observer installation serving release vA, whose Python environment, release, configuration, manifest and units are read back and whose observer is running
When the committed observer role installs a scratch installation whose release variable names release vB
Then the scratch installation MUST have its own Python environment, at a path distinct from production's, serving release vB
And the apply MUST NOT require production to serve vB first
And production's Python environment MUST still serve vA, and production's configuration, manifest and units MUST keep their bytes, and its running observer MUST NOT restart
And when the scratch Python environment's path is set to production's Python environment under /opt/livespec-incident, the role MUST refuse before its first write, naming both paths and stating that nothing was written, stopped or removed
And the committed teardown MUST remove the scratch installation's Python environment and units while production's Python environment and release keep their bytes.
```

**Co-edit owed by the revise.** The revise that ratifies this proposal adds the new scenario's `## ` heading to `tests/heading-coverage.json` as a `"test": "TODO"` row whose `reason` names the integration tier the owed test runs at and whose `"work_item"` is `livespec-dev-tooling-whzwtw`, and regenerates `tests/heading-coverage-debt.json` with `just generate-heading-coverage-debt-register`.
