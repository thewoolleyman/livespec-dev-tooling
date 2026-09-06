---
topic: ci-runner-node-rebuild-recipe
author: claude-fable-5-1 (livespec plan k3s-on-gmktec-for-vps-usage session)
created_at: 2026-09-06T12:11:40Z
---

## Proposal: The runner-pool node rebuild recipe: one committed bare-metal procedure, one profile per node, rehearsed before it is trusted

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a new section `## Runner-pool node rebuild recipe` to non-functional-requirements.md stating this repository's obligation as the provisioning repository for the fleet's self-hosted CI runner pool: `ci-runner/k3s/` MUST carry ONE procedure that takes a node from powered-on hardware with empty storage to a pool member, beginning with a bare-metal stage under `ci-runner/k3s/phase0-bare-metal/` that precedes the pinned k3s install and the node-local runbook; every node-specific value MUST come from a per-node profile that is data; the procedure MUST be re-runnable and MUST refuse destructive storage steps against populated volumes without explicit consent; a node's rebuild MUST be rehearsed and the rehearsal recorded before the procedure is trusted for that node and after any change to it; the per-host info repository carries the hardware facts and profile values and never the procedure; the pool's backup-and-restore artifacts are data recovery and never the rebuild path. Add one `## Scenario:` section to scenarios.md carrying the end-to-end rehearsal behavior. Both new `## ` headings get `tests/heading-coverage.json` entries co-edited at revise, the scenario's naming the integration tier.

### Motivation

livespec's proposed change ci-host-rebuildable-from-bare-metal (filed 2026-09-06 from plan k3s-on-gmktec-for-vps-usage, epic livespec-sab5gn) states the fleet-level PROPERTY in livespec SPECIFICATION/non-functional-requirements.md §"Self-hosted CI runner host requirements": a host carrying fleet CI MUST be rebuildable from bare metal by a committed procedure that a per-host profile parameterizes, and the recipe, its profiles, and its rehearsal obligation are recorded by the repository that provisions the host's job runtime, never in that specification. This repository IS that provisioning repository (its `ci-runner/k3s/` tree carries `provision-k3s.sh`, the pinned single-node k3s install, and `phase2/install-node.sh`, the ordered node-local runbook that begins at an installed k3s and requires an admin kubeconfig), so the matching obligation belongs here. The maintainer directed on 2026-09-06 that GitOps is the plan's number-one priority — the fleet's dedicated CI hosts rebuildable from scratch, from git, scripted end to end, bare metal to CI node — and ruled the same day that the recipe's home is a new `ci-runner/k3s/phase0-bare-metal/` tree, because that stage runs before k3s exists and before `install-node.sh`'s precondition holds. The independent gitops-rebuildability review of the pool's node on 2026-09-06 found exactly the gap this section closes: everything from a prepared disk onward is in this tree and boot-proven, while the storage-controller virtual disk, the GPT and ESP, the volume group and its logical volumes and filesystems were reached by hand from a recovery medium on 2026-09-04 with only the end state recorded (ledger items livespec-ifwnqj.3, .4 and .5, now children of livespec-sab5gn). A second pool node is planned by the same plan; stating the profile rule here is what makes that node a second profile rather than a second procedure. Per the authoring discipline, the load-bearing behavior carries a scenario, filed with this proposal.

### Proposed Changes

