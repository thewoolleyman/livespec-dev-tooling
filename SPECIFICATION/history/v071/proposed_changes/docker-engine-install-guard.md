---
topic: docker-engine-install-guard
author: claude-opus-5-5
created_at: 2026-10-15T22:06:01Z
---

## Proposal: Specify the Docker engine install guard in non-functional-requirements.md

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- tests/heading-coverage.json

### Summary

Adds one new section, `## Docker engine install guard`, to `SPECIFICATION/non-functional-requirements.md`, immediately after §"Fabro factory host provisioning". It states the guard that installs the Docker engine on a k3s-and-Tailscale factory host behind a dead-man rollback: the single-flight reservation under one lock, the phase set and the operation-by-marker dispatch table, the boot-scoped monotonic deadline, the dead-man timer, start, observe and the challenge, the commit point, the post-commit path, the rollback driver, the host actions, the package fence, the preflight, the probes and every bound.

### Motivation

The guard was designed in plan petri-factory-on-gmktec (livespec-orchestrator-beads-fabro epic bd-ib-fyozyd) through eight review rounds; revision 8 returned NO-BLOCKERS from both Codex and Fable, and the design is copied verbatim into this repository at `docs/docker-engine-guard-design.md`. Its executable was regroomed into six factory-safe work-items (livespec-dev-tooling-ubpufs, -uhu6lm, -4dqyxj, -3ieder, -mxp5ds and -bfzrq7), each referencing §"Fabro factory host provisioning". That section governs only the play, the host_vars, one instance per mapping, the sandbox envelope and HOST_VARS.md, so nothing ratified governs the guard's lock, admission, lifecycle, dead-man rollback, firewall footprint, package fence or probes, and every child would fail the factory's Definition-of-Done gate. The coordinator (session gitops-fleet-capacity-monitoring) confirmed the gap with a BLOCK verdict on ubpufs's Definition of Done and ruled spec-first. This proposal distils revisions 5 to 8 and the binding nine-point rider recorded on livespec-dev-tooling-xxfqqr into normative clauses, so that every assertion of the six children traces to a clause under one H2. It adds no behaviour that the reviewed design does not already require; where the rider settled a value (the dead-man's 900-second service budget, --collect, busctl conditions, the sandbox_storage drop-ins, a failed guard unit refusing admission, FINISH starting the units, recover's budget and route through the locked helper), the clause states the settled value.

### Proposed Changes

Insert the following section into `SPECIFICATION/non-functional-requirements.md` immediately after §"Fabro factory host provisioning" (that is, at the end of the file, after its "Documented beside the values" paragraph):

