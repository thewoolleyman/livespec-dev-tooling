# 011 — M4 inbound VXLAN: what was measured, what is left, and the cluster-wide choice

Plan `homelab-k8s-worker-nodes` (epic `livespec-dev-tooling-ko26ez`). Written
2026-11-11 by the homelab-k8s-worker-nodes seat for legacy-coordinator-agent's
FOR THE MAINTAINER list (coordinator rulings at ~19:10Z and ~19:20Z).

## What is measured

All readings are against `poweredge-xubuntu`, timing a 32 MiB transfer inside
the pods. "Into the M4" means the data flows from poweredge to the M4 worker VM.

| Path | Wi-Fi `en0` (03:33Z) | Wired `en7`, 1 GbE USB (16:04Z, 16:08Z) |
|---|---|---|
| Overlay (VXLAN) into the M4 | 228 KiB/s | 456 / 474 KiB/s |
| Overlay (VXLAN) out of the M4 | 16466 KiB/s | 91022 / 99296 KiB/s |
| Underlay (node IPs) into the M4 | 33436 KiB/s | 109226 / 105703 KiB/s |
| Underlay (node IPs) out of the M4 | 16549 KiB/s | 96376 / 99296 KiB/s |

A correction belongs with these numbers. `prove-worker.sh` names each
throughput figure after the requesting client, not after the direction the data
moves. `throughput-worker-to-peer` is a client on the worker downloading from
the peer, so its data flows INTO the worker. The 16:10Z receipt first reported
the wired result the other way round, as "inbound fixed, outbound collapsed".
It was retracted at 19:05Z, and the numbers above are the corrected reading.

The wired link beats Wi-Fi on every path: inbound overlay is about 2x faster,
outbound overlay about 6x, and the underlay 3-6x. It stays (coordinator ruling,
~19:10Z). The 06:25Z success test, overlay inbound within 2x of underlay
inbound, FAILS: 465 KiB/s against about 105 MiB/s is a ratio of about 230x.

### The two-way offload sweep (18:56-19:03Z, `prove-vxlan-offload.sh` at 9cf436c1, rc 0, 13/13 receipts ok)

- Inbound baseline is 505 KiB/s. Each toggle tried leaves it between 530 and
  605 KiB/s: lima0 gro off, flannel.1 gro off, flannel.1
  tx-checksum-ip-generic off, flannel.1 tso off, and flannel.1 gso off.
- Outbound baseline is 33781 KiB/s, from a cold first transfer. Under each
  toggle it reads 74-96 MiB/s.
- The settings most likely to matter cannot be toggled. `lima0
  rx-checksumming` is `[fixed]`, and `tx-udp_tnl-segmentation` is `[fixed]` on
  both lima0 and flannel.1. lima0 tx, tso and gso are already off.
- No guest offload setting cures inbound. This is the 06:25Z step-0 branch:
  the virtio NIC's fixed rx-checksum handling of VXLAN-encapsulated frames,
  which only a different NIC attachment could change.

## Single-node levers (coordinator rule P5 forest check)

- **Lima native vz bridged networking: unavailable.** Lima 2.2.1 offers only
  socket_vmnet (managed `lima: shared|bridged|host`, or an unmanaged `socket:`)
  and `vzNAT`, per its `share/lima/templates/default.yaml`. `limactl` carries no
  vz bridge, because a Virtualization.framework bridged attachment needs
  Apple's restricted `com.apple.vm.networking` entitlement. vzNAT puts the VM on
  192.168.105.x, which the LAN peers cannot reach, so flannel cannot reach the
  node at all (ruled out 06:25Z).
- **(i) `flannel.1` MTU on the M4 alone: not the cause, by measurement.**
  - A DF ping sweep at ~01:25Z ruled MTU out on Wi-Fi, and the 1400-byte ICMP
    proof passes on wired.
  - On wired, the link MTUs are consistent: `en7` 1500, lima0 1500 and
    flannel.1 1450, which is exactly lima0 minus the 50-byte VXLAN header.
  - Outbound VXLAN at the same MTU runs at 91-99 MiB/s. A fragmentation fault
    would hit large frames in both directions.
  - The homelab-worker flannel net-conf carries no MTU key, so a test value
    would need a committed DaemonSet change. The measurements already exclude
    MTU, so that change is not worth making.
