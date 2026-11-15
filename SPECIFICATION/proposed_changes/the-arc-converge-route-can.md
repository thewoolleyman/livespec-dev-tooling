---
topic: the-arc-converge-route-can
author: claude-opus-5-5
created_at: 2026-11-15T16:55:38Z
---

## Proposal: The ARC converge adds a scale set from one values file and removes it when the file goes

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Make the CI stack converge (`converge-ci-stack.sh`) derive its runner scale sets from the committed values files instead of its hard-coded `SCALE_SETS` map, skip `helm upgrade` for a scale set whose rendered inputs are unchanged so that adding one values file leaves every existing scale set at its Helm revision, and `helm uninstall` a scale set whose values file has been removed (with the `ci_converge_unit` role pruning the removed file and counting the removal as a changed input). The text is placed beside the existing ARC converge clauses in §"Runner-pool node rebuild recipe" of non-functional-requirements.md, with two Given/When/Then scenarios placed after the existing live-converge scenario. The per-organization credential Secret is already covered by v232 and is not restated.

### Motivation

Work item livespec-dev-tooling-xyi5vu (plan stale-base-merge-options, epic livespec-dev-tooling-xowhol) was classified spec-change: its DoD bullets 1 and 2 (adding an ARC runner scale set from one new values file with no revision change to the existing scale sets; a `helm uninstall` when a values file is removed) are stated nowhere in SPECIFICATION at v232. The organization move of 2026-11-15 requires adding scale sets registered at livespec-ai repository URLs beside the existing ones without disturbing them, and removing the old ones when their values files go. Measured on origin/master 0dc8b17fd: `ci-runner/k3s/phase2/reconstruct/converge-ci-stack.sh` hard-codes the 15-entry `SCALE_SETS` map (only the homelab worker sets are found by glob), so a new scale set needs a script edit; its step 7 runs `helm upgrade --install` on every release on every converge run, which advances every release's Helm revision whenever any input changes; and neither the script nor the `ci_converge_unit` role ever runs `helm uninstall`, while the role neither deletes a removed values file from `/usr/local/lib/ci-runner-k3s/arc/` nor counts its removal as a changed input, so removing a values file today changes nothing on the cluster. DoD bullet 3 (the per-organization credential in its own Kubernetes Secret) is already governed by the v232 paragraph "ARC GitHub App credentials, one Secret per account." under "## Runner-pool node rebuild recipe". The requester named contracts.md as a target; the existing ARC converge clauses are in non-functional-requirements.md, so the clause is placed there instead.

### Proposed Changes

The governing text belongs beside the existing ARC converge clauses, which live in `SPECIFICATION/non-functional-requirements.md` §"Runner-pool node rebuild recipe" (not in `contracts.md` or `constraints.md`, neither of which states an ARC scale-set converge clause at v232).

1. In `SPECIFICATION/non-functional-requirements.md`, under the existing heading `## Runner-pool node rebuild recipe`, insert the following paragraph immediately AFTER the paragraph that begins `**Live converge from the control node.**` and immediately BEFORE the paragraph that begins `**ARC GitHub App credentials, one Secret per account.**`. No H2 heading is added or changed in this file.

```
**Scale sets from their values files, added and removed without touching the others.** The runner scale sets that the CI stack converge (`ci-runner/k3s/phase2/reconstruct/converge-ci-stack.sh`, run by `converge-ci-stack.service`) installs MUST be read from the committed values files, and MUST NOT be enumerated in the converge script or in the `ci_converge_unit` role. There MUST be one Helm release per file matching `ci-runner/k3s/phase2/arc/values-*.yaml` other than the template `values-EXAMPLE-repo.yaml`, plus one per file matching `ci-runner/k3s/phase2/arc/worker/values-*-homelab-worker.yaml`, each release named by its file's `runnerScaleSetName` value. The superseded phase-1 file `ci-runner/k3s/arc/values-host-unique.yaml` MUST NOT be one of them. Before its first Helm call for any scale set, the converge MUST refuse a values file that declares no `runnerScaleSetName`, naming the file, and MUST refuse two values files that declare the same `runnerScaleSetName`, naming both files; on either refusal it MUST install, upgrade and uninstall no scale set. Adding a scale set MUST therefore take one new values file (with the ClusterQueue and derivation record the pool's queue rules require) and MUST NOT require an edit to the converge script or to the `ci_converge_unit` role.

A converge MUST leave every scale set whose inputs it did not change as it found it. A scale set's inputs are its values file as rendered by the converge (with the hook-template revision and the architecture overlay rendered in) and the pinned `gha-runner-scale-set` chart. For an installed release whose inputs are byte-identical to the inputs of its last successful apply, the converge MUST NOT run `helm upgrade`, so that the release's latest Helm revision (as `helm history` reports it), its AutoscalingRunnerSet's `metadata.generation` and its listener pod all stay as they were. A release whose inputs changed MUST be upgraded, and a release that is not installed MUST be installed. The converge MUST decide whether the inputs changed from a record read back from the live release (for example, a digest of its inputs stored on the release), and MUST NOT decide it from a file on the host, so that a converge after a boot from an empty datastore installs every scale set. When that read-back fails, the converge MUST upgrade the release, because a failed read MUST NOT be taken as "unchanged".

When a values file is removed, the converge MUST remove its scale set. After the install-and-upgrade step, it MUST list the Helm releases of the `gha-runner-scale-set` chart in namespace `arc-runners`, MUST run `helm uninstall` on each release whose name no committed values file declares, and MUST log each release it uninstalled. It MUST NOT uninstall a release of any other chart, and MUST NOT uninstall the ARC controller release. This removal MUST run even when the always-on stop above skips the installs, because removing a scale set needs no placeable listener. When the listing of releases fails, or any committed values file cannot be read, the converge MUST uninstall nothing and MUST end with a failure that says which read failed: a failed read MUST NOT be taken as an empty set of committed scale sets. The `ci_converge_unit` role MUST remove from the installed tree (`/usr/local/lib/ci-runner-k3s/arc/` and its `worker/` directory) each values file the repository no longer carries, and MUST count that removal as a changed converge input, so that the committed live-converge apply (`just ansible-apply ansible/ci-pool.yml`) runs the converge after a values file is removed and reports no change on the next run.
```

