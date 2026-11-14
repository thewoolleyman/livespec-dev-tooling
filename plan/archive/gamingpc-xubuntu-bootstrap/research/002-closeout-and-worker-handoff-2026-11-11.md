# Gaming PC Xubuntu bootstrap — accepted baseline and worker handoff

## Closeout authority and boundary

The maintainer directed this closeout on 2026-11-11 UTC:

> writte a wrapup so I can close your plan out.  You are done unless I need more work on the host, otherwise homelab-k8s-worker-nodes will take it from here. Go ahead and c lose out and archive, I'll reopen if needed.

This is an accepted operational baseline and durable handoff. The epic's scope
ruling supersedes the original six-assertion finish line with the four
closeout assertions below. The original request and assertions in
[001](001-charter-and-discovery-2026-11-10.md) remain unchanged for audit.
Deferred work is explicitly named here; archival does not claim it passed.

## Delivered and observed

- Installed Xubuntu 26.04 on the specifically approved separate 2 TB Crucial
  P310, with its own EFI partition and ext4 root. Existing Windows partitions
  were preserved. The installation record includes exact prior disk approval,
  preservation checks and the maintainer's successful Windows boot afterward.
- Set Xubuntu first in UEFI at the maintainer's request, with a visible
  ten-second GRUB menu offering Windows. A normal maintenance reboot returned
  to Xubuntu, kernel 7.0.0-43-generic, and its separate root.
- Installed the ordinary untagged Tailscale member `gamingpc-xubuntu`,
  `100.80.153.83`, with Tailscale SSH. Login and passwordless sudo were
  observed from the Air, Pro and VPS through the documented paths.
- Configured ordinary SSH host trust on both Macs, independently verified
  against each Mac's Tailscale network map. The same command now works on both:

  ```sh
  ssh ubuntu@gamingpc-xubuntu.perch-rudd.ts.net
  ```

- Applied the maintainer-approved Ubuntu maintenance update: 403 upgrades,
  one new package and no removals. Package audit, dependency and GRUB syntax
  checks passed; the subsequent reboot and remote reconnection succeeded.
- Verified the Radeon RX 9070 XT with accelerated Mesa rendering, currently
  Mesa 26.0.8. The maintainer confirmed password login and desktop operation.
- Published the private host-information repository with measured hardware,
  storage, OS, network, GPU, access, service, rollback and explicit unknowns,
  plus instruction-only agent configuration.

## Measured hardware and access

| Item | Verified value |
| --- | --- |
| CPU | AMD Ryzen 7 9800X3D, 8 cores / 16 threads, amd64 |
| RAM | **32 GB installed**, two 16 GB DDR5 DIMMs in A2/B2; A1/B1 empty |
| DIMM identifier | `F5-7200J3445G16G`; matching G.SKILL product family |
| Configured memory speed | 4800 MT/s; BIOS overclock-profile state not inspected |
| Storage | Separate 2 TB Xubuntu P310; Windows P310 remains protected |
| Network | Wired `enp10s0`; measured LAN 192.168.1.179, negotiated 1 Gbps |
| Tailnet name | `gamingpc-xubuntu.perch-rudd.ts.net` |
| Operator | `ubuntu`, with verified noninteractive sudo |
| Services verified | Tailscale SSH, LAN OpenSSH socket and LightDM |

The firmware omits the DIMM retail suffix, so the exact Trident variant and
color are unverified. The 64 GB purchase kit does not match the two 16 GB
modules actually detected. Advertised DDR5-7200 profile speed is not a claim
that this CPU/board currently runs, or has been stability-tested, at 7200.

## Accepted closeout assertions

1. The installed Xubuntu system boots from its approved separate drive, with
   the preserved Windows layout and historical installation approval and boot
   evidence documented.
2. Plain SSH from both the MacBook Air and MacBook Pro to
   `ubuntu@gamingpc-xubuntu.perch-rudd.ts.net` reaches `gamingpc-xubuntu` as
   `ubuntu` with strict host-key checking and working sudo.
3. The private `gamingpc-xubuntu-info` repository is clonable and publishes
   measured hardware, storage, operating-system, network, GPU and service
   facts, explicit unknowns and instruction-only agent configuration.
