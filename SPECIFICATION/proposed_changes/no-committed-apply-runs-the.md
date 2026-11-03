---
topic: no-committed-apply-runs-the
author: claude-opus-5-5:ci-runtime-and-cost
created_at: 2026-11-03T16:27:03Z
---

## Proposal: A merged runner-pool change reaches the live cluster through one committed control-node apply

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add to §"Runner-pool node rebuild recipe" a **Live converge** obligation: a merged change to the cluster stack this tree declares MUST be applicable to the live cluster by one committed control-node apply that runs the CI stack converge on the CI server, waits for it, fails loud with the unit's result and journal tail, and changes nothing when nothing changed. Add the scenario that exercises it.

### Motivation

Measured 2026-11-03: livespec-dev-tooling-lzkzwb's infra PR #3266 merged (435fe22a) and `just ansible-apply ansible/ci-pool.yml --tags ci_converge_unit` installed its new scale set and ClusterQueue on poweredge (changed=3), but the `ci_converge_unit` role deliberately enables `converge-ci-stack.service` without starting it, and the fleet host guard (GitOps deployment discipline) correctly refuses a by-hand `systemctl start`. So no committed path applies a merged runner-pool change to the live cluster short of a reboot. livespec-dev-tooling-un3zhi realizes the apply; its dispatch was refused at the spec-change tier because §"Runner-pool node rebuild recipe" does not state it.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md` §"Runner-pool node rebuild recipe", after the **Re-runnable, and destructive only on consent.** paragraph, add:

> **Live converge from the control node.** A merged change to the cluster stack this tree declares — the ARC controller and scale sets, the hook pod template, Kueue core and every queue — MUST be applicable to the live cluster by ONE committed apply run from the control node, which runs the CI stack converge on the CI server and waits for it to finish. That apply MUST fail when the converge fails, naming the converge unit's result and the tail of its journal, and MUST report no change when the converge's inputs on the host are unchanged since its last successful run. A by-hand start of the converge on the host MUST NOT be the path, and a reboot MUST NOT be required to apply a merged change.

In `SPECIFICATION/scenarios.md`, add:

```markdown
## Scenario: a merged runner-pool change reaches the live cluster through one committed apply

Given a merged change that adds a runner scale set and its ClusterQueue under ci-runner/k3s/phase2/
And the converge tree on the CI server has been refreshed to that change
When the operator runs the committed live-converge apply from the control node
Then the CI stack converge runs on the CI server and the apply waits for it
And the new scale set's listener and ClusterQueue exist on the live cluster
And a second run of the same apply reports no change
```

The revise commit adds a `tests/heading-coverage.json` TODO row for the new heading (integration tier, owner livespec-dev-tooling-un3zhi) and the regenerated debt register.
