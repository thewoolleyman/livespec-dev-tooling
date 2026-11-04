---
topic: homelab-worker-nodes
author: claude-opus-5-5
created_at: 2026-11-04T17:08:27Z
---

## Proposal: Homelab worker nodes

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Add a non-functional-requirements section governing the portable homelab worker node: the `start-homelab-worker-node-container <host>` task, its declared hosts and derived `<host>-homelab-worker` identity, Lima install-or-reuse on macOS, the VM capability probe that must pass before any workload is admitted, idempotent reruns and the one-worker-per-host rule, the separate worker tailnet identity, standard TLS bootstrap into the existing K3s fleet under an admission hold, and reviewed cluster changes. Add six scenarios that state the observable behaviour of those rules.

### Motivation

Plan homelab-k8s-worker-nodes (epic livespec-dev-tooling-ko26ez, research/004-two-host-phases-2026-11-04.md) runs one worker on macbook-m4-max and then one on macbook-air, provisioned by the same start task. A child's Definition of Done must reference a governing heading, and no SPECIFICATION/ heading covers the portable worker yet, so the worker's behaviour is ratified before Phase C's implementation children are filed. This is the repository's own CI and factory infrastructure, so it belongs in non-functional-requirements.md under the Boundary litmus.

### Proposed Changes

Add the following section to `SPECIFICATION/non-functional-requirements.md`, placed after §"Developer host platforms":

```markdown
## Homelab worker nodes

A homelab worker node is one Kubernetes worker that runs in a container on a host the maintainer already owns and joins the existing K3s fleet. The requirements below govern the worker's start task, its host provisioning and its enrollment. Work this section names as owed is owned by plan `homelab-k8s-worker-nodes`.

- **Start task and declared hosts.** `just start-homelab-worker-node-container <host>` MUST be the one entry point that provisions and starts a worker. `<host>` MUST name a host declared in the repository's committed homelab-worker host list; the initial list declares `macbook-m4-max` and `macbook-air`. An undeclared `<host>` MUST be refused, naming the argument and the declared hosts, before any host change. Every declared host MUST be provisioned through the same code path; a host's declaration MAY carry data (such as its VM resource budget) but MUST NOT select different provisioning code.
- **Derived identity.** The task MUST derive the worker name `<host>-homelab-worker` from the argument and MUST use that one name for the worker container, its Kubernetes Node and its worker tailnet hostname.
- **One worker per host.** A host MUST run at most one worker. A rerun with the same argument MUST reconcile that worker in place. A run on a host already bound to a worker of a different name MUST be refused, naming the existing worker, and MUST NOT create a second worker.
- **macOS VM runtime.** On a macOS host the task MUST run the worker inside a named Lima Linux VM using Apple's Virtualization.framework (`vz`) backend. It MUST install Lima through Homebrew only when `limactl` is absent. It MUST reuse an installed Lima whose version is at least the minimum the task declares, and MUST NOT upgrade an installed Lima. An installed Lima older than that minimum MUST be refused, naming the installed and minimum versions. A rerun MUST keep the VM's disk, the worker's persisted identity and its caches. The task MUST NOT stop, recreate or delete an existing VM to converge it; a VM whose configuration cannot be converged in place MUST be refused with a diagnosis naming the setting.
- **Capability probe before admission.** Before it starts the worker container, the task MUST probe the Linux environment the worker will run in for: AppArmor loaded and enforcing; pod user namespaces with idmapped mounts; `/dev/net/tun`; cgroup v2 with the controllers the kubelet needs delegated; shared mount propagation; a nested containerd able to start a container; and local storage that supports reflink copies. When any capability is missing the task MUST exit non-zero, name every missing capability with an actionable remedy, and MUST NOT start the worker container or submit an enrollment request. The probe MUST NOT weaken or disable a capability to make itself pass.
- **Worker image.** The worker image MUST be built from this repository's sources as a native OCI image for the host architecture, running upstream kubelet and containerd with no K3s agent, pinned to the fleet's Kubernetes minor version, and published to GHCR under the repository's existing image publication conventions.
- **Host tailnet identity.** The task MUST NOT change the host's own Tailscale identity, login or settings. The worker MUST join the tailnet under its own `<host>-homelab-worker` identity from inside the worker's network namespace, and that identity MUST persist across worker restarts.
- **Standard bootstrap under an admission hold.** The worker MUST join the fleet through standard Kubernetes TLS bootstrap with a short-lived, narrowly scoped bootstrap credential, and MUST obtain the node identity `system:node:<host>-homelab-worker`. Enrollment material MUST NOT be stored in an image layer, in Git, in a command argument or in a logged or inspect-visible environment variable. A newly joined worker MUST carry the taint `homelab-worker.livespec.dev/admission=hold:NoSchedule` until that hold is lifted by a separate, explicit operator action; the start task MUST NOT lift it.
- **Reviewed cluster changes.** Every production cluster network or control-plane change a worker needs MUST land through a reviewed pull request that records its rollback procedure, and MUST be proved against an isolated K3s fixture matching the fleet's version and network configuration before it is applied to the production fleet.
```

Add the following scenarios to `SPECIFICATION/scenarios.md`, after the last existing scenario:

```markdown
## Scenario: the start task refuses an undeclared host before any host change

Given a host argument that the committed homelab-worker host list does not declare

When `just start-homelab-worker-node-container <host>` runs

Then it MUST exit non-zero naming the argument and the declared hosts

And it MUST NOT install a package, create or start a VM, or start a worker container

## Scenario: a VM missing a required capability stops the start task before the worker starts

Given a declared host whose Lima VM does not enforce AppArmor

When `just start-homelab-worker-node-container <host>` runs

Then it MUST exit non-zero

And its output MUST name the AppArmor capability with an actionable remedy

And it MUST NOT start the worker container or submit an enrollment request

## Scenario: rerunning the start task reuses Lima and keeps the VM

Given a declared host with an installed Lima at or above the task's minimum version

And that host's named Lima VM already exists with a persisted worker identity

When `just start-homelab-worker-node-container <host>` runs again

Then it MUST NOT install or upgrade Lima

And it MUST NOT stop, recreate or delete the VM

And the worker MUST keep the persisted identity it had before the rerun

## Scenario: a second worker on the same host is refused

Given a host already bound to the worker `<host-a>-homelab-worker`

When `just start-homelab-worker-node-container <host-b>` runs on that host for a different declared host `<host-b>`

Then it MUST exit non-zero naming the existing worker `<host-a>-homelab-worker`

And it MUST NOT create a second VM or worker container

## Scenario: the start task leaves the host's own tailnet identity unchanged

Given a declared host logged in to the tailnet under its own host name

When `just start-homelab-worker-node-container <host>` runs

Then the task MUST NOT invoke a Tailscale login, logout or settings change on the host

And the worker MUST enroll in the tailnet under the hostname `<host>-homelab-worker`

## Scenario: a newly joined worker carries the admission hold

Given a worker that completes standard TLS bootstrap into the fleet as `<host>-homelab-worker`

When its Node becomes Ready

Then the Node MUST carry the taint `homelab-worker.livespec.dev/admission=hold:NoSchedule`

And a pod without a toleration for that taint MUST NOT be scheduled onto it
```

The co-edit for `tests/heading-coverage.json` (one row for `## Homelab worker nodes` and one per scenario) lands in the revise commit, as the repository's revise co-edit discipline requires.