4. The `homelab-k8s-worker-nodes` plan holds the published gaming PC access,
   resource and validation handoff and explicit remaining-work dispositions
   under the maintainer's direction.

Current read-only checks establish current state and the availability of the
historical evidence; they do not repeat the installation, original disk
checksums or physical Windows boot. Capture and independent replay records
on epic `livespec-dev-tooling-p37yia` grade these revised assertions only.

## Ownership after this handoff

`homelab-k8s-worker-nodes` (`livespec-dev-tooling-ko26ez`) owns the next steps.
Its existing scope already selected the native Linux k3s-agent route. This
bootstrap did not install k3s, join the cluster, assign capacity, apply workload
roles or compete with that seat's prepared profile/inventory work. The
maintainer's closeout direction designates the receiving plan as owner;
posting the handoff is not a claim that a Herdr seat was personally resumed
or acknowledged it.

Remaining work is transferred or deferred explicitly:

- **DisplayPort startup detection/activation:** worker-plan host follow-up if
  needed. Xorg initially reported DisplayPort disconnected even though the
  monitor was already on that input. It later appeared connected without an
  active mode. Manual `xrandr` activation at 4K/60 Hz restored the primary
  DisplayPort login box, confirmed remotely and by the maintainer. The saved
  greeter monitor preference is not a proven persistent activation fix.
  Headless fleet access works; unattended physical-console startup is unproved.
- **RAM reconciliation and optional tuning:** worker-plan host follow-up if
  needed. Use measured 32 GB for later capacity work. Locating/installing the
  purchased 64 GB kit and changing/testing a BIOS memory profile were not done.
- **Core fleet-manifest registration:** worker plan routes this through
  `livespec` core's owning registration workflow. The host repo's released
  instruction-only configuration is committed; central registration is not
  claimed complete.
- **k3s enrollment, admission, resource sizing and workload proof:** receiving
  worker plan's existing scope, using its shared provisioning and capacity
  rules. This explicitly includes delivery of the cluster agent join token to
  `/etc/rancher/k3s/agent-join-token` through the normal credential path and its `op`, `github-ci-runners` group
  and `/usr/local/bin/with-github-ci-runners-env.sh` prerequisites. These are
  worker-enrollment responsibilities, not unfinished OS/access baseline work.
  The token itself is never copied into this wrap-up. Preserve both operating
  systems and current access paths.

The maintainer may reopen host-bootstrap work if needed. No continuing host
mutation, reboot, background monitor or new worker session is left running by
this bootstrap closeout.

## Published evidence and read-first chain

- [Host record](https://github.com/thewoolleyman/gamingpc-xubuntu-info), main
  `f29a87808974ea9e4299effe6a26b4355d314bc4` at closeout capture; read `AGENTS.md`,
  `docs/bootstrap.md` and `docs/hardware.md`.
- [Air SSH record](https://github.com/thewoolleyman/macbook-air-info/blob/9aa5a467448670b09bec6f0a1083b1afa73bafef/docs/ssh-access.md).
- [Pro SSH record](https://github.com/thewoolleyman/macbook-pro-info/blob/2a7c5605d95955027f75765b383424cfaf605063/docs/gamingpc-ssh.md).
- [Central access record](https://github.com/thewoolleyman/tailscale-admin/blob/5768ced9c32996b7bffffa696a5d7f0e4638e291/README.md).
- The receiving plan's ledger epic `livespec-dev-tooling-ko26ez` contains the
  access handoff and its already authorized worker route; use its latest scope
  and current typed next action rather than an old chat recap.

## Closeout verification

The independent replay reproduced all four revised assertions and published
verified plan record `01a1c923-3741-72ee-b6d7-f4c7633f6f61`. Independent
completeness evidence `gamingpc-closeout-independent-20261111` is recorded in
comment `01a1c923-5bf9-7bcf-810a-0676ed685e00`. Its publishing session differs
from the capture/archiving session. The ordinary archive primitive accepted
all gates, closed epic `livespec-dev-tooling-p37yia` and moved this plan into
`plan/archive/`. No deferred result was asserted as completed.
