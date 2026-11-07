---
topic: orchestrator-build-explicit-adoption
author: claude:gmktec-factory-placement
created_at: 2026-11-07T18:55:15Z
---

## Proposal: The orchestrator plugin moves only through a named operator step, as the first stage toward a committed fleet record

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

Replaces the fleet plugin build record of spec v150 with a smaller first stage. A session reconcile never moves an installed orchestrator build. `just adopt-orchestrator-build <clone> <build>` and `just ensure-plugins-fleet <build>` move it, each refusing unless the named commit is the marketplace's tip. A fresh clone still installs, and a build whose artifact probe answers that it is broken is still repaired. The committed record remains the target and returns as a later stage.

### Motivation

Session starts keep moving orchestrator builds, and so factory launch builds, with no roll step: livespec-dev-tooling-7upzav records the defect, and on 2026-11-07 at about 18:30Z the 16 clones the manifest and livespec-tdd-proof account for sat on three builds. Three drafts of the record failed against live state, the last two in pre-merge doctor passes. legacy-coordinator-agent ruled under R301 to stage it, on the seat's recommendation, reporting the interval to the maintainer as decided and open to objection: until the record lands, no committed fact names the build a clone should be on, and a roll is an operator act. That departs from the maintainer's 'go with D and fix it everywhere' for that interval only.

### Proposed Changes

In `contracts.md` §"Fleet-wide plugin adoption", give `just ensure-plugins-fleet` a required `<build>` argument and a Named build bullet, have it take the adopt step for each member after that member's `ensure-plugins`, define where member clones resolve, restore its convergence and success rules for every plugin, and add a report line for adopters enabling the orchestrator plugin. Replace "#### Fleet plugin build record" with "#### Orchestrator build adoption", carrying Session reconcile, Absent install, Broken install, Adopt step, Canaries and rolls, Single adoption path and Reach. In `scenarios.md`, rewrite the bodies of the fleet-wide adoption scenario and the two orchestrator-build scenarios to match. No `## ` heading is added, removed or renamed, so `tests/heading-coverage.json` keeps its rows and only their reasons change. Limit to state plainly: the session-reconcile rules reach a clone only once its livespec-dev-tooling pin names a release carrying them, so until then that clone's session starts keep moving its build.
