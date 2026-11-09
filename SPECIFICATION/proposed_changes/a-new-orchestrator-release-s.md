---
topic: a-new-orchestrator-release-s
author: claude-opus-5-5
created_at: 2026-11-09T18:16:06Z
---

## Proposal: A canary of an orchestrator build starts only after a stage probe has executed every rendered workflow input command once in a factory pod

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/scenarios.md

### Summary

livespec-dev-tooling's justfile gains an operator-invoked recipe, `just canary-stage-probe <tag>`. It renders every workflow input command that the orchestrator implement workflow at a release tag passes for this repository, quoted exactly as a dispatched launch renders it. It executes each command once, in a checkout of this repository, inside one pod on a factory node built from the factory sandbox image, and reports a per-input verdict. The Canaries and rolls bullet then requires that recipe to have exited 0 against a build's release tag before an operator takes the adopt step that starts a canary of that build. The probe judges rendered inputs only and does not replace the canary's sample runs.

### Motivation

On 2026-11-09 the orchestrator 0.308.0 canary was judged on full sample runs: bd-ib-xdhe5z, about two hours, plus bd-ib-qv7ba2's run 01M701JK9NVG. The defect was in a rendered workflow input. Commit 6f90584d4's conformance hook reinstall rendered the hook-install input shell-quoted as ONE word, so its set-dash-dash construct reached bash as a single command name and exited 127. Three of its seven sites were fail-closed, so every run reaching publish_draft or pr_refresh ended needs_human, and the janitor showed the same 'command not found' and ignored it. Six fleet projects had already adopted the broken build before the samples judged it, and the corrective v0.309.2 roll was needed to recover. A probe that renders and executes each input command once would have caught the defect in minutes, before any clone adopted the build. legacy-coordinator-agent ruled at about 12:3xZ 2026-11-09 that the probe is a PERMANENT canary step. It directed the probe, run by hand, as the gate for the corrective roll. This proposal makes it a committed recipe and a stated canary precondition. Linked work item: livespec-dev-tooling-jfnmnb (plan gmktec-factory-placement, epic livespec-dev-tooling-me5aqz); its spec-change hold names this topic. Composition: livespec-orchestrator-beads-fabro#4749 (maintainer-accepted 2026-11-09 ~17:0xZ, pending its orchestrator revise) moves the release branch's fast-forward to AFTER the canary's samples pass, with canary clones adopting the release by a named-build adopt naming its tag. This repository's Canaries and rolls bullet already starts a canary with the named-build adopt step. The probe is placed before that adopt step, not before the release branch's fast-forward, so it holds under the current release order and under #4749's order alike.

### Proposed Changes

In SPECIFICATION/contracts.md, section "Cross-repo coordination automation surface", subsection "Orchestrator build adoption", insert this bullet immediately BEFORE the bullet that begins "- **Canaries and rolls.**":

"- **Canary stage probe.** livespec-dev-tooling's justfile MUST ship an operator-invoked recipe, `just canary-stage-probe <tag>`. `<tag>` is a published release tag of the orchestrator plugin. It is a local-vantage, operator-invoked surface, NOT a CI check, and it carries no run lever. The recipe MUST render each workflow input command that the orchestrator's implement workflow at `<tag>` passes for this repository: the conformance hook install, every conformance verify step and every `prepare_toolchain_*` input. It MUST render each one exactly as the Dispatcher's launch renders it into the run's inputs, quoting included, because a probe that quotes differently does not exercise the command a run executes. The recipe MUST create exactly one pod on a factory node, from the factory sandbox image the factory instance's environment catalog names, with the factory node selector, including the factory-budget admission node label `ci-runner.io/factory-admit=true`, so that it lands only on a factory node the factory-budget reconciler currently admits. The pod MUST NOT carry the label by which the sandbox driver owns and cleans up its pods (`app.kubernetes.io/managed-by=sandbox-driver-kubernetes`), because the recipe, not the driver, owns its removal. In a checkout of this repository inside that pod, it MUST execute each rendered input command once, and MUST print one line per input naming the input, its rendered command and its exit code. The recipe MUST exit 0 only when every rendered input command exited 0. Otherwise it MUST exit non-zero, naming each failing input with its exit code, and a failure to create, schedule or reach the pod MUST also exit non-zero, naming that cause. The recipe MUST remove its pod when it ends, whatever its verdict, including when it is interrupted. On an idle factory node it SHOULD reach its verdict in under 15 minutes. The probe judges rendered input commands only. It MUST NOT be read as judging the workflow graph, which the canary's sample runs judge end to end."

In the bullet that begins "- **Canaries and rolls.**", after its first sentence ("An operator starts a canary by taking the adopt step in the clones the canary's runs resolve their launch build from: livespec-orchestrator-beads-fabro's for orchestrator work, and a named other repository's for a non-orchestrator leg."), insert:

"An operator MUST NOT take the adopt step that starts a canary of a build until `just canary-stage-probe <tag>` against that build's release tag has exited 0. When it exits non-zero, the build MUST NOT be canaried, and the failing inputs are recorded where the roll is tracked. A passing probe MUST NOT stand in for the canary's sample runs."

In SPECIFICATION/scenarios.md, append two scenarios:

"## Scenario: a canary stage probe refuses a release whose rendered hook-install input exits 127

Given an orchestrator release tag whose implement workflow renders the conformance hook install input so that it exits 127 inside the factory sandbox
When the operator runs `just canary-stage-probe <tag>` on the operator host
Then the recipe MUST print one line per rendered input naming the input, its rendered command and its exit code
And it MUST exit non-zero naming the conformance hook install input with exit code 127
And its pod MUST no longer exist after the recipe ends
And the operator MUST NOT take the adopt step that starts a canary of that build"

"## Scenario: a canary stage probe passes a release whose every rendered input exits 0

Given an orchestrator release tag whose every rendered workflow input command for this repository exits 0 inside the factory sandbox
When the operator runs `just canary-stage-probe <tag>` on the operator host
Then the recipe MUST exit 0
And its pod MUST no longer exist after the recipe ends
And the operator MAY then take the adopt step that starts that build's canary, whose sample runs still judge the workflow graph"

The revise pass that accepts or modifies this proposal MUST co-edit tests/heading-coverage.json with one entry for each new scenario heading. Each entry MAY be a spec-first "test": "TODO" row whose reason names the host-captured tier, plus a "work_item" key naming livespec-dev-tooling-jfnmnb, and the debt register MUST be regenerated in the same commit. The pod and image exist only on the fleet's k3s cluster and forge, which no factory sandbox reaches, so the owed tests are host-captured.
