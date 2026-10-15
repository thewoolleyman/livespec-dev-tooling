# docker-engine-guard: design (copied for the implementing factory runs)

Provenance. This file is a VERBATIM copy of
`plan/petri-factory-on-gmktec/research/002-docker-engine-dead-man-design-2026-10-15.md`
in `thewoolleyman/livespec-orchestrator-beads-fabro`, as merged at
`42c75216` (PR #3033). It is copied here because a factory run clones only
this repository. The original stays authoritative; if the two ever differ,
the original wins. The implementation rider that the round-8 reviews added
follows the copy, under "Implementation rider".

How to read it. The document grew by revision. **Revisions 5 to 8 (sections
F, G, H and I) govern**; where a later section and an earlier one disagree, the
later one wins, exactly as each revision's own preamble says. Sections before
"Revision 5" are kept for their measured facts (the "Measured state" section,
Mechanism 1's start condition, Mechanism 4's firewall footprint, R6's package
fence, R7's provenance states and R8's probes), which Revision 5 says stand.

Work items: plan epic `bd-ib-fyozyd` (orchestrator ledger) and items
`livespec-dev-tooling-xxfqqr` (the host-routed role and converge) and its
factory-safe guard child (this repository's ledger).

---

# 002 — Docker on gmktec-xubuntu without a lockout: the docker_engine role design

Date: 2026-10-15. Author: session `petri-factory-on-gmktec`. Carrier:
`livespec-dev-tooling-xxfqqr`. **Revision 4.** Rounds 1, 2 and 3 of independent review (all BLOCKERS) of the independent read-only review are answered in "Review
dispositions" at the end. Round 2 showed that a controller and a watchdog
arbitrating through files cannot be made crash-safe without a lot of protocol.
Revision 3 therefore removes the race instead of arbitrating it: ONE host-local
actor owns every decision, and Docker is made UNABLE to start by any path
unless that actor allows it. Nothing converges on gmktec-xubuntu until a fresh
review of this revision returns NO-BLOCKERS.

## The constraint

The maintainer is travelling and cannot reach gmktec-xubuntu physically. Its
only remote access is Tailscale SSH (served from tailscaled's userspace network
stack, which still depends on the host's underlay networking, routes, DNS and
tailscaled's health). `local-homelab-llama-server.service` and `k3s-agent`
(a CI pool agent with ARC listener and CI job pods, 12 churn slots per its
committed profile) must keep running throughout.

## Measured state (2026-10-15)

gmktec-xubuntu: Ubuntu 26.04; iptables 1.8.11 on the nft backend; FORWARD and
INPUT policy ACCEPT; IPv4 forwarding 1, IPv6 all/default forwarding 0/0,
bridge-nf-call-iptables/ip6tables 1/1; policy rules 5210-5270 and table 52 are
tailscaled's; no `docker0`, no `DOCKER*` chain, no Docker or containerd
package; `/var/lib/docker`, `/var/lib/containerd`, `/etc/docker` and
`/run/docker.sock` absent. `/run/containerd` EXISTS and holds `runc/` and `s/`:
k3s's embedded containerd (socket `/run/k3s/containerd/containerd.sock`) keeps
its shim sockets and runc state there. No `needrestart`, no
`/usr/sbin/policy-rc.d`. apt hooks present: `20apt-esm-hook.conf`,
`20packagekit`, `50appstream`, `50command-not-found`, `70debconf`.
`unattended-upgrades`, `apt-daily.timer`, `apt-daily-upgrade.timer` active.
The agent has `/etc/rancher/k3s/node-status-kubeconfig` (the pool's
node-status credential). The LLM's `/health` on the tailnet address answers 200
without a key.

hp-xubuntu: same OS and the same three package versions beside a k3s agent;
packaged units `TimeoutSec=0`, `Restart=always`, `KillMode=process`; postinst
scripts enable the units and start them; Docker 29 adds chains `DOCKER`,
`DOCKER-USER`, `DOCKER-FORWARD`, `DOCKER-CT`, `DOCKER-BRIDGE`,
`DOCKER-INTERNAL` in both families plus direct built-in-chain rules (raw
PREROUTING per-container drops, nat POSTROUTING masquerade of
172.17.0.0/16).

## Mechanism 1 — Docker cannot start unless allowed (fail-closed, durable)

Before any package is installed, the role writes systemd drop-ins for
`containerd.service`, `docker.service` and `docker.socket` carrying

```ini
[Unit]
ConditionPathExists=|/run/docker-engine-guard/allow-start
ConditionPathExists=|/var/lib/docker-engine-guard/confirmed
```

(the `|` prefix makes the two an OR). systemd evaluates the condition on EVERY
start attempt — boot, socket activation, a postinst `invoke-rc.d` start, a
`Restart=` respawn, an operator's `systemctl start` — and an unmet condition
leaves the unit inactive without running it. So:

- the package install cannot start anything (the postinst start finds the
  condition unmet), and the install is network-inert by construction, not by
  masks whose interaction with `deb-systemd-helper` would need proving;
- `/run` is tmpfs, so after ANY reboot before confirmation neither path
  exists and Docker cannot start: the durable inhibition is the absence of a
  file, which needs no boot-time guard to succeed;
- removing `/run/docker-engine-guard/allow-start` is the first act of a
  rollback, after which `Restart=always` cannot respawn the daemon.

The role verifies the drop-ins are loaded (`systemctl show -p
ConditionPathExists` on each unit) before the install, and verifies after the
install that all three units are inactive.

## Mechanism 2 — one actor owns the transition

`/usr/local/libexec/docker-engine-transition` (Python, stdlib only; the host
has Python 3.14) runs as a persistent template unit
`docker-engine-transition@<run-id>.service` with `Restart=on-failure`. It is
the ONLY party that creates `allow-start`, starts the daemons, decides
`confirmed` or `rolled-back`, and cleans up. The Ansible controller never
starts, enables or stops Docker; it only:

1. writes configuration while the host is inert, then starts the actor unit;
2. runs the CONTROLLER-SIDE probes (a new Tailscale SSH connection with
   connection sharing disabled, and the LLM `/health` across the tailnet)
   when the actor's state says `awaiting-confirmation`, and writes
   `/var/lib/docker-engine-guard/<run-id>/controller-ok` (a file the actor
   reads; the controller's write grants nothing by itself);
3. reads the actor's state file until it is `confirmed`, `rolled-back` or
   `rollback-partial`, and fails the play on anything but `confirmed`.

The actor's state is one file, `state.json`, replaced atomically
(`write tmp; fsync; rename; fsync dir`), so every reader sees a complete prior
state or a complete new one. It records the phase and, during rollback, the
completed rollback phases. Because one process makes every decision in
sequence, there is no claim race to arbitrate: confirmation and rollback cannot
both happen.

**Phases of the actor:**

1. `starting`: create `allow-start`; start `containerd.service`, then
   `docker.service`, each with a 60-second bounded wait for readiness
   (`docker info`).
2. `canary`: pull and run ONE canary container from a small pinned image
   (by digest) with `--network bridge`, which exercises the endpoint, veth and
   per-container raw rules. From the host, read the canary PID's
   `/proc/<pid>/cgroup` and confirm its path is under `fabro-sandbox.slice`,
   then read that slice's `memory.max` and `cpu.max` from the host and compare
   with the declared values. From inside the canary, an HTTPS request to a
   fixed external endpoint must succeed (bridge egress).
3. `observing`: for a window of `W` seconds, every 15 seconds, run the
   HOST-SIDE probes (Mechanism 3) and require every sample to pass; write
   `awaiting-confirmation` once the window opens.
4. `confirm`: when the window has passed AND `controller-ok` exists AND it was
   written after the window opened, stop and remove the canary, write
   `/var/lib/docker-engine-guard/confirmed`, remove `allow-start`, enable the
   three units, write state `confirmed`, and exit 0.
5. On ANY failed probe, any failed start, any phase exceeding its own
   deadline, or the overall deadline `N` expiring without `controller-ok`:
   **rollback**.

**Rollback**, in priority order, each phase with its own deadline, each
completion recorded in `state.json` before the next begins, and the whole thing
idempotent so that a restarted actor (after a crash or a kill) resumes from
the first incomplete phase:

1. remove `allow-start` (no new start of any of the three units is possible);
2. restore each family's FORWARD policy to its snapshot value if it differs
   (access-relevant, takes milliseconds);
3. kill by cgroup: `systemctl kill --kill-whom=all --signal=SIGKILL` on
   `docker.service`, `containerd.service` and `fabro-sandbox.slice` (which
   holds every container this run created), then a bounded `systemctl stop`
   of all three plus `docker.socket`; verify no process remains in those
   cgroups. Killing by cgroup is what spares k3s: its containerd and shims
   live in `k3s-agent.service` and the kubepods slices, never in these
   cgroups. Nothing under `/run/containerd` is deleted, because k3s's shims
   keep sockets and runc state there;
4. remove Docker's firewall footprint (Mechanism 4);
5. delete `docker0` and any veth whose master is `docker0`;
6. compare forwarding and bridge-netfilter sysctls of both families with the
   snapshot and RECORD any difference (shared state is not written back
   blindly; a difference is reported as a partial recovery);
7. write `rolled-back`, or `rollback-partial` naming each phase that did not
   complete.

The actor unit has `TimeoutStartSec=infinity` and enforces its own per-phase
deadlines, so systemd never kills it mid-rollback; if it does die,
`Restart=on-failure` resumes it from `state.json`. A boot-time copy of the same
actor (`docker-engine-transition-boot.service`, enabled, ordered `Before=` the
three units) resumes any run whose state is neither `confirmed` nor
`rolled-back` — but correctness after a reboot does not depend on it, because
Mechanism 1 already prevents any start.

**Budgets.** `N` (overall deadline before confirmation) is 1500 seconds.
Start 120, canary 180, observation window `W` 420 (see Mechanism 3),
controller probes 120, slack 660. Rollback phases: 1-2 within 5 seconds; 3
within 60; 4 within 300 with per-command `iptables -w 5` and at most three
passes; 5-7 within 30. A rollback phase that exceeds its deadline is recorded
and the actor proceeds to the next phase; it then retries incomplete phases
once more before writing its final state.

## Mechanism 3 — what is probed, before and during

All host-side probes run in the role's preflight (they must pass BEFORE
anything changes; a failing baseline is a refusal) and continuously during the
observation window.

1. **Node Ready**: through `/etc/rancher/k3s/node-status-kubeconfig`, the
   Node object's `Ready` condition is `True`. Reported as Node Ready, never
   substituted by kubelet healthz.
2. **Services**: `k3s-agent`, `tailscaled` and every unit in
   `docker_engine_must_stay_running` are active.
3. **Pod network, from a pod's network namespace**: choose a running pod on
   this node that is NOT host-network (k3s crictl `inspectp`), take its
   sandbox PID, and from `nsenter -t <pid> -n` with host binaries run fresh
   request/reply probes: a DNS query to the cluster DNS service IP whose
   answer comes from a DNS pod on ANOTHER node (verified at preflight from the
   endpoint's node name through the node-status credential's read of
   endpoints, or else the probe is a TCP connect to a pod IP in another node's
   pod CIDR); a TLS handshake to the Kubernetes API service ClusterIP; an
   HTTPS request to `https://api.github.com/zen`. The pod is re-selected if it
   disappears (ARC listener churn).
4. **Firewall invariants**: `iptables-save` and `ip6tables-save` WITHOUT
   counters, canonicalized; each family's FORWARD policy equals the snapshot.
   A change in INPUT or a `ts-*` chain is reported as a diagnostic and fails
   the probe (fail-closed), without claiming Docker caused it.
5. **Sysctls**: the five forwarding and bridge-netfilter values equal the
   snapshot.

**Window `W`.** k3s's embedded network-policy controller (kube-router)
resyncs on a five-minute period by default and kube-proxy on thirty seconds;
the role reads the effective k3s agent flags at preflight, refuses if either is
set above five minutes, and sets `W` to the longer period plus two minutes
(420 seconds at the defaults). Samples are every 15 seconds; every sample must
pass.

The controller-side probes (new Tailscale SSH session; LLM `/health` across
the tailnet) run at preflight, and once more after `awaiting-confirmation`,
before writing `controller-ok`.

## Mechanism 4 — removing exactly Docker's firewall footprint

Snapshot at preflight: `iptables-save` and `ip6tables-save` per table, without
counters. At rollback, per family and table: parse current rules into exact
token lists; Docker's rules are those present now and absent from the
snapshot that reference `docker0`, `172.17.0.0/16` or a chain absent from the
snapshot whose name starts with `DOCKER`. Delete each by its full
specification with `-D`, never by position. Then flush every Docker chain
absent from the snapshot, then delete them. Only the iptables-nft commands are
used. Re-read and repeat (at most three passes) and finally verify the residual
set is empty, recording any residue. The guarded scope is the default
`docker0` bridge only: the role refuses at preflight, and the actor fails its
probes, if any other Docker network, bridge or Docker-created interface
exists.

## Mechanism 5 — the apt transaction is fenced and audited before it runs

1. **Fence**: stop `apt-daily.timer` and `apt-daily-upgrade.timer`, then wait
   (bounded) until no `apt`, `apt-get`, `dpkg` or `unattended-upgrade` process
   runs and the dpkg frontend lock is free. The timers are restarted at the end
   of the role run whatever its outcome (an `always` block). These are not
   network units.
2. **Audit before install**: `apt-get -s install --no-install-recommends
   --no-remove docker.io=29.1.3-0ubuntu4.1 containerd=2.2.2-0ubuntu1.1
   runc=1.4.0-0ubuntu1`; refuse unless every `Inst` line is in the committed
   allowlist of (package, version) pairs and there is no `Remv` and no
   upgrade of an installed package. Download exactly those `.deb` files
   (`apt-get download`, into a role cache) and refuse unless their maintainer
   scripts match committed sha256 digests (audited once by reading them, the
   audit recorded in HOST_VARS.md). The host's apt hook files are compared
   with committed digests too; an unexpected hook refuses.
3. **Install**: from the downloaded `.deb` files (`dpkg -i` on that exact
   set), so the transaction that runs is byte-for-byte the one audited, with no
   resolver decision left. A post-install `dpkg-query` diff must show exactly
   the expected additions.

Because Mechanism 1 holds, a dpkg run interrupted half-way leaves inert
packages that cannot start; the next role run classifies that state
(Mechanism 6) and completes it with `dpkg --configure -a` inside the same
fence.

## Mechanism 6 — what a later run does with what it finds

The preflight classifies the host before acting:

| found | action |
| --- | --- |
| no Docker packages, no Docker state, no guard directory | fresh install |
| packages installed, `/var/lib/docker-engine-guard/installed` names this role's audited set, no `confirmed` | resume: complete configuration, start a new actor run |
| `confirmed` present and configuration matches | validate only (probes read-only); no-op |
| a run whose state is `rollback-partial` | refuse until an operator acknowledges `-e docker_engine_acknowledge_run=<id>` after reading its record |
| Docker packages or state without this role's `installed` record (for example hp's hand-installed Docker) | refuse: foreign Docker is never adopted or touched |

`/var/lib/docker` or `/var/lib/containerd` holding data from anything but this
role's own recorded runs is foreign state; it is refused, never erased.

## The daemon configuration

```json
{
  "iptables": true,
  "ip6tables": true,
  "ip-forward": true,
  "ip-forward-no-drop": true,
  "ipv6": false,
  "bip": "172.17.0.1/16",
  "cgroup-parent": "fabro-sandbox.slice",
  "live-restore": false
}
```

No `default-address-pools`: the factory creates no network beyond `docker0`,
and the guarded scope refuses any. `ip-forward-no-drop` keeps the FORWARD
policy ACCEPT on every daemon initialization (reviewer, round 1, upstream
29.1.3 source). `ipv6: false` keeps the default bridge IPv4-only.
`cgroup-parent` names the sandbox slice, whose unit is installed and started by
the slice role's systemd-only half BEFORE the actor's first start.
Sandbox reachability is unchanged from hp: Docker accepts traffic from
`docker0` and masquerades it outward; this design sets no egress policy.

## Capacity and admission

The slice on gmktec is sized from gmktec. The kubelet's `system-reserved` must
already be EFFECTIVE (read from the live Node's allocatable) to cover the
slice before the current Fabro server admits a run; it lives in gmktec's
phase0 profile, owned by the `k3s-on-gmktec-for-vps-usage` plan, whose
profile declares empty `KUBELET_ARGS` and 12 churn slots today. The fresh-host
order is: slice unit (systemd only), `docker_engine` (through `confirmed`),
the slice role's daemon-dependent half, `otel_receiver`, `sccache_redis`,
`container_reclaim`, `disk_guard`, `fabro_server` with the gmktec instance
`service_state: stopped` until the reservation is effective. The play's tags
and host groups are arranged so the first-install logic can never run on
hp-xubuntu (Mechanism 6 also refuses its foreign Docker).

## Acceptance before the gmktec converge

The role's actor is exercised by fault injection on a disposable host before
gmktec: kill the actor at each phase boundary and in the middle of each
rollback phase, kill the controller after `controller-ok`, withhold
`controller-ok`, fail a probe, and reboot before confirmation; each must end
`rolled-back` (or `confirmed` where confirmation had completed) with no
Docker process, no Docker rule and no `docker0` left behind on rollback.

Two layers carry that acceptance. (a) Unit tests of the actor's phase machine
in livespec-dev-tooling's suite, with the system calls behind a narrow
interface and a fake host: every phase boundary, every rollback phase
interrupted and resumed, every deadline, both outcomes of the controller
signal. (b) An integration run on a disposable QEMU virtual machine on the
control node (Ubuntu 26.04 cloud image; the control node has QEMU but no
KVM, so it runs emulated and slowly), with real systemd, real dpkg, real
iptables-nft and the real three packages, and with the k3s and LLM probes
replaced by stubs that the test makes pass or fail. Measured 2026-10-15:
`/usr/bin/qemu-system-x86_64` exists on the control node and `/dev/kvm` does
not; hp-xubuntu has `/dev/kvm` but no VM tooling and runs live factory work,
so it is not used. The k3s coexistence itself is not exercised before gmktec;
the probes in Mechanism 3, the baseline refusal and the rollback are what
cover it there.

## Review dispositions

Round 1:
1. Rollback could hang: SIGKILL by cgroup after removing the start permission,
   per-phase deadlines, no systemd start timeout on the actor, resumable phases.
2. Races between expiry, confirmation and install: one actor (Mechanism 2);
   install outside the window and inert (Mechanism 1); reboot covered by the
   tmpfs start permission.
3. Cleanup missed direct rules: Mechanism 4 (resolved in round 2).
4. Counter deltas: Mechanism 3 (resolved in round 2).
5. Apt fence: Mechanism 5 (timers stopped, audited downloaded set installed
   by `dpkg -i`, hook digests).
6. Slice not established: slice unit started before first start; the canary's
   cgroup and the slice's limits read from the host.
7-8. Sysctls and scope: recorded comparisons; `docker0`-only scope enforced.
9. Play cannot target gmktec: carrier `livespec-dev-tooling-2puzjr`, with the
   first-install order above.
10-11. Resolved in round 2.
12. Stale host records: fixed by a pull request to `gmktec-xubuntu-info`
    coordinated with `k3s-on-gmktec-for-vps-usage` before the converge.

Round 2:
1. Non-crash-safe claim: no claim exists; one actor, atomic `state.json`,
   resumable rollback owned by the actor.
2. Activation outside the arbiter, disabled-at-boot asserted: the actor alone
   creates `allow-start` and starts the units; `ConditionPathExists` makes
   every start path fail closed without depending on masks, enablement or a
   boot guard succeeding.
3. Apt transaction race and hooks: Mechanism 5 installs the exact audited
   `.deb` set under a fence, with hook digests.
4. Rollback timeout: no systemd timeout; per-phase deadlines with priority
   order (start permission, FORWARD policy, kill, firewall, interfaces,
   sysctls) and resume after any kill.
5. Address pools: removed; `docker0`-only scope enforced at preflight and in
   probes.
6. Empty store and consumers: Mechanism 6 refuses foreign state; the canary
   is the only container during the guarded phase and is killed by cgroup.
7. Container cgroup proof: read from the host via the canary PID; canary runs
   during the observation window, before confirmation.
8. Resume path: Mechanism 6.
9. Probe scope and timing: Node Ready via the node-status credential;
   non-host-network pod re-selected on churn; cross-node DNS verified; `W`
   derived from the effective resync periods; continuous sampling; counters
   stripped.
10-11. Notes accepted as stated.
12. Companion implementation and host records: as round 1 item 12.

## Revision 4 — what changes, and why

Round 3 was reviewed twice, by a Fable reviewer and by a read-only Codex
reviewer, independently. Both judged the start condition (Mechanism 1) sound
against the systemd 259 source the hosts run. Both found the actor's
crash-safety, ownership and liveness incompletely specified, and both found
the pre-install condition check unable to observe what it claimed. Revision 4
replaces the affected parts of Mechanisms 1, 2, 3, 5 and 6 with the rules
below; where this section and an earlier section disagree, this section
governs.

A context change since revision 3 also matters: the plan's first step is now
a direct-LAN OpenSSH fallback (port 22022, bound by device to the wired
interface, separate host key), so gmktec has two independent access paths
(Tailscale SSH and LAN OpenSSH through poweredge or hp), and both arrive on
INPUT, which no step of this design touches. The Docker converge does not
start until that fallback is proven on gmktec.

### R1. One permission at a time, and one commit point

There are exactly two start permissions, and at any moment at most one of them
is in force:

- before the commit point, ONLY `/run/docker-engine-guard/allow-start`
  (tmpfs) exists; `/var/lib/docker-engine-guard/confirmed` does not;
- the COMMIT POINT is the atomic creation of `confirmed` (write a temporary
  file holding the run id and the configuration digest, fsync, rename, fsync
  the directory). Before it, any failure rolls back. After it, the run is
  committed: no failure after the commit point ever rolls back; recovery only
  FINISHES confirmation (remove `allow-start`, enable the units, write the
  terminal state), every step idempotent.

`state.json` is derived, never authoritative for the decision: on start or
recovery the actor reads `confirmed` first. If `confirmed` exists and names
this run and the current configuration digest, the run is committed; if it
exists but names another run or digest, the actor refuses and records why. If
it is absent, the run is not committed, whatever `state.json` says. A missing or
unparsable `state.json` with no `confirmed` is treated as an uncommitted run
and rolled back. Rollback before the commit point therefore needs to revoke
only `allow-start`, which is its first action.

### R2. Mechanically one owner on the host

- The actor holds an exclusive `flock` on `/run/docker-engine-guard/owner.lock`
  for its whole life, acquired non-blocking; failure to acquire is a refusal,
  so two actors can never run.
- There is ONE actor unit, `docker-engine-transition.service` (not a
  template), and one run id at a time, recorded in
  `/var/lib/docker-engine-guard/current-run`. The controller never allocates a
  new run while `current-run` names a run whose terminal state is not
  `confirmed`, `rolled-back` or an acknowledged `rollback-partial` whose repair
  has been verified; it RESUMES that run instead (rerunning the actor in
  recovery mode). An acknowledgment of `rollback-partial` permits an operator
  to repair; it never makes a new run eligible until a verification pass shows
  no Docker process, job, rule, interface or permission remains.
- Boot recovery is the same unit started with `--recover`: it acquires the same
  lock, and in recovery mode it performs only rollback phases (or, after the
  commit point, confirmation finalization). It never performs a forward phase,
  so it never waits on a Docker unit, and its `Before=` the three units cannot
  deadlock.

### R3. Liveness the actor cannot lose

- `Type=notify`, `NotifyAccess=main`, `WatchdogSec=60`; the actor sends
  `WATCHDOG=1` from its main loop and is killed and restarted by systemd if it
  stops making progress (a hang, a SIGSTOP, a blocking call).
- `Restart=always`, `RestartSec=5`, and `StartLimitIntervalSec=0` in `[Unit]`
  so systemd never gives up on it. Every external command runs as a
  subprocess with its own timeout; no call blocks unbounded.
- `ExecStart` exits 0 only after recording a terminal state (`confirmed`,
  `rolled-back`, `rollback-partial`) and non-zero otherwise; `Restart=always`
  also covers clean exits by a signal. `SuccessExitStatus=` is not widened.
- Restart semantics: an actor restarted in a FORWARD phase (`starting`,
  `canary`, `observing`, `awaiting-confirmation`) without `confirmed` rolls
  back; it never resumes the forward phase. Restarted in rollback, it resumes
  at the first rollback phase whose POSTCONDITION does not hold now (each phase
  has a re-checkable postcondition, so state recorded before a reboot is
  re-verified, not trusted). Restarted after the commit point, it finishes
  confirmation.
- Each rollback phase runs inside its own exception handler: an exception is
  recorded in `state.json` with the phase name and the actor proceeds to the
  next phase, exactly as for a deadline overrun. A phase that keeps failing
  ends the run `rollback-partial` naming it, with every later phase attempted.
- The overall deadline is an absolute wall-clock instant recorded at arming
  and never extended by a restart, a resume or a reboot.
- The invariant for an actor that never starts: `allow-start` is created by the
  actor itself as the first act of the `starting` phase, after the lock and
  the state file exist, so an actor that fails before that leaves no
  permission at all.
- Acceptance adds: a hung actor (SIGSTOP), repeated crash in rollback phase 4
  (must end `rollback-partial` naming phase 4 with phases 5-7 done), SIGTERM
  and SIGHUP, start-limit exhaustion, failure before the first state write,
  kills between every operation inside confirmation finalization, two
  concurrent controller starts, a controller retry during rollback, and a
  reboot at each phase.

### R4. Rollback ordering, revised

1. remove `allow-start`, then stop `docker.socket` at once (a listening socket
   would otherwise keep re-triggering condition-skipped starts);
2. restore each family's FORWARD policy if it differs from the snapshot;
3. cancel any queued start job for the three units (`systemctl cancel`), then
   kill by cgroup (`systemctl kill --kill-whom=all --signal=SIGKILL` on
   `docker.service`, `containerd.service`, `fabro-sandbox.slice`), then a
   bounded stop; verify no process remains in those cgroups and no job is
   queued. k3s processes are in `k3s-agent.service` and the kubepods slices
   (measured: every k3s shim on gmktec is in `k3s-agent.service`), so none is
   reachable;
4-7. firewall footprint, interfaces, sysctls, final record, as in revision 3,
   each phase in its own exception handler.

The firewall comparison set is scoped so a reconciler's healthy churn is
never mistaken for Docker's footprint or for a fault: built-in chain policies
of all chains in both families; the built-in `INPUT`, `FORWARD`, `OUTPUT`,
`PREROUTING` and `POSTROUTING` chains' own rules; the `ts-*` chains' contents.
Never the contents of a chain a reconciler owns (`KUBE-*`, `FLANNEL-*`), which
kube-router edits per pod. Whitespace is canonicalized identically in snapshot
and current (hp shows a double space inside an `nfacct` rule), and the
`DOCKER` chain is handled per table (filter and nat both have one).

### R5. The start-condition proof that can actually return a hit

1. Before touching packages, prove the MECHANISM on this host: install a
   throwaway unit `docker-engine-guard-probe.service` (`ExecStart=/bin/true`)
   with the identical two-line `ConditionPathExists=|` drop-in layout; start it
   and require `ConditionResult=no`, `ActiveState=inactive` and no
   `ExecMainStartTimestamp`; create a test permission path, start it again and
   require it to run; remove the probe and the test path.
2. Before `dpkg -i`, prove the REAL drop-ins will load: extract the audited
   `.deb` files' unit files into a scratch root, place the drop-ins beside
   them, and require `systemd-analyze verify --root=<scratch>` to pass for all
   three units; check each drop-in's exact path
   (`/etc/systemd/system/<unit>.d/50-docker-engine-guard.conf`, mode 0644).
3. After `dpkg -i`: `systemctl cat` shows the drop-in for each unit;
   `ConditionResult=no`, `ActiveState=inactive` and no
   `ExecMainStartTimestamp` on both services; `docker.socket` holds no socket
   (`ss -lx`); and the journal since the install holds a "condition ... was
   not met" skip for each unit the postinst tried to start. That journal line
   is the positive control that the gate fired.

### R6. A package fence that holds the lock it relies on

- The role takes the dpkg FRONTEND lock itself (a small helper holding an
  `fcntl` write lock on `/var/lib/dpkg/lock-frontend`, which is the lock apt
  and unattended-upgrades take) and holds it from the audit through the
  install. `dpkg -i` runs under it with `DPKG_FRONTEND_LOCKED=1`, the
  documented way for a frontend that already holds the lock to call dpkg. No
  apt, packagekit or unattended-upgrades operation can start in between.
- Under the lock and before mutation: refuse unless `dpkg --audit` is empty and
  no trigger is pending (`/var/lib/dpkg/triggers/Unincorp` empty); re-read the
  installed versions of every dependency the audit relied on and refuse if any
  changed since the audit.
- The `.deb` files are downloaded before the lock (a download changes no dpkg
  state), and each file's SHA256 must equal the `SHA256:` field of the
  `Packages` index entry for that package and version (`apt-cache show
  <pkg>=<ver>`), and its control `Version:` must equal the allowlist. The
  maintainer-script digests and the allowlist of (package, version) pairs are
  committed in the role and reviewed before any apply.
- The direct `dpkg -i` path runs dpkg's own triggers (the systemd unit-directory
  trigger runs a daemon-reload; man-db) and no apt hook; dpkg configuration
  under `/etc/dpkg/dpkg.cfg.d` is compared with committed digests.
- Recovery of an interrupted install runs `dpkg --configure` on THIS run's
  packages only, never `--configure -a`; any other pending package refuses.
- The apt timers: their prior state (enabled and active, per timer) is
  persisted before they are stopped; a host-side transient timer restores
  exactly that prior state after 30 minutes unless the role restores it first,
  so a lost controller cannot leave security updates paused. A timer that was
  inactive before is not started.

### R7. Provenance written before mutation

The guard records `intended` (the run id, the audited package set with
versions and SHA256s, and the configuration digest) BEFORE the first package
mutation, and the run's states are: `prepared` (guard directory and
configuration written, no package touched), `installing`, `installed-inert`,
`running` (the actor's forward phases), `rolling-back`, `rollback-partial`,
`committed` (= `confirmed` exists), `confirmed` (finalized). A later run
reconciles the actual package and configuration state against `intended`: a
partial install of exactly the intended set resumes; anything outside it is
foreign and refused, never erased.

### R8. Probes, corrected

- Node Ready through the node-status credential's authorized read of the
  node's own STATUS subresource (`get --raw
  /api/v1/nodes/<node>/status`); the committed grant is `get`/`patch` on
  `nodes/status` for that node only, so no other read is attempted with it.
- Cross-node DNS: measured 2026-10-15, CoreDNS is one replica on poweredge
  (`10.42.0.88`) behind `kube-dns` `10.43.0.10`. The preflight re-reads that
  through a read delegated to the k3s server (`k3s kubectl get pods -n
  kube-system -o wide` there, the fleet guard's allowed read) and requires
  every backend to be on another node; the probe is then a DNS query to
  `10.43.0.10` from the pod's namespace, sent and parsed by a host Python
  script (no resolver file is used, so the pod namespace's missing resolver
  does not matter).
- External HTTPS from the pod namespace connects to an address resolved on the
  host first and sends SNI explicitly, to an endpoint with no per-hour quota
  (an Ubuntu archive mirror `HEAD`), not the GitHub API (60 per hour
  unauthenticated). The canary's egress uses the same endpoint.
- A failed sample is re-probed once immediately and counts only if it fails
  twice; every failure is recorded with the probe and its error so an operator
  can tell "Docker broke the pod network" from "CoreDNS restarted".
- The resync window is derived from the effective intervals recorded with
  their source (kube-proxy's `iptables-sync-period`, kube-router's
  `iptables-sync-period` as k3s passes them, flannel's reconcile), never from
  defaults alone, plus two minutes.
- Controller freshness: at the END of the window the actor writes a
  challenge (a random nonce, the run id, the time). The controller runs its
  probes (a new Tailscale SSH session, the LLM `/health`, and a LAN-fallback
  login to gmktec through poweredge) only after reading that challenge, and
  answers with the nonce; the actor accepts an answer only for the current
  challenge and within 120 seconds of issuing it. An answer from before a
  restart or reboot is never accepted.
- The k3s shim inventory (`/run/containerd/s`, `/run/containerd/runc/k8s.io`)
  and the PIDs of every k3s shim are recorded at preflight; every sample and
  the end of rollback phase 3 require that none disappeared.
- The canary's cgroup is resolved through `systemctl show -p ControlGroup
  fabro-sandbox.slice` (it is `/fabro.slice/fabro-sandbox.slice`, nested),
  never a literal path.

### R9. Exclusive admission during the window

The Docker API is admitted to nobody but the actor until the commit point:
`docker.socket` is mode 0660, group `docker`, and the role refuses unless the
`docker` group has no members. The only container during the guarded window
is the canary, verified by listing containers at every sample; Docker's
built-in `bridge`, `host` and `none` networks are expected, any other network
fails the sample; the expected interfaces are `docker0` and the canary's one
veth pair, identified by the canary's own endpoint. If anything unexpected is
found, the run rolls back and records that its `docker0`-only cleanup may not
cover it (`rollback-partial`), rather than claiming a complete recovery.

### Where the companion work stands

The factory group, the first-install play order, the split of the sandbox
slice role and gmktec's host_vars are carrier `livespec-dev-tooling-2puzjr`,
and the gmktec converge does not start until that carrier is implemented,
reviewed and merged. The stale host record (`gmktec-xubuntu-info` AGENTS.md
still describing the old taint and capacity) is corrected through that
repository before the converge, coordinated with the session that owns its
k3s plan.

## Revision 5 — two short scripts and a repeating dead-man, no long-lived actor

Round 4 (Fable and Codex, independently) found the remaining defects in the
long-lived actor itself: `Restart=always` respawns a finished actor forever;
the watchdog arms only after `READY=1`, which was never specified; a hard crash
inside one rollback phase repeats that phase forever; and controllers
allocating runs are not serialized with the actor. Each fix would add more
protocol to the one component whose job is to be trustworthy. Revision 5
removes that component. Where this section and any earlier section disagree,
this section governs; Mechanism 1 (the start condition), the firewall
footprint rules (Mechanism 4 and R4's comparison scope), the probes (R8), the
package fence (R6, as amended below) and the provenance states (R7) stand.

### F1. The pieces

- `/usr/local/libexec/docker-engine-guard` — ONE executable with three
  subcommands, each SHORT (bounded by per-command timeouts, minutes at most)
  and IDEMPOTENT, each taking the same exclusive `flock` on
  `/run/docker-engine-guard/lock` (waiting at most 60 seconds, then exiting
  non-zero without acting):
  - `start <run>`: under the lock, refuse unless the reservation names `<run>`,
    `rolled-back` and `confirmed` are both absent for it, and the dead-man
    timer for `<run>` is armed; then create `allow-start`, and start
    `containerd.service` then `docker.service` with bounded waits.
  - `confirm <run> <nonce>`: under the lock, refuse unless the current
    challenge for `<run>` carries `<nonce>` and is younger than 120 seconds
    and no rollback has STARTED for `<run>` (`rollback-started` absent); then publish `confirmed` (the commit point,
    R1), stop and disable the dead-man timer, remove `allow-start`. Every step
    after the commit point is idempotent and repeated by any later `confirm`.
  - `rollback <run>`: under the lock, if `confirmed` names `<run>`, exit 0 and
    do nothing (committed runs are never rolled back). Otherwise write
    `rollback-started` for `<run>` first (from then on `confirm` refuses, so a
    run that began rolling back can never be committed), then run EVERY
    rollback step in order, each wrapped in its own `timeout`, each attempted
    whatever the previous one returned: remove `allow-start`; stop
    `docker.socket`; cancel only the queued jobs whose unit is one of the three
    (read from `systemctl list-jobs`, cancelled by job id, never a bare
    `systemctl cancel`); restore each family's FORWARD policy; kill by cgroup
    and stop the three units and `fabro-sandbox.slice`; disable the three
    units (the postinst enabled them); remove Docker's rule footprint; delete
    `docker0` and the canary's veth; compare sysctls. Then re-check ALL the
    postconditions together, after every writer is stopped: no permission,
    socket, process, job or start pending for the three units, both FORWARD
    policies as snapshotted, no Docker rule, no `docker0`, sysctls as
    snapshotted. Write `rolled-back` only if every postcondition holds, else
    write `rollback-partial` naming each failed postcondition. Exit 0 either
    way, having recorded an outcome.

- The DEAD-MAN: a transient timer armed by the role BEFORE `start`, with
  `systemd-run --unit=docker-engine-deadman-<run> --on-active=<N>
  --on-unit-inactive=60 --timer-property=AccuracySec=1s
  --property=TimeoutStartSec=600 docker-engine-guard rollback <run>`. It
  fires at the deadline and then again every 60 seconds after each run
  finishes, forever, until `confirm` stops it. Because `rollback` is
  idempotent and attempts every step on every run, a step that hangs (killed
  by its own `timeout`) or keeps failing cannot stop the later steps, and a
  rollback killed half way is simply repeated a minute later. A `rolled-back`
  outcome makes later firings no-ops; a `rollback-partial` outcome keeps
  retrying, which is what an operator wants while access remains. No process
  needs to stay alive for any of this: there is no watchdog, no READY, no
  restart policy and no state machine to resume.

Why this closes round 4's blockers. Restart loops: there is no long-lived
service to restart. Watchdog: none is needed, because liveness is the timer
firing again, not a process staying healthy. A hard crash or hang in one step:
the next firing starts from the top and every step is attempted with its own
timeout. Serialization: every writer of the shared permission and of the
outcome takes the same lock and checks the other outcome under it, and the
controller's run reservation (F2) is taken under that lock too.

### F2. One run at a time, reserved under the same lock

`docker-engine-guard reserve <run>` (same lock) creates
`/var/lib/docker-engine-guard/run` naming `<run>` only if it is absent or names
a run whose outcome is `rolled-back` or `confirmed`; otherwise it refuses and
prints the holder. The role's FIRST action on the host is `reserve`; every
later subcommand refuses for any other run. Configuration (`daemon.json`
keys, the drop-ins, the probe parameters) is written by the role only after a
successful `reserve`, so a second controller cannot overwrite the first's
configuration without first failing to reserve. A `rollback-partial` run
keeps the reservation until an operator has repaired the host and a
`docker-engine-guard verify <run>` (read-only, same postcondition set as the
end of rollback) passes, which then marks it `rolled-back`.

### F3. Reboot

`allow-start` is on tmpfs and `confirmed` is absent before the commit point,
so after any reboot none of the three units can start (Mechanism 1), Docker's
rules never come back (they are not persisted and no daemon re-creates them),
and `docker0` does not exist. The transient dead-man does not survive the
reboot and does not need to. The units the postinst enabled stay enabled but
condition-skipped until a later run's `rollback` disables them; that is
harmless (a skipped start is not a failure) and is reported.

### F4. Commit point details (Codex round 4, SHOULD-FIX 4)

`confirm` writes `confirmed.tmp` (run id, digest of the role-OWNED daemon keys
parsed and canonicalized, not the file's bytes), fsyncs it, renames it to
`confirmed`, and fsyncs the directory. The moment the rename returns, the run
is committed, even if the directory fsync then fails: a visible marker is never
followed by a rollback; the failure is recorded as a durability warning and
`confirm` is repeated. Both permissions exist briefly between the rename and
the removal of `allow-start`; that overlap is safe because the run is already
committed. After the commit point Docker is an ordinary enabled service: a
later converge that finds `confirmed` and a different OWNED-keys digest treats
it as a post-commit reconfiguration (write the keys, record a pending drained
restart, as the slice role does), never as a guarded transition and never as a
refusal; the slice role's re-serialization of `daemon.json` changes no owned
key and so no digest.

### F5. The condition proof, with instruments that can return a hit

1. The probe unit is given its OWN test permission path
   (`/run/docker-engine-guard/probe-allow`), never `allow-start`; its two-line
   OR condition names that path and the real `confirmed` path. After the
   probe, the role asserts `allow-start` and the probe path are both absent
   immediately before `dpkg -i`.
2. Before `dpkg -i`, `systemctl --root=<scratch> cat <unit>` (systemd 259) on a
   scratch root holding the audited packages' unit files plus the drop-ins must
   list the drop-in for each of the three units and contain both
   `ConditionPathExists=|` lines with the exact paths.
   (`systemd-analyze verify --root` is not used: it fails on a scratch root
   without the targets and executables, and it is silent about a misplaced
   drop-in.)
3. After `dpkg -i`: `systemctl cat` lists the drop-in for each unit,
   `ConditionResult=no` and no `ExecMainStartTimestamp` on both services, no
   socket for `docker.socket`, and the journal since the install holds, for
   each unit the postinst tried to start, systemd's message for unmet
   trigger conditions ("... was skipped because no trigger condition checks
   were met"), which is the text systemd writes for `|` conditions.

### F6. The package fence, amended (Fable round 4, SHOULD-FIX 7; Codex round 4, SHOULD-FIX 6)

- The lock-holding helper runs as a transient unit (`systemd-run --wait
  --collect --property=RuntimeMaxSec=<audit+install budget plus margin>`), so
  its lifetime is owned by systemd, not by the controller's SSH session; the
  role stops it in an `always` block. If it expires during the install, `dpkg`
  still holds `/var/lib/dpkg/lock` itself, so apt sees an ordinary lock
  failure, not a concurrent write.
- The apt timers are restored by the role when the guarded run reaches an
  outcome; the host-side transient restore is a backstop only, armed with a
  deadline of the worst-case run (install budget plus `N` plus the first
  rollback) plus 30 minutes, and it starts only timers that were active before.
- A fresh transaction requires an empty `dpkg --audit` and no pending trigger;
  recovering THIS run's interrupted install is a separate branch that allows
  exactly this run's packages in `half-installed`/`unpacked`/
  `half-configured`/`triggers-pending` and runs `dpkg --configure` on them
  only. `/etc/dpkg/dpkg.cfg` and `/etc/dpkg/dpkg.cfg.d/*` are digest-checked.
- There is no systemd unit-directory dpkg trigger on this OS; the role runs an
  explicit `systemctl daemon-reload` after `dpkg -i` and before the post-install
  checks.

### F7. Admission and collision checks (Codex round 4, SHOULD-FIX 8; Fable NOTE 11)

- Before `reserve`: refuse if any account has `docker` as its primary group or
  is a member of it, and state the trust assumption that root-run services on
  this host do not use the Docker API during the window (none exists today: no
  Docker client is installed).
- Refuse if `172.17.0.0/16` overlaps any address on any interface, any route in
  any routing table (`ip route show table all`, both families as applicable),
  the tailnet range or the cluster's pod and service CIDRs.
- CoreDNS is not pinned to a node: the cross-node property of the DNS probe is
  read at preflight AND again at the end of the window (a read delegated to the
  k3s server); if it is no longer cross-node, the probe result is reported as
  "same-node" and does not count toward confirmation.
- k3s's resync settings are read from `/etc/rancher/k3s/config.yaml` and its
  drop-ins (root-only), not from the unit's `ExecStart`.

### F8. k3s witness (Codex round 4, SHOULD-FIX 7)

The shim-survival assertion is dropped: CI pods legitimately come and go. What
is asserted instead is what Docker cleanup could actually damage: every kill
and stop targets only `docker.service`, `containerd.service`,
`docker.socket` and `fabro-sandbox.slice`; `k3s-agent.service` keeps its
`containerd` process (same PID before and after the window); `/run/containerd/s`
and `/run/containerd/runc/k8s.io` still exist; and the Node stays Ready.

### F9. Acceptance, restated for this shape

On the disposable VM: kill or hang each rollback step (each must be timed out
and the later steps still run in the same firing); kill a firing half way (the
next firing completes it); run `confirm` and the deadline firing concurrently
in both orders (exactly one outcome, never both); start a second controller
while a run is reserved (refused); reboot before the commit point (no unit
starts, no rule exists); fail the directory fsync after rename (committed, not
rolled back). On gmktec, only after the LAN fallback is proven there.

## Revision 6 — every lock holder externally bounded, one observer, a full lifecycle per run

Round 5 (Fable and Codex, independently) confirmed the repeating dead-man is
mechanically sound on systemd 259 and that F5's instruments now return hits,
and found these gaps, all answered here. Where this section and an earlier one
disagree, this section governs.

### G1. Every operation is a bounded transient oneshot unit (Codex B1, Fable SF2)

Every guard subcommand runs ONLY as its own transient unit, never as a bare
child of a controller's SSH session:

```
systemd-run --unit=docker-engine-guard-<op>-<run>-<seq> --wait --collect \
  --property=Type=oneshot --property=TimeoutStartSec=<op budget> \
  --property=TimeoutStopSec=30 --property=KillMode=control-group \
  --property=SendSIGKILL=yes /usr/local/libexec/docker-engine-guard <op> <run> ...
```

`Type=oneshot` makes `TimeoutStartSec` bound the whole execution; on expiry
systemd sends SIGTERM to the whole control group and SIGKILL after 30 s, so a
stalled guard (including a SIGSTOP'd one) and every child of it are gone within
budget plus 30 s, and the `flock` on `/run/docker-engine-guard/lock` (a fixed
file created once, never replaced) is released with the process. Budgets:
`reserve` 60 s, `publish` 120 s, `start` 180 s, `observe` W plus 300 s,
`confirm` 120 s, `rollback` 600 s, `release` 60 s. The dead-man's service is
the same shape (`Type=oneshot`, `TimeoutStartSec=600`). The recovery-delay
bound is therefore explicit: at most one in-flight operation's budget plus 30
s, plus the dead-man's 60-second interval, plus one rollback budget.

### G2. A run's lifecycle, every transition under the lock (Codex B2, Fable SF5)

Each run has a single `phase` field in `/var/lib/docker-engine-guard/runs/<run>/`
and transitions only forward, only under the lock, with the run's absolute
deadline (wall clock plus the boot id it was set under) checked at every
decision:

`reserved` → `published` → `started` → `observed` → `committed` → `confirmed`
with `rolling-back` → `rolled-back` | `rollback-partial` reachable from
`reserved` through `observed` (never from `committed` or `confirmed`).

- `start` requires exactly `published` and an unexpired deadline on the same
  boot; it moves to `started` BEFORE creating `allow-start`, so a duplicate or
  delayed `start` finds `started` and refuses. It never runs on a run that is
  `rolling-back`, `rolled-back` or `rollback-partial`.
- `confirm` first checks for `confirmed`/`committed` naming this run: if
  present it only FINISHES (no challenge needed). Otherwise it requires
  `observed`, a passing evidence record (G4), the matching nonce of a challenge
  issued on this boot and younger than 120 s, and an unexpired deadline; then
  it publishes the marker (commit point), sets `committed`, removes
  `allow-start`, ENABLES the three units, stops the dead-man timer and moves to
  `confirmed`.
- `rollback` sets `rolling-back` first (from then on neither `start` nor
  `confirm` can act), then runs the driver (G5). At an expired deadline the
  dead-man's rollback wins at the decision point even if a `confirm` is
  waiting for the lock, because `confirm` re-checks the deadline under the lock.

### G3. All shared writes go through the locked helper (Codex B3, Fable SF3/SF7)

- The controller never writes into place. It uploads per-run inputs (the owned
  `daemon.json` keys, the drop-ins, the probe parameters, the snapshot
  instructions) into `/var/lib/docker-engine-guard/runs/<run>/inputs/`, a
  directory created by `reserve` for that run alone. `publish <run>` (locked)
  verifies the run is `reserved` and is the current reservation, takes the
  snapshot (`before/`, stored in the run directory — its home), installs the
  inputs into place, and moves the run to `published`. A delayed controller of
  an older run cannot write into place: its `publish` refuses, and its uploads
  land only in its own run directory.
- Post-commit configuration changes go through `reconfigure <run>` (locked),
  which requires the run to be the current, `confirmed` one.
- `reserve` refuses while the current run is neither `rolled-back`,
  `confirmed` nor `released`. A controller that finds a run in any other phase
  ATTACHES to it: it runs `rollback <run>` (for any pre-commit phase) or
  `confirm <run>` (for `committed`), then `verify <run>`, then reserves anew.
  A crash after `reserve` and before `publish` leaves a `reserved` run with no
  snapshot; `rollback` on it only releases the reservation (nothing was
  started). A `confirmed` run is `released` by the next `reserve`, so every
  later converge after a confirmation reserves normally.

### G4. One observer, owned and bounded (Codex B4, Fable B1)

`observe <run>` is a bounded oneshot unit that requires `started` and owns the
whole window: it pulls and runs the canary, proves the canary's cgroup and the
slice's limits from the host, proves bridge egress, then samples the host every
15 s over W (R8's probes and F8's witness), re-probing a failed sample once.
It does NOT hold the lock across the window; it takes the lock only to record
progress, and it aborts if the run has left `started`. Its results go to an
evidence record (run id, boot id, configuration digest, window start and end,
every sample) in the run directory. On ANY failed sample it triggers
`rollback <run>` itself (as a separate transient unit) and exits. On success it
removes the canary, issues the challenge (`/run/docker-engine-guard/challenge`,
tmpfs, so a reboot clears it; it carries run id, boot id and nonce) and moves
the run to `observed`. If the controller dies at any point, nothing else is
needed: the dead-man rolls the run back at the deadline. The deadline `N` is
set at `reserve` to cover publish, start, observe and confirm budgets plus
margin.

### G5. A rollback driver that cannot be stuck behind one phase (Codex SF5, Fable SF6)

The rollback executable is a minimal driver that runs each phase as a SEPARATE
child process with its own timeout, and before entering a phase records an
attempt in `runs/<run>/rollback/<phase>.attempts`. A phase whose recorded
attempts reach 3 without a recorded success is skipped on later firings (its
postcondition is still checked at the end and reported), so a parser that
crashes the same way every time can delay the later phases by at most three
firings, not forever. The final all-postconditions check (F1) decides the
outcome. When the outcome is `rolled-back`, the dead-man stops itself
(`systemctl stop` of its own timer unit, never `disable`, which is an error for
a transient unit). When it is `rollback-partial`, the dead-man keeps firing but
only re-runs phases whose postcondition still fails and whose attempt budget is
not exhausted; once every failing phase is exhausted it stops itself and the run
waits for an operator (`verify` after a repair).

### G6. Effective conditions, not text (Codex SF7)

F5's checks are strengthened: before install, the scratch root holds the
packages' unit files plus EVERY drop-in that exists on the host for the three
units (so a pre-existing override is seen), and the role refuses any drop-in
other than its own; after install it reads the manager's parsed condition list
(`systemctl show -p Conditions` parsed through `busctl` / the D-Bus `Conditions`
property, which carries type, trigger flag and path) and requires exactly the
two OR conditions with the expected paths; and in a fresh-install branch it
requires `confirmed`, `allow-start` and the probe path all absent immediately
before `dpkg -i`.

### G7. Package fence, remaining items (Codex SF8, Fable NOTE 10)

`dpkg -i` runs inside the lock-holding helper's transient unit on the host
(G1), never from the controller's session. If the helper is killed during the
install, the recovery branch (F6) runs on the next `publish`/`start` attempt
for that run and only for this run's packages; interrupted trigger processing
(`triggers-awaited`/`triggers-pending` on this run's packages, or on the
handlers they activate, systemd and man-db being the measured ones) is
completed by `dpkg --triggers-only` restricted to those packages, and anything
else pending refuses.

### G8. Acceptance additions

On the disposable VM, in addition to F9: SIGSTOP of each subcommand while it
holds the lock (killed within its budget plus 30 s, lock released); repeated
parent death of the rollback driver at the same phase (that phase is skipped
after 3 attempts and the later phases run); a delayed controller `publish`
after a newer reservation (refused); a duplicate `start` after rollback began
(refused); a `confirm` arriving after the deadline (refused, rollback wins); a
`confirm` retried after a crash past the commit point and after 120 s
(finishes); a failed observation sample (rollback triggered by `observe`); a
reboot after `reserve` and after `started` (no unit starts, the next controller
attaches and rolls back).

## Revision 7 — remove the flexibility that kept creating races

Round 6 found the remaining problems in features this design did not need:
concurrent controllers, automatic takeover of another controller's run, an
unfenced observer, a guarded transition re-entered after a confirmed install,
and a deadline that started before the network-inert install. Revision 7
removes those features and states the constraints mechanically. Where this
section and an earlier one disagree, this section governs.

### H1. Single-flight, no automatic takeover (Codex round 6 SF3)

The role refuses to start any guarded operation unless, under the lock: no run
is in a non-terminal phase, and none of the guard's units
(`docker-engine-guard-*.service`, the dead-man timer and its service) is active
or activating. It never attaches to, rolls back or takes over another run. An
unfinished run is recovered only by an explicit operator invocation naming it
(`-e docker_engine_recover=<run>`), which dispatches marker-first (H5). A second
controller arriving during a healthy run is therefore refused with the run id,
its phase and its deadline, and changes nothing.

### H2. The observer is a singleton and is fenced by rollback (Codex round 6 B1)

- `observe` runs only as the fixed unit `docker-engine-guard-observe.service`;
  systemd refuses a second activation of an active unit, so two observers
  cannot run. It claims the run under the lock before doing anything
  (`started` → `observing`), so an `observe` for a run that has left `started`
  refuses.
- `rollback`'s first actions after `rolling-back` are: stop
  `docker-engine-guard-observe.service` and `docker-engine-guard-start.service`
  (control-group kill, SIGKILL after 10 s) and wait for both to be inactive;
  only then revoke `allow-start` and stop Docker. A stopped observer has no
  pending request left to submit, so it cannot touch a later run's daemon.
  `reserve` (H1) also requires both units inactive.
- The observer does not wait for the rollback it triggers on a failed sample:
  it writes the failure to its evidence record, starts `rollback <run>` as its
  own transient unit with `--no-block`, and exits. Rollback's stop of the
  observer unit is then a no-op, and neither waits on the other.
- The observer never takes the lock while it holds a Docker API request; it
  takes the lock only between requests to check that the run is still
  `observing` and to record progress.

### H3. After a confirmation, the guarded transition is closed (Codex round 6 B2)

The guarded transition exists to install Docker once. `reserve` refuses
whenever `/var/lib/docker-engine-guard/confirmed` exists. Every later converge
on a confirmed host takes the post-commit path only: validate the role-owned
`daemon.json` keys (by the canonical owned-keys digest), the drop-ins and the
units; and if a change is required, apply it through `reconfigure` (locked,
budget 120 s), which writes the owned keys and records a pending drained
restart exactly as the slice role does, and never removes or rewrites the
`confirmed` marker. A no-op converge reserves nothing and ends `ok`. The
`release` subcommand is removed.

### H4. The deadline starts at arming, after the inert install (Codex round 6 SF4/SF5)

The executable sequence is:

1. `reserve` (no deadline yet).
2. `publish`: phase `publishing`; take the snapshot (stored in the run
   directory); install the inputs; run the fenced, audited package transaction
   (inert by Mechanism 1); verify F5/G6; phase `published`. An interrupted
   `publish` leaves the run `publishing` with its intended package set and
   snapshot recorded; the operator's recovery invocation re-runs `publish` for
   that run (allowed only from `publishing`, idempotent, resuming the package
   transaction through the recovery branch for exactly the intended set) or
   rolls it back. The snapshot is taken once, before the first package
   mutation, and never replaced by a later one.
3. `arm`: under the lock, record the deadline as a boot id plus a
   `CLOCK_MONOTONIC` instant (`now + N`), and arm the dead-man with
   `--on-active=` equal to the remaining interval (recomputed from the
   monotonic clock at the moment of arming) plus the 60-second repeat; phase
   `armed`. A wall-clock timestamp is recorded for reports only.
4. `start` (from `armed`, deadline not passed, same boot), `observe`,
   `confirm`, as in G2 with H2.

Every decision compares the monotonic clock against the recorded deadline on
the recorded boot; a different boot id means the deadline has passed.

### H5. Recovery reads the marker before the phase (Codex round 6 SF6)

Every dispatch (rollback, confirm, the operator's recover) first reads
`confirmed`. If it names the run, the run is committed whatever the phase says:
recovery finishes confirmation (G2's steps after the commit point, each
idempotent) and then validates the committed installation (units enabled and
running, permission present, owned keys matching); it never runs the
rollback verifier. If the marker is absent, the run is uncommitted whatever the
phase says (including a recorded `committed` after a failed directory fsync and
a reboot): it is rolled back, and only the rollback path uses the rollback
verifier.

### H6. Every bound stated (Codex round 6 SF7)

- Budgets (`TimeoutStartSec`, oneshot, control-group kill, SIGKILL after 30 s):
  `reserve` 60 s, `publish` 1800 s (install included), `arm` 60 s,
  `start` 180 s, `observe` W + 300 s, `confirm` 120 s, `rollback` 900 s,
  `verify` 120 s, `reconfigure` 120 s.
- Each rollback phase child runs under `timeout -k 10 <phase budget>`, and the
  phase budgets sum to 600 s, leaving 300 s of the rollback budget for the lock
  wait and the final all-postconditions check.
- The lock file descriptor is opened close-on-exec, so no child inherits it.
- Before entering a phase the driver durably records the attempt (write,
  fsync, rename); a phase's success record is cleared whenever the final check
  finds its postcondition failing again, so a postcondition that regresses
  becomes eligible for repair.
- The recovery bound holds under the process-failure model (killed, hung or
  crashing processes); it is not claimed for kernel or storage failure.

### H7. Acceptance additions

Two consecutive no-op converges on a confirmed host (no reservation, no
change); a post-commit `reconfigure` and its interruption; a second controller
during each phase of a healthy run (refused, run unaffected); a paused observer
just before canary creation, then rollback, then a resumed observer (it is
dead); duplicate `observe` (refused); a failed sample while the observer exits
(rollback runs, no deadlock); a delayed `arm` (the timer fires at the recorded
deadline, not later); a crash between the commit rename and the phase update,
and a reboot after a failed directory fsync (each dispatched by the marker).

## Revision 8 — admission and dispatch, stated as tables

Round 7 (Codex) found that two revision-7 rules, read literally, refused the
owning run's own work: H1's admission predicate blocked `publish` and `start`
of the run it had just admitted, and H5's marker-first rule sent every first
`confirm` to rollback. Revision 8 replaces H1's predicate and H5's dispatch
with the tables below; everything else in H1-H7 stands.

### I1. Admission of a NEW reservation (replaces H1's predicate)

`reserve <run>` succeeds, under the lock, only if ALL hold; the reserving
invocation's own unit is excluded from every check:

| check | requirement |
| --- | --- |
| `confirmed` marker | absent (H3) |
| current reservation | none, or one whose run is `rolled-back` |
| guard units | `docker-engine-guard-start.service`, `docker-engine-guard-observe.service`, the dead-man timer and its service, and any other `docker-engine-guard-*.service` except this invocation's: each `inactive` (not active, activating, deactivating or reloading), with no queued job |
| docker group | no account has `docker` as primary or supplementary group (when the group exists) |

A refused `reserve` names the holding run, its phase and its deadline, and
changes nothing. That is the whole of single-flight: a second controller cannot
reserve. It does not apply to operations on the CURRENT run.

### I2. Operations on the CURRENT run (replaces H5's dispatch)

Every operation below runs under the lock, first checks that `<run>` is the
current reservation (else refuses), then reads the marker, then decides by the
table. "Deadline passed" means the recorded boot id differs or the monotonic
deadline has passed.

| operation | marker names `<run>` | marker absent | marker names another run or is unreadable |
| --- | --- | --- | --- |
| `publish` | refuse | allowed from `reserved` or `publishing` (resume of an interrupted inert install, H4) | refuse |
| `arm` | refuse | allowed from `published` | refuse |
| `start` | refuse | allowed from `armed`, deadline not passed | refuse |
| `observe` | refuse | allowed from `started`, deadline not passed | refuse |
| `confirm` | FINISH: idempotent post-commit steps, then committed validation | allowed from `observed` with passing evidence, a current-boot challenge younger than 120 s with the matching nonce, and deadline not passed: COMMIT then finish | refuse |
| `rollback` (dead-man, observer, operator) | no-op, exit 0 | allowed from every pre-commit phase: roll back (a run whose phase reads `committed` with no marker is rolled back; permission is never recreated from a phase) | refuse and report |
| `recover` (operator) | as `confirm` FINISH | `publishing`: resume `publish`; any other pre-commit phase: `rollback` | refuse and report |

The marker read and the decision happen under one lock acquisition.

### I3. Fixed unit identities (Codex round 7 SF3)

`start` runs only as `docker-engine-guard-start.service` and `observe` only as
`docker-engine-guard-observe.service` (fixed names; systemd refuses a second
activation). Every other operation keeps a per-invocation name. Admission (I1),
rollback's stop (H2) and acceptance use these same identities, and
"quiescent" means `inactive` with no queued job.

### I4. Runtime directory and post-install admission (Codex round 7 SF4)

- Every helper first ensures `/run/docker-engine-guard` exists (mode 0700,
  root) with `mkdir -p` and opens `lock` with `O_CREAT` and close-on-exec,
  never unlinking or replacing it; after a reboot the first helper creates them.
- The docker-group check of I1 is repeated by `arm`, after the install has
  created the `docker` group and before any permission is granted; `arm`
  refuses (and the run is rolled back) if any account is in the group.

### I5. Acceptance additions

The ordinary successful sequence end to end (reserve, publish, arm, start,
observe, first confirm commits); an interrupted inert publish resumed by
`recover`; a deadline rollback while the observer is active; a second
controller's `reserve` during each phase (refused, run unaffected); and every
row of I2 exercised once.

---

## Implementation rider

Recorded on `livespec-dev-tooling-xxfqqr` on 2026-10-15T10:05:25Z, verbatim:

> Rider, plan bd-ib-fyozyd (session petri-factory-on-gmktec), 2026-10-15. BINDING implementation scope.
> 
> Design status: revision 8 of research 002 (livespec-orchestrator-beads-fabro, plan/petri-factory-on-gmktec/research/002-docker-engine-dead-man-design-2026-10-15.md, merged by PR 3033) passed independent round-8 review with NO-BLOCKERS from both Codex and Fable. The reviews are in that plan's 002-reviews directory (review-round8-codex.md, review-round8-fable.md). Every finding below fails toward a refusal or a rollback, never a lockout, so each is carried as an implementation rider rather than another design revision:
> 
> 1. A Restart= respawn does NOT re-evaluate ConditionPathExists on systemd 259 (auto-restart states map to activating, and unit_start skips the condition test there). The rollback's explicit stop of docker.socket before docker.service is therefore load-bearing; say so in the role and add a respawn test.
> 2. The dead-man's own service needs TimeoutStartSec at least the 900 s rollback budget (today 600 s), so the primary rollback path is not killed before its final postcondition check.
> 3. start must verify the dead-man timer is live; arm must be idempotent against an existing timer unit.
> 4. A rollback from the publishing phase must not strand later runs: recovery must not be keyed only to the run id, and the next publish must handle a non-empty dpkg --audit left by that rollback.
> 5. Controller-observed failures trigger rollback (role-side rescue), and the challenge is re-issued rather than reused.
> 6. Read effective conditions through busctl (D-Bus), not systemctl show -p Conditions, which renders unprintable on gmktec's systemd 259.
> 7. Tolerate the fleet's sandbox_storage drop-ins (present on hp, absent on gmktec) instead of refusing on them.
> 8. recover must state how it delegates to the locked helper and carry an explicit lifetime if it is itself a helper.
> 9. Classify a failed dead-man service in admission, and add --collect to the dead-man recipe; give verify and reconfigure explicit dispatch rows; after commit, FINISH must start (not only enable) the units.
> 
> Convergence gates, unchanged: no converge on gmktec until the LAN SSH fallback is applied and demonstrated there, the attended converge is announced to gitops-fleet-capacity-monitoring and the k3s sessions first, and the disposable-host acceptance test has passed.