- **(ii) A VMM that holds the bridged entitlement, such as Tart: plausible
  but costly, and unverified on this host.**
  - Tart runs on Virtualization.framework and documents a bridged mode,
    `tart run --net-bridged=<interface>`, which needs that entitlement. Tart is
    not installed on the M4, so the seat could not run
    `codesign -d --entitlements -` on it to verify the entitlement.
  - The cost: the start task (`start-homelab-worker-node-container.sh`), the
    VM template (`homelab-worker/lima/worker.yaml`), the capability probe and
    its tests are all Lima-specific (`limactl` throughout). Moving means a new
    VMM path through the start task, a re-imaged worker VM, a worker departure,
    and a rejoin under `join-worker.sh`.
  - The payoff is uncertain. A vz bridged attachment is still a virtio NIC
    under Virtualization.framework, and the `[fixed]` rx-checksum behaviour
    belongs to that virtio device, not to socket_vmnet. Tart could show the
    same collapse.
  - If the maintainer wants it, it can be measured cheaply first: a throwaway
    Tart VM, bridged on en7, running iperf3 UDP 8472 and VXLAN from poweredge.
    That is a host change the maintainer must authorize.

## The cluster-wide choice: (a) host-gw vs (c) wireguard

The backend question is cluster-wide in practice, for two reasons:

- **Every k3s node already runs vxlan.** k3s v1.36.2 runs embedded flannel,
  with the backend chosen by the server's `--flannel-backend` flag (default
  `vxlan`). The four k3s nodes report `flannel.alpha.coreos.com/backend-type:
  vxlan`.
- **A mixed backend does not interoperate.** The M4 runs its own
  `homelab-worker-flannel` DaemonSet, with its own net-conf (`vxlan`, VNI 1,
  port 8472), so its file could name a different backend. But a flannel node
  programs routes only for peer leases of its own backend type. An M4 on
  host-gw would route to its peers directly, while every vxlan peer would still
  send to the M4 over VXLAN, through the collapsed inbound path. Flannel does
  not support mixed backends.

So the only fix that changes the inbound path is one backend for all five
nodes.

### (a) host-gw: recommended

- **What it does.** Each node installs a plain route to every other node's pod
  CIDR via that node's IP, with no encapsulation. Pod traffic into the M4 then
  takes the underlay path, which is measured at ~105 MiB/s into the M4 today.
  This option removes VXLAN, so it is the one whose fix follows from the
  measurements.
- **Precondition, met.** All nodes must share one L2 segment. All five do:
  poweredge .200, hp .4, gmktec .156, gamingpc .179 and the M4 VM .201, all on
  192.168.1.0/24.
- **Cost, ongoing.** A node off this LAN cannot join: cloud-burst capacity, the
  VPS, or a roaming laptop on another network. The cloud-burst plan, research
  003, would need its own overlay, or a return to vxlan or wireguard.
- **Cost during the switch.**
  - The server flag changes, then k3s restarts on the server and every agent,
    and the M4's DaemonSet net-conf changes to match.
  - Cross-node pod traffic drops while the routes are rebuilt. Every in-flight
    CI job and factory run on poweredge, gmktec and hp is at risk, along with
    gates-cq Jobs, which have `backoffLimit=0`.
  - So the switch runs in a window: `k3s-window-drain.yml pause-arc` to queue
    CI, and the factory's cancel-and-re-dispatch route
    (`.ai/factory-restart-cancels-runs.md`) to empty and refill the factory.
    The existing `restart-k3s-server.yml` and `restart-k3s-agent.yml` do the
    restarts.
  - Per node the switch is minutes; the whole window is perhaps 30-60 minutes,
    unmeasured.
- **Rollback.** The same window run in reverse: the flag back to vxlan, the
  restarts, and the M4 net-conf reverted.

### (c) wireguard-native

- **What it does.** It encrypts pod traffic between nodes over UDP 51820, and
  works across L3, so off-LAN nodes stay possible.
- **Cost.**
  - Every node needs the wireguard kernel module (Ubuntu 24.04 ships it,
    including in the M4 VM).
  - It adds per-packet crypto CPU on every node.
  - The pod MTU drops to about 1420.
  - The switch window and rollback are the same as for (a).
- **Uncertain payoff.** wireguard is still UDP encapsulation into the M4's
  virtio NIC. Whether the `[fixed]` rx path mistreats it as it does VXLAN is
  unmeasured; the 06:25Z UDP discriminator was dropped. It might fix inbound,
  or might collapse the same way.

### Recommendation

The seat recommends **(a) host-gw**:

- Its mechanism avoids encapsulation, and the path it would use is measured
  healthy at ~105 MiB/s.
- Its precondition, one LAN, holds for every current node.
- Its cost is the loss of off-LAN nodes, which no current node needs.

Two cheaper steps come before the switch window. Each is a single-node or
single-host measurement on a committed route. Both need a committed route
before they run, and the maintainer to authorize the host change.

- A UDP-encapsulation discriminator into the M4. It would show whether (c)
  could ever work, and whether (a)'s reasoning holds.
- The Tart bridged-mode measurement from (ii).

If the maintainer would rather keep off-LAN capacity open, choose (c), but
measure UDP 51820 into the M4 first.

The M4 stays held (committed cordon adopted 18:55:37Z) until a route meets the
success test.