**Change 1 — the new section in SPECIFICATION/non-functional-requirements.md.** Insert the following new `## ` section immediately AFTER the section headed `## Runner-pool cache telemetry` (the file's final section), verbatim:

> ## Runner-pool node rebuild recipe
>
> **Scope.** This section states this repository's obligation, as the repository that provisions the fleet's self-hosted CI runner pool, under livespec `SPECIFICATION/non-functional-requirements.md` §"Self-hosted CI runner host requirements" clause "A host carrying fleet CI MUST be rebuildable from bare metal by a committed procedure". The property is that specification's; the recipe, its profiles, and its rehearsal obligation are this repository's.
>
> **One procedure, staged.** `ci-runner/k3s/` MUST carry ONE procedure that takes a pool node from powered-on hardware with empty storage to a pool member taking jobs, and every stage of it MUST be a committed, executable artifact in this tree. The procedure MUST begin with a bare-metal stage under `ci-runner/k3s/phase0-bare-metal/` that produces the node's storage layout — storage-controller configuration where the node has one, partitioning, volume management, and the role-labeled storage tiers of §"Runner-pool build cache tiers" **Storage placement** with their filesystems — and installs the base operating system, and that stage MUST precede the pinned k3s install and the ordered node-local runbook, whose preconditions (an installed operating system; an installed k3s and its admin kubeconfig) the bare-metal stage MUST establish. The documented rebuild sequence MUST name the bare-metal stage as its first step, so that a rebuild done exactly as written starts from empty storage and not from a prepared disk.
>
> **One profile per node.** Every node-specific value the procedure needs — the storage devices and controller layout, the placement of each role-labeled tier, the network interface and address the node's runtime binds, the node's cluster role (server or agent) and the address of the cluster it joins, and the node's admission capacity — MUST be read from a per-node profile committed beside the procedure, and the procedure MUST NOT embed a value that belongs to one node. A second pool node MUST be a second profile consumed by the same procedure and MUST NOT be a second procedure or a hand-edited copy of the first.
>
> **Re-runnable, and destructive only on consent.** The procedure MUST be re-runnable against a node already in its profile's declared state, changing nothing. Every step that destroys existing storage MUST refuse to run against a populated volume unless that invocation carries the operator's explicit destruction consent, and the refusal MUST name the volume it refused.
>
> **Rehearsed before trusted.** A node's rebuild procedure MUST be rehearsed — executed from empty storage through to the node executing a job — before it is relied on for that node, and again after any change to the procedure or to that node's profile; the rehearsal's outcome MUST be recorded in the plan store or on the owning ledger item, naming the procedure revision and the profile it ran with. A procedure not rehearsed since it last changed MUST be treated as unproven, and a step that a rehearsal cannot reproduce MUST be treated as a defect in the procedure, never as an accepted gap, and MUST be scripted before the node is treated as conforming.
>
> **Facts in the host record, the procedure here.** The per-host information repository for a node MUST carry the node's hardware facts and its profile's values and MUST NOT carry the procedure or any copy of it; this tree MUST NOT carry a host's hardware facts beyond what its profile consumes. A backup-and-restore artifact for a node MAY be kept beside the procedure for data recovery and MUST NOT be documented or used as the way the node's configuration is reproduced.

**Change 2 — the scenario in SPECIFICATION/scenarios.md.** Append the following new `## Scenario:` section immediately AFTER the section headed `## Scenario: a fabro sandbox hits the shared compilation cache` (the file's final section), verbatim, in the file's existing Given/When/Then paragraph style:

> ## Scenario: a pool node is rebuilt from bare metal by the recipe and its profile
>
> Given `ci-runner/k3s/` carries one node rebuild procedure whose first stage is `ci-runner/k3s/phase0-bare-metal/` and one committed profile per pool node
>
> And a pool node is powered on with empty storage
>
> When an operator runs the procedure naming that node's profile
>
> Then the node's storage layout, base operating system, pinned k3s, and node-local mechanisms MUST reach the profile's declared state with no step performed by hand
>
> And the node MUST join the pool and execute a non-gating job addressed to it alone
>
> And re-running the procedure against the finished node MUST change nothing and MUST refuse every step that would destroy its populated storage
>
> And the rehearsal's outcome MUST be recorded naming the procedure revision and the profile

**Change 3 — the heading-coverage co-edits, at revise time.** Because Changes 1 and 2 each add one `## ` heading, the revise payload's `resulting_files[]` MUST include `../tests/heading-coverage.json` with two added entries in the file's existing shape: `{"spec_root": "SPECIFICATION", "spec_file": "non-functional-requirements.md", "heading": "## Runner-pool node rebuild recipe", "test": "TODO", "reason": "Seeded by livespec plan k3s-on-gmktec-for-vps-usage (epic livespec-sab5gn) at revise time 2026-09-06. Replace TODO with the test id that asserts the bare-metal stage exists under ci-runner/k3s/phase0-bare-metal/, is named first in the documented rebuild sequence, and reads every node value from a profile, when the phase0 child lands.", "work_item": "livespec-sab5gn"}` and `{"spec_root": "SPECIFICATION", "spec_file": "scenarios.md", "heading": "## Scenario: a pool node is rebuilt from bare metal by the recipe and its profile", "test": "TODO", "reason": "Seeded by livespec plan k3s-on-gmktec-for-vps-usage (epic livespec-sab5gn) at revise time 2026-09-06. A scenario describes end-to-end behavior, so its test MUST resolve to the integration tier or above: the mapped test is the integration-tier rehearsal of the rebuild procedure against a node profile; replace TODO with that test id when it lands.", "work_item": "livespec-sab5gn"}`. The scenario entry's `reason` names the integration tier as `check-heading-coverage` direction 4 requires.

**Drift sweep (performed while authoring; the reviewer re-derives it).** §"Runner-pool build cache tiers" **Storage placement** already requires every cache tree to live under a label-addressed tier movable by copy and relabel; the new section references those tiers and does not restate their rules. `ci-runner/k3s/README.md` §"Files" describes `provision-k3s.sh` and `phase2/install-node.sh` as the fresh-node sequence; under the new section that description gains a preceding first step when the bare-metal stage lands, which is that child's edit, not this proposal's. `contracts.md` §"Self-hosting" concerns this library's own workflow pins and is unaffected. No count or enumeration elsewhere in the specification refers to the number of runner-pool sections.
