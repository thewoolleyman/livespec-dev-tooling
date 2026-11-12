---
topic: delete-the-dead-phase-1
author: claude-opus-5-5 (ci-pool-provisioning-leftovers)
created_at: 2026-11-12T02:25:56Z
---

## Proposal: A superseded runner-pool rebuild stage is retired from the tree

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Adds one paragraph, "A superseded stage is retired.", to non-functional-requirements.md section "Runner-pool node rebuild recipe", directly after "One procedure, staged.". Once a committed stage of the procedure supersedes an earlier ci-runner/k3s/ artifact and nothing executes or reads it, the artifact MUST be deleted with its pre-deletion commit cited. The README rebuild sequence and the scripts' operator output MUST name the superseding stage. Outside plan/, CHANGELOG.md and SPECIFICATION/history/, a deleted path MAY appear only in a line recording its deletion. Adds one scenario to scenarios.md. It has no H2 of its own in the NFR file, so the only new heading is the scenario's.

### Motivation

Plan ci-pool-provisioning-leftovers (epic livespec-dev-tooling-fby3sx) found five ci-runner/k3s/ phase-1 artifacts with no executor: install-arc.sh, install-kueue.sh, arc/values-host-unique.yaml, kueue/resources.yaml and test-job/proof-job-kueue.yaml. phase2/reconstruct/converge-ci-stack.sh superseded them, inlining their work and never invoking them. The README rebuild sequence and provision-k3s.sh's operator output still tell an operator to run the two installers, so a rebuild done exactly as written runs a superseded installer with values files different from the ones the converge applies. Work item livespec-dev-tooling-y4umcc deletes them. On 2026-11-12 the spec-change-tier judgement on orchestrator v0.320.0 held it with verdict partial on this topic. The judgement found that "Runner-pool node rebuild recipe" requires the documented sequence to follow the committed automation, but states neither naming the boot converge as the ARC/Kueue install step, nor deleting superseded installers, nor citing pre-deletion commits. The sibling obligation "A replaced installer is retired" in "Host provisioning tree" covers only ansible roles that carry a # Replaces claim, so it does not reach this tree. Excluding SPECIFICATION/history/ keeps a retirement from editing a frozen snapshot, which the first y4umcc run did (livespec-dev-tooling#4229).

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section "## Runner-pool node rebuild recipe", insert the following paragraph immediately after the paragraph that begins "**One procedure, staged.**":

**A superseded stage is retired.** When a committed stage of the procedure supersedes an earlier artifact under `ci-runner/k3s/` (an installer, or a manifest or values file that only that installer applied), so that no stage of the procedure executes or reads it any longer, that artifact MUST NOT remain in the tree, and the commit that deletes it MUST cite the artifact's pre-deletion commit in its body. `ci-runner/k3s/README.md`'s rebuild sequence and the operator output of the procedure's scripts MUST name the superseding stage, never a superseded artifact, as the step that installs what the superseded artifact installed. Outside `plan/`, `CHANGELOG.md` and `SPECIFICATION/history/`, a deleted superseded artifact's path MAY appear only in a line that records its deletion. An artifact that some stage still executes or reads is not superseded and MUST stay in the tree.

In SPECIFICATION/scenarios.md, append the following scenario:

## Scenario: a superseded ci-runner/k3s installer is deleted and the rebuild sequence names the boot converge

Given `ci-runner/k3s/phase2/reconstruct/converge-ci-stack.sh` installs ARC and Kueue on boot, and no stage of the procedure executes `ci-runner/k3s/install-arc.sh` or `ci-runner/k3s/install-kueue.sh` or reads the values and manifest files only they applied

When the change that retires them lands

Then neither installer, nor any values or manifest file that only they applied, MUST exist in the tree

And the deleting commit's body MUST cite each deleted file's pre-deletion commit

And the rebuild sequence in `ci-runner/k3s/README.md` and the operator output of `ci-runner/k3s/provision-k3s.sh` MUST name the boot converge as the step that installs ARC and Kueue

And outside `plan/`, `CHANGELOG.md` and `SPECIFICATION/history/`, a line naming a deleted path MUST be one that records its deletion

And `ci-runner/k3s/phase2/kueue/cluster-queue-phase1-proof.yaml`, which the converge still applies, MUST remain in the tree

The revise that accepts this proposal MUST add a tests/heading-coverage.json row for the new scenario heading, a spec-first TODO row naming its tier and an owning work_item, and MUST register it in tests/heading-coverage-debt.json.
