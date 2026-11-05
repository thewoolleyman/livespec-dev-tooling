> **Superseded in part, 2026-11-05:** stage two ran and failed every pod-network check, because a K3s node's flannel VXLAN device is bound to its LAN interface. Option A is not the production underlay, §4's "There is no ACL change" was wrong, and §5's production /32 routes are dropped. The M4 Max worker joins as a home-LAN node instead. See [008](008-lan-worker-and-test-strategy-2026-11-05.md) §1-§3.

# 007 — Fixture stage two: the tailnet underlay (2026-11-05)

Stage one is proved. On `hw-fixture` (k3s v1.36.2-k3s1, production flags, M4 Max worker VM), the worker joined through the
production path:

- At `egress-selector-mode: agent`, logs and exec on the worker fail. That is the negative control (macbook-m4-max-info
  `20fc08aa`).
- At `disabled`, all 11 checks of 006 §3 pass (`a97ec2f3`, `87570a5a`): logs, exec, port-forward, kubelet stats, K3s-node logs,
  pod-to-pod both ways, ClusterIP, DNS and a NetworkPolicy deny.

In stage one the worker sat on the fixture's Docker network, so its VXLAN reached the K3s nodes directly. Stage two removes that
shortcut. It proves the underlay production will use: K3s nodes on a LAN, and a worker that reaches them only over the tailnet.
005 §3 calls this Option A (per-node /32 subnet routes) and lists its unknowns. This note decides how stage two runs.

## 1. Why Option A's routes are needed in both directions

- **Node to worker.** Flannel's VXLAN device on a K3s node is `local <LAN IP> dev eno1`, so the outer packet's source is the
  node's LAN address, not its tailnet address. The worker's tailscaled accepts a packet from a peer only if its source is in that
  peer's AllowedIPs. So the node must advertise its own `<LAN IP>/32` and have it approved. Without that, the worker drops every
  VXLAN packet from the node, even though the node itself routes 100.x over `tailscale0` today.
- **Worker to node.** The worker reaches `<LAN IP>` only through the advertised /32, so it runs with `--accept-routes`. The
  converge step in livespec-dev-tooling#3473 runs `tailscale up --hostname=<worker>` without that flag. That is a defect for
  Option A and is fixed with this slice.

One alternative was tested and rejected: letting the worker reach the LAN through the Mac host's NAT. It covers only the worker
to node direction, and only while the Mac is at home, so the AllowedIPs problem above remains.

## 2. Stage-two topology inside the M4 Max worker VM

- **The fixture's "LAN".** This is `hw-fixture`'s Docker network (172.18.0.0/16). Its two K3s nodes keep the embedded flannel
  exactly as in stage one: `public-ip` 172.18.0.x, VTEP bound to `eth0`. That mirrors poweredge and gmktec on `eno1`.
- **Tailscale on the fixture's K3s nodes.** Each node container runs its own tailscaled, the same pinned release the worker image
  carries (1.104.4, SHA-256 checked), with `--state=mem:` so it is an ephemeral device. The tailnet removes it once it goes
  offline, and nothing persists in the tailnet after teardown. Each node logs in interactively as an untagged member and
  advertises its own `<172.18.0.x>/32`. This is the same per-node shape production uses: no subnet router, no SNAT question, and
  risk 1 of 005 (outer-packet routing with the VTEP bound to a device) is exercised on the real flannel path.
- **The worker.** It runs in production mode: off the fixture network, on Docker's default bridge, which Docker's isolation rules
  separate from the fixture network. It joins the tailnet as `<host>-homelab-worker` with `--accept-routes`. Its flannel
  interface is `tailscale0`, as production's ConfigMap `homelab-worker-cluster` sets it, so the worker's VTEP `public-ip` is its
  tailnet IPv4. Its node IP is its tailnet IPv4, and it reaches the fixture API server through the advertised /32.
- **The worker's identity is the production one.** The tailnet identity `<host>-homelab-worker` persists by design (spec "Host
  tailnet identity"), and a second device under the same name would be renamed `-1`. So the stage-two worker uses the production
  tailscale state (`/mnt/lima-hwdata/worker/tailscale`). Its kubelet, containerd and enrollment state stay under the fixture root
  (`/mnt/lima-hwdata/fixture-worker`), with `tailscale/` there as a symlink to the production directory. A bind mount resolves the
  symlink, and teardown's `rm -rf` of the fixture root removes only the link. The maintainer approves the worker's login once,
  here, and production reuses it.

## 3. What stage two proves

The 11 checks of `prove-fixture-worker.sh` at `disabled`, now over the tailnet underlay, plus:

- **MTU asymmetry (005 risk 3).** The worker's flannel derives 1230 (1280 - 50); the nodes use 1450. Large TCP transfers run both
  ways between a worker pod and a node pod, plus a UDP datagram above 1280 bytes.
- **Path recording.** For each node, record whether the tailnet path is direct or DERP-relayed (`tailscale ping`), because a relay
  changes latency and MTU.
- **No LAN hijack.** The fixture nodes' prefs keep `RouteAll:false`, and the worker's `--accept-routes` routes only the advertised
  /32s.

## 4. Maintainer actions stage two needs (asked once, together)

1. Approve three tailnet logins: the worker `macbook-m4-max-homelab-worker` (persistent; production reuses it) and the two
   ephemeral fixture nodes (`hw-fixture-server-0`, `hw-fixture-agent-0`).
2. Approve the two fixture /32 routes in the admin console.

There is no ACL change, no tag, no auth key and no autoApprover. tailscale-admin's constraints forbid adding any of those without
the maintainer's exact authorization, and none is needed.

## 5. Production Option A, after stage two passes

poweredge, gmktec and hp each run `tailscale set --advertise-routes=<own LAN IP>/32`; the maintainer approves the routes; rollback
is `tailscale set --advertise-routes=`. These are host changes for each node's owner, recorded in the fleet's host records, and
reviewed with rollback, as 005 §4 item 7 says.

**Risk to carry into that change (005 risk 2).** macOS clients accept subnet routes by default. Once 192.168.1.x/32 routes exist,
a Mac at home would reach those three nodes over WireGuard instead of the LAN. The path keeps working but is slower. The
production change must either turn off route acceptance on the home Macs (a host change through each Mac's info-repo agent) or
record the slower path as accepted. That is decided with the production change, not in stage two.