> ## Docker engine install guard
>
> **Scope.** This section governs the Docker engine install guard: the executable `/usr/local/libexec/docker-engine-guard` and the role steps that drive it. The guard installs the Docker engine on a factory host that already runs k3s and Tailscale, without risking that host's network access. A *run* is one attempt to install and commit the engine. Durable state lives under `/var/lib/docker-engine-guard`; runtime state lives under `/run/docker-engine-guard`, which is tmpfs and is cleared by a reboot. The *guarded units* are `docker.service`, `docker.socket` and `containerd.service`. The *start permission* is the file `/run/docker-engine-guard/allow-start`, and the *commit marker* is the file `/var/lib/docker-engine-guard/confirmed`. The guarded transition exists to install the engine once: after a run has committed, every later converge on that host takes the post-commit path. The guarded transition applies only to a host on which none of the guarded units is installed.
>
> **Start condition.** Each guarded unit MUST carry a guard drop-in whose conditions are exactly two OR'd `ConditionPathExists=|` lines, one naming the start permission and one naming the commit marker, so that no guarded unit can start unless a run holds the start permission or a run has committed. The guard MUST read each guarded unit's effective conditions from the service manager through `busctl` (the D-Bus `Conditions` property), and that check MUST pass only when exactly those two OR path conditions are present. The guard MUST accept its own drop-ins and the fleet's `sandbox_storage` drop-ins for `docker.service` and `containerd.service`, and MUST refuse any other drop-in on a guarded unit.
>
> **One run at a time, under one lock.** Every guard operation MUST first ensure that `/run/docker-engine-guard` exists with mode `0700`, owned by root. It MUST then take an exclusive lock on `/run/docker-engine-guard/lock`, opening that file with `O_CREAT` and close-on-exec and never unlinking or replacing it. An operation MUST wait at most 60 seconds for the lock, and MUST exit non-zero without acting when the wait expires. At most one run MUST be a host's current reservation.
>
> `reserve <run>` MUST create a reservation only when all of the following hold under the lock:
>
> - the commit marker is absent;
> - there is no current reservation, or the current reservation's run is `rolled-back`;
> - every guard unit other than the reserving invocation's own unit is `inactive` with no queued job, where the guard units are `docker-engine-guard-start.service`, `docker-engine-guard-observe.service`, every dead-man timer and its service, and every other `docker-engine-guard-*.service`;
> - no account has `docker` as its primary group or as a supplementary group.
>
> A guard unit in the `failed` state is not `inactive`, and the refusal MUST name it. A refused `reserve` MUST print the holding run's id, its phase and its deadline, and MUST change nothing. The guard MUST NOT attach to, roll back or take over another run, except through an operator's `recover` that names that run. Every operation on a run MUST refuse when that run is not the current reservation.
>
> **Phases.** Each run MUST record exactly one phase. The guard MUST write the phase durably (write, fsync, rename, then fsync the directory), and the phase MUST move only forward and only under the lock. The install path's phases are `reserved`, `publishing`, `published`, `armed`, `started`, `observing`, `observed`, `committed` and `confirmed`. The rollback path's phases are `rolling-back`, `rolled-back` and `rollback-partial`. The rollback path MUST be reachable from every phase from `reserved` through `committed` of a run the commit marker does not name, and MUST NOT be reachable from a run the commit marker names. The commit marker decides whether a run is committed, not the phase: a run whose marker is absent is uncommitted whatever its phase reads, including a recorded `committed`.
>
> **Dispatch table.** Every operation on the current run MUST read the commit marker and decide by the following table, in one lock acquisition. "Deadline passed" means that the recorded boot id differs from the current boot id, or that the monotonic deadline has passed.
>
> | operation | marker names the run | marker absent | marker names another run, or is unreadable |
> | --- | --- | --- | --- |
> | `publish` | refuse | allowed from `reserved` or `publishing` | refuse |
> | `arm` | refuse | allowed from `published` | refuse |
> | `start` | refuse | allowed from `armed`, deadline not passed | refuse |
> | `observe` | refuse | allowed from `started`, deadline not passed | refuse |
> | `confirm` | finish | allowed from `observed`, deadline not passed: commit, then finish | refuse |
> | `rollback` | no-op, exit 0 | allowed from every phase from `reserved` through `committed`, and from `rolling-back` and `rollback-partial`; a no-op on `rolled-back` | refuse and report |
> | `recover` | finish | resume `publish` from `publishing`; roll back from any other uncommitted phase | refuse and report |
> | `verify` | refuse | allowed from `rollback-partial` and `rolled-back` | refuse |
> | `reconfigure` | allowed from `confirmed` | refuse | refuse |
>
> **Deadline.** `arm` MUST record the run's deadline as the current boot id plus a `CLOCK_MONOTONIC` instant N seconds ahead, where N covers the `start`, `observe` and `confirm` budgets plus a margin. `arm` MAY also record a wall-clock time, for reports only. Every operation that checks the deadline MUST treat a deadline recorded under a different boot id as passed.
>
> **Publish.** The controller MUST write a run's inputs (the owned `daemon.json` keys, the drop-ins and the probe parameters) only into that run's `inputs/` directory, and only `publish` MUST install them into place. `publish` MUST move the run to `publishing` before its first package step, and MUST move it to `published` once the package step and the post-install condition check have passed. `publish` MUST take the host snapshot exactly once, before the first package step, and store it in the run's `before/` directory. A `publish` resumed from `publishing` MUST keep that first snapshot. The snapshot MUST hold the output of `iptables-save` and `ip6tables-save` per table without counters, the FORWARD policy of each address family, and the five watched forwarding and bridge-netfilter sysctls.
>
> **Arm and the dead-man.** The package install creates the `docker` group, so `arm` MUST repeat the docker-group check: it MUST refuse, and trigger rollback, when any account is in the group. `arm` MUST arm the run's dead-man as the transient timer `docker-engine-deadman-<run>` through `systemd-run` with `--collect`, with `--on-active` equal to the interval remaining to the deadline (recomputed from the monotonic clock at arming), with `--on-unit-inactive=60`, with `AccuracySec=1s`, and with a service `TimeoutStartSec=900` whose command is `rollback <run>`. `arm` MUST succeed when that timer unit already exists. The dead-man therefore fires at the deadline, and again 60 seconds after each rollback it runs, until `confirm` or a rollback outcome stops it.
>
> **Start.** `start` MUST run only as the fixed unit `docker-engine-guard-start.service`. It MUST refuse when the run's dead-man timer unit is not active. It MUST move the run to `started` before it creates the start permission, so that a duplicate or delayed `start` refuses. It then starts `containerd.service` and then `docker.service`, each with a bounded wait.
>
> **Observe and the challenge.** `observe` MUST run only as the fixed unit `docker-engine-guard-observe.service`, so that the service manager refuses a second observer. It MUST move the run from `started` to `observing` under the lock before its first sample. It MUST stop sampling when a lock-held check finds the run no longer `observing`, and it MUST NOT hold the lock while a Docker API request is outstanding. It samples the host every 15 seconds over the observation window, and records each sample in the run's evidence record. That record carries the run id, the boot id, the configuration digest, and the window's start and end.
>
> On a failed sample, `observe` MUST record the failure in the evidence record, start `rollback <run>` as its own transient unit without waiting for it, and exit. On a passing window, `observe` MUST remove the canary and write a challenge under `/run/docker-engine-guard` that carries the run id, the boot id and a fresh nonce, and then move the run to `observed`. Each passing window's nonce MUST differ from every earlier one.
>
> **Commit.** `confirm` MUST commit only from `observed`, and only with passing evidence, an unexpired deadline, and a challenge that was issued on the current boot, is younger than 120 seconds and carries the matching nonce. A `confirm` that carries an expired or already-used challenge MUST refuse. To commit, `confirm` writes `confirmed.tmp` holding the run id and the canonical digest of the role-owned daemon keys, fsyncs it, renames it to the commit marker, and fsyncs the directory. The run is committed the moment the rename returns. A failed directory fsync after the rename MUST be recorded as a durability warning and MUST leave the run committed.
>
> After committing, `confirm` MUST perform the post-commit steps:
>
> - set `committed`;
> - remove the start permission;
> - enable and start the three guarded units;
> - stop the dead-man timer;
> - move the run to `confirmed`.
>
> A `confirm` for a run the commit marker already names MUST repeat those steps idempotently, without a challenge. After the post-commit steps, `confirm` MUST validate that the three guarded units are enabled and running, that the commit marker is present (after the commit it is the only path the guarded units' start condition can satisfy), and that the owned daemon keys match the marker's digest.
>
> **After the commit.** `reserve` refuses while the commit marker exists, so the guarded transition never runs again on that host. A converge on a committed host MUST validate the owned daemon keys by their digest, the drop-ins and the units. It MUST apply a needed change only through `reconfigure`, which writes the owned daemon keys and records a pending drained restart as §"Fabro factory host provisioning" requires, and which MUST NOT remove or rewrite the commit marker. A converge that needs no change MUST reserve nothing. `verify <run>` MUST re-evaluate the rollback postcondition set read-only, and MUST rewrite `rollback-partial` as `rolled-back` only when every postcondition holds.
>
> **Rollback.** `rollback` on a run not already on the rollback path MUST record `rolling-back` before any other step; a later firing on `rolling-back` or `rollback-partial` MUST keep the recorded phase until it writes its outcome. From the first `rolling-back` on, `start` and `confirm` refuse for that run. It MUST stop `docker-engine-guard-observe.service` and `docker-engine-guard-start.service`, with SIGKILL after 10 seconds, and wait for both to be inactive before it revokes the start permission. The rollback driver then runs its phases in this order:
>
> 1. stop `docker.socket` before `docker.service`;
> 2. cancel the queued jobs of the three guarded units;
> 3. restore each address family's FORWARD policy;
> 4. kill by cgroup, and stop, the guarded units and `fabro-sandbox.slice`;
> 5. disable the three guarded units;
> 6. remove Docker's firewall footprint;
> 7. delete the bridge interfaces;
> 8. compare the sysctls with the snapshot;
> 9. run the final check, which reads every postcondition together after every stop phase.
>
> The *postconditions* are:
>
> - no start permission;
> - no socket, process, queued job or pending start for the guarded units;
> - each FORWARD policy as snapshotted;
> - no Docker rule;
> - no `docker0`;
> - each watched sysctl as snapshotted.
>
> The driver MUST run each phase as a child process under `timeout -k 10` with that phase's budget, and the phase budgets MUST sum to 600 seconds. Before entering a phase, the driver MUST durably record an attempt for it. A phase whose recorded attempts reach three without a recorded success MUST be skipped. A phase that fails, times out or is skipped MUST NOT prevent any later phase from running. The final check MUST clear the success record of every phase whose postcondition it finds failing.
>
> The driver MUST write `rolled-back` only when every postcondition holds; otherwise it MUST write `rollback-partial`, naming each failed postcondition. It exits 0 either way. With a `rolled-back` outcome, the driver MUST stop its own dead-man timer with `systemctl stop`. With a `rollback-partial` outcome, a later firing MUST re-run only the phases whose postcondition fails and whose recorded attempts are under three. Once every failing phase has exhausted its attempts, the driver MUST stop its own dead-man timer, and the run waits for an operator's repair followed by `verify`.
>
> **Host actions.** Every external command the guard runs MUST go through one runner with an explicit timeout. Firewall changes MUST use only the `iptables-nft` commands.
>
> - **Footprint.** Docker's firewall footprint MUST be exactly the rules that are present now and absent from the snapshot and that reference `docker0`, `172.17.0.0/16`, or a chain absent from the snapshot whose name starts with `DOCKER`. Every rule and chain the snapshot contains MUST be excluded from the footprint.
> - **Footprint removal.** Removal MUST issue `iptables -D` and `ip6tables -D` with each rule's full specification, then flush and delete the selected chains. It MUST re-read and repeat, for at most three passes, and MUST report every residual Docker rule.
> - **FORWARD restore.** FORWARD restore MUST issue one `-P FORWARD` per address family, with the policy recorded in the snapshot.
> - **Job cancellation.** Job cancellation MUST issue `systemctl cancel` with the job ids of the queued jobs whose unit is a guarded unit, and never a bare `systemctl cancel`.
> - **Cgroup kill.** The cgroup kill MUST issue `systemctl kill --kill-whom=all --signal=SIGKILL` for `docker.service`, `containerd.service` and `fabro-sandbox.slice`, followed by a bounded `systemctl stop` of those units and `docker.socket`. No kill or stop MUST target any other unit, so `k3s-agent.service` and its containerd are never touched.
> - **Disable.** The disable action MUST disable the three guarded units.
> - **Interfaces.** The interface action MUST delete `docker0` and every veth whose master is `docker0`.
> - **Sysctls.** The sysctl action MUST compare the five watched forwarding and bridge-netfilter values with the snapshot and report each difference.
> - **Postcondition read.** The postcondition read MUST report the state of the permission, sockets, processes, queued jobs, FORWARD policies, Docker rules, `docker0` and sysctls as one record.
>
> **Package fence.** The package step MUST refuse:
>
> - when the simulated transaction installs a package or version outside the committed allowlist, removes a package, or upgrades an installed package;
> - when an installed version the audit relied on has changed since the audit;
> - when a downloaded `.deb`'s SHA256 differs from the archive index, or its maintainer scripts differ from the committed digests;
> - when a host apt hook file or dpkg configuration file differs from its committed digest.
>
> The package step MUST run `dpkg -i` on exactly the audited `.deb` files, with `DPKG_FRONTEND_LOCKED=1` in its environment. It MUST require the post-install `dpkg-query` difference to equal the audited additions. Recovery of an interrupted install MUST run `dpkg --configure` only on this run's `half-installed`, `unpacked` or `half-configured` packages. It MUST complete interrupted triggers with `dpkg --triggers-only`, restricted to packages in a guard run's recorded intended set, so that a rollback from `publishing` never strands a later run. The package step MUST refuse when `dpkg --audit` names a package outside every recorded intended set.
>
> **Preflight.** Before `reserve`, the preflight MUST refuse in each of these cases:
>
> - `172.17.0.0/16` overlaps an address on any interface, a route in any routing table, the tailnet range, or the cluster's pod or service CIDR;
> - any account has `docker` as its primary group or is a member of it;
> - any effective k3s resync interval exceeds five minutes.
>
> The guard MUST read each effective resync interval from `/etc/rancher/k3s/config.yaml` and its drop-ins, and record each with its source. The resync window is the largest of those intervals plus two minutes.
>
> **Probes.** Each sample of the observation window MUST run these probes:
>
> - **Services.** The services probe requires `k3s-agent`, `tailscaled` and every unit in `docker_engine_must_stay_running` to be active.
> - **Node Ready.** The Node Ready probe reads the node's own status through `get --raw /api/v1/nodes/<node>/status`, using the node-status credential.
> - **DNS.** The DNS probe requires every CoreDNS backend to be on another node. That placement is read through the k3s server at the preflight and again at the end of the window, and a same-node result is reported as not counting toward confirmation. The probe sends its query to the kube-dns service address from the pod network namespace, and parses the reply without a resolver file.
> - **API.** The API probe completes a TLS handshake to the Kubernetes API service ClusterIP from the pod network namespace.
> - **HTTPS.** The HTTPS probe connects from the pod network namespace to an address resolved on the host, sends SNI explicitly, and issues a HEAD to an Ubuntu archive mirror.
> - **Sysctls.** The sysctl probe requires the five watched values to equal the snapshot.
> - **k3s witness.** The preflight records the containerd PID of `k3s-agent.service` and the paths `/run/containerd/s` and `/run/containerd/runc/k8s.io`. A sample fails when that PID has changed or either path is missing.
> - **Containers and networks.** The canary's cgroup is resolved through `systemctl show -p ControlGroup fabro-sandbox.slice`. A sample fails when any container other than the canary exists, or when any Docker network other than `bridge`, `host` and `none` exists.
> - **Interfaces.** A sample fails when any interface other than `docker0` and the canary's one veth pair has appeared since the snapshot.
> - **Firewall.** A sample's firewall comparison covers the built-in chain policies of both families, the rules of `INPUT`, `FORWARD`, `OUTPUT`, `PREROUTING` and `POSTROUTING`, and the contents of `ts-*` chains. It skips the contents of `KUBE-*` and `FLANNEL-*` chains.
>
> A failed probe MUST be re-run once immediately, and MUST count as failed only when it fails twice. Every probe failure MUST be recorded with the probe's name and its error.
>
> **Bounds.** Every guard operation MUST run only as its own transient `Type=oneshot` unit, never as a bare child of a controller's session. Each unit's `TimeoutStartSec` is the operation's budget, with a control-group kill and SIGKILL 30 seconds after it. The budgets are:
>
> | operation | budget |
> | --- | --- |
> | `reserve` | 60 s |
> | `publish` | 1800 s, install included |
> | `arm` | 60 s |
> | `start` | 180 s |
> | `observe` | the window plus 300 s |
> | `confirm` | 120 s |
> | `rollback` | 900 s |
> | `verify` | 120 s |
> | `reconfigure` | 120 s |
> | `recover` | 1800 s |
>
> `start` and `observe` use their fixed unit names; every other operation uses a per-invocation unit name. `recover` MUST perform its work through the same locked helper as the other operations. The recovery bound — one in-flight operation's budget plus 30 seconds, plus the dead-man's 60-second interval, plus one rollback budget — is claimed for killed, hung or crashing processes, not for kernel or storage failure.

Add one entry to `tests/heading-coverage.json` for the new heading, as spec-first debt: `spec_root` `SPECIFICATION`, `spec_file` `non-functional-requirements.md`, `heading` `## Docker engine install guard`, `test` `TODO`, `work_item` `livespec-dev-tooling-ubpufs`, and a `reason` acknowledging that a real test is owed at the required tier. Regenerate `tests/heading-coverage-debt.json` mechanically in the same change.

## Proposal: Add acceptance scenarios for the Docker engine install guard

### Target specification files

- SPECIFICATION/scenarios.md
- tests/heading-coverage.json

### Summary

Adds seven Gherkin scenarios to `SPECIFICATION/scenarios.md` for the guard's load-bearing behaviour: single-flight reservation, the live dead-man precondition of start, a deadline from an earlier boot, a late confirm losing to rollback, a marker-named run being finished rather than rolled back, a failing rollback phase not stopping later phases, and recover's two arms.

### Motivation

Per the authoring discipline, load-bearing behaviour is stated as a clause and also as a scenario. These seven scenarios carry the state transitions the coordinator's review named as the guard's minimum content (single-flight under one lock, the dispatch table keyed on operation and marker state, the boot-scoped deadline, start's timer-live check and its started-before-permission ordering, and recover's two arms), each exercisable at the integration tier against the guard's CLI on a fake host.

### Proposed Changes

Append the following scenarios to the end of `SPECIFICATION/scenarios.md`, keeping the file's convention of a blank line before and after every Gherkin keyword line:

> ## Scenario: a second controller cannot reserve the Docker engine install guard while a run is unfinished
>
> Given a factory host whose Docker engine install guard holds a current reservation for run A in phase `observing`
>
> When a second controller invokes `reserve` for run B
>
> Then the reservation MUST be refused
>
> And the refusal MUST print run A's id, its phase and its deadline
>
> And run A's phase, its deadline and its dead-man timer MUST be unchanged
>
> ## Scenario: the Docker engine install guard refuses to start without a live dead-man
>
> Given a run in phase `armed` whose deadline has not passed
>
> And the run's dead-man timer unit is not active
>
> When `start` is invoked for that run
>
> Then `start` MUST refuse
>
> And the start permission MUST NOT be created
>
> ## Scenario: a Docker engine install guard deadline recorded on an earlier boot counts as passed
>
> Given a run in phase `armed` whose deadline was recorded under a boot id that differs from the current boot id
>
> When `start` is invoked for that run
>
> Then `start` MUST refuse because the deadline has passed
>
> And the start permission MUST NOT be created
>
> ## Scenario: a Docker engine install guard confirm that arrives after the deadline loses to the rollback
>
> Given a run in phase `observed` with passing evidence and a current challenge
>
> And the run's deadline has passed
>
> When `confirm` is invoked with the challenge's nonce
>
> Then `confirm` MUST refuse
>
> And the commit marker MUST NOT be written
>
> And a later `rollback` for that run MUST roll it back
>
> ## Scenario: a Docker engine install guard run named by the commit marker is finished, never rolled back
>
> Given a run whose commit marker names it while its recorded phase reads `committed`
>
> When `rollback` is invoked for that run
>
> Then `rollback` MUST exit 0 without acting
>
> When `confirm` is invoked for that run without a challenge
>
> Then `confirm` MUST enable and start the three guarded units, stop the dead-man timer and move the run to `confirmed`
>
> ## Scenario: a Docker engine install guard rollback phase that keeps failing does not stop the later phases
>
> Given a run in phase `rolling-back` whose job-cancellation phase fails on every attempt
>
> When the dead-man fires `rollback` four times
>
> Then every phase after job cancellation MUST run on each firing
>
> And on the fourth firing the job-cancellation phase MUST be skipped, its recorded attempts having reached three
>
> And the outcome MUST be `rollback-partial`, naming each failed postcondition, unless every postcondition holds
>
> ## Scenario: the Docker engine install guard's recover resumes an interrupted publish and rolls back any other uncommitted run
>
> Given a run in phase `publishing` whose commit marker is absent and whose snapshot was already taken
>
> When an operator invokes `recover` for that run
>
> Then `publish` MUST resume for that run and keep the first snapshot
>
> Given a run in phase `started` whose commit marker is absent
>
> When an operator invokes `recover` for that run
>
> Then the run MUST be rolled back

Add one `tests/heading-coverage.json` entry per new scenario heading (`## Scenario: a second controller cannot reserve the Docker engine install guard while a run is unfinished`; `## Scenario: the Docker engine install guard refuses to start without a live dead-man`; `## Scenario: a Docker engine install guard deadline recorded on an earlier boot counts as passed`; `## Scenario: a Docker engine install guard confirm that arrives after the deadline loses to the rollback`; `## Scenario: a Docker engine install guard run named by the commit marker is finished, never rolled back`; `## Scenario: a Docker engine install guard rollback phase that keeps failing does not stop the later phases`; `## Scenario: the Docker engine install guard's recover resumes an interrupted publish and rolls back any other uncommitted run`), each as spec-first debt with `test` `TODO`, `work_item` naming the guard's scenario-coverage work-item `livespec-dev-tooling-4on5pg` (a factory-safe child of plan epic bd-ib-fyozyd that drives the guard CLI end to end against the fake host from `tests/consumer/`, blocked by the six guard children), and a `reason` acknowledging that a real test is owed at the integration tier. Regenerate `tests/heading-coverage-debt.json` mechanically in the same change.