2. In `SPECIFICATION/scenarios.md`, insert the following two scenarios immediately AFTER the existing scenario `## Scenario: a merged runner-pool change reaches the live cluster through one committed apply` (after its last line, `And a second run of the same apply MUST report no change`) and BEFORE the heading that follows it:

```
## Scenario: a new scale-set values file adds its scale set and leaves every existing scale set at its revision

Given the live pool runs one scale set per committed values file under `ci-runner/k3s/phase2/arc/` and `ci-runner/k3s/phase2/arc/worker/`, each last converged with its current inputs

And a merged change adds `ci-runner/k3s/phase2/arc/values-livespec-ai-livespec.yaml`, with `runnerScaleSetName: "livespec-ai-livespec-k3s"`, `githubConfigUrl: "https://github.com/livespec-ai/livespec"` and `githubConfigSecret: arc-github-app-installation-livespec-ai`, together with its ClusterQueue, and changes no other values file, no line of `converge-ci-stack.sh` and no file of the `ci_converge_unit` role

When the operator runs `just ansible-apply ansible/ci-pool.yml` from the control node

Then `converge-ci-stack.service` MUST run `converge-ci-stack.sh` on the CI server and the apply MUST wait for it

And `helm list -n arc-runners` MUST list the release `livespec-ai-livespec-k3s`, and GitHub MUST list a runner scale set named `livespec-ai-livespec-k3s` registered at `https://github.com/livespec-ai/livespec`

And every other release MUST show in `helm history` the same latest revision it showed before the apply, and its AutoscalingRunnerSet's `metadata.generation` and its listener pod's creation time MUST be unchanged

And a second run of `just ansible-apply ansible/ci-pool.yml` MUST report no change

## Scenario: removing a scale-set values file uninstalls that scale set and no other

Given the release `livespec-ai-livespec-k3s` is installed from `ci-runner/k3s/phase2/arc/values-livespec-ai-livespec.yaml`

And a merged change removes that values file and no other values file

When the operator runs `just ansible-apply ansible/ci-pool.yml` from the control node

Then the `ci_converge_unit` role MUST remove `values-livespec-ai-livespec.yaml` from `/usr/local/lib/ci-runner-k3s/arc/` and MUST report the converge input as changed

And `converge-ci-stack.sh` MUST run `helm uninstall livespec-ai-livespec-k3s` in namespace `arc-runners` and log the release it uninstalled

And `helm list -n arc-runners` MUST NOT list `livespec-ai-livespec-k3s`, and no AutoscalingRunnerSet or AutoscalingListener of that name MUST remain

And every other release MUST show in `helm history` the same latest revision it showed before the apply

And a second run of `just ansible-apply ansible/ci-pool.yml` MUST report no change
```

3. The per-organization credential (DoD bullet 3 of livespec-dev-tooling-xyi5vu) MUST NOT be restated: it is already governed by the v232 paragraph `**ARC GitHub App credentials, one Secret per account.**` in the same section, which names the Secret `arc-github-app-installation-livespec-ai` that the first scenario's values file references. The revise that accepts this proposal MUST add `tests/heading-coverage.json` rows for the two new `## Scenario:` headings (a spec-first `"test": "TODO"` row MUST name the integration tier or above, carry `"work_item": "livespec-dev-tooling-xyi5vu"`, and be registered in `tests/heading-coverage-debt.json`).
