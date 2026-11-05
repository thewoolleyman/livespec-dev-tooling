---
topic: homelab-worker-lan-node
author: claude-opus-5-5
created_at: 2026-11-05T22:03:57Z
spec_commitments:
  impl_followups:
    - id_hint: homelab-worker-lan-bridged-network
      description: |
        The start task declares a bridged home-LAN network in the worker's Lima VM, checks its host prerequisites (socket_vmnet in its root-owned location and a passing limactl sudoers --check) and refuses with a diagnosis when they are missing; the worker container uses the VM's bridged LAN address as its node IP and flannel interface; homelab-worker/networking/cluster.yaml carries the LAN interface and an API server address that is a SAN of the API server's certificate.
---

## Proposal: Homelab worker VM joins the home LAN through a bridged network

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add a bridged home-LAN network to the worker's Lima VM with a prerequisite check, make the worker a home-LAN node, and widen reviewed cluster changes to tailnet-policy changes.

### Motivation

Fixture stage two (plan homelab-k8s-worker-nodes, research 008 §1; macbook-m4-max-info c62eaff2) proved that a worker reachable only over the tailnet cannot carry pod traffic: a K3s node's flannel VXLAN device is bound to its LAN interface, so VXLAN to a tailnet VTEP leaves through the LAN gateway and is lost. The maintainer chose to run the M4 Max worker as a home-LAN node and defer roaming workers (2026-11-05: "Start with the lan bridge, we will worry about the roaming machines like air later, it can be deferred for now."). A bridged Lima network was measured to work on the M4 Max (macbook-m4-max-info 373e5c8e). The route grant the stage-two fixture needed (tailscale-admin#42) showed that tailnet-policy changes are cluster-reachability changes too.

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md, section `## Homelab worker nodes`:

1. Append to the **macOS VM runtime** bullet: "The VM MUST carry a Lima bridged network on the host's LAN interface, so the worker has an address on the home LAN. Before it creates or starts the VM, the task MUST check the bridged network's host prerequisites — Lima's `socket_vmnet` in its root-owned location and a passing `limactl sudoers --check` — and when either is missing MUST exit non-zero, naming each missing prerequisite with its remedy, without creating or starting the VM. The task MUST NOT install or modify those prerequisites itself; they are documented host changes. An existing VM without the bridged network MUST be refused with a diagnosis naming the setting, per the rule above."

2. Insert a new bullet after **Host tailnet identity**: "- **Home-LAN node.** The worker MUST use its VM's bridged home-LAN address as its Kubernetes node IP and as the interface of its pod-network underlay. A worker whose only path to the fleet is the tailnet is out of scope until a later revision of this section; the worker's tailnet identity is not its pod-network underlay."

3. In the **Reviewed cluster changes** bullet, replace "Every production cluster network or control-plane change a worker needs" with "Every production cluster network, control-plane or tailnet-policy change a worker needs".
