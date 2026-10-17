# docker_engine acceptance — the fault catalogue

The disposable-VM acceptance that must pass before any `docker_engine`
converge on gmktec-xubuntu. Each case lists the injection and the outcome
that counts as a pass. The source is `docs/docker-engine-guard-design.md`:
§"Acceptance before the gmktec converge", F9, G8, H7, I5, and the
implementation rider (`livespec-dev-tooling-xxfqqr`, 2026-10-15T10:05:25Z).

Every case starts from the `baseline` snapshot (`vm.sh restore baseline`):
a guest prepared by `baseline.sh`, with no Docker package and the stub
`tailscaled`, `k3s-agent` and LLM-health units active.

**Rolled back** means all of the following hold together. No guard
permission exists. No process, job or pending start exists for
`containerd.service`, `docker.service` or `docker.socket`. Both FORWARD
policies match the snapshot. No Docker rule or chain exists in either
family. No `docker0` exists. The watched sysctls match the snapshot. The
k3s, flannel, kube-router and Tailscale chains match their pre-change
state. The run's record says `rolled-back`.

**Confirmed** means all of the following hold together. The commit marker
names the run. The three units are enabled and running. The owned daemon
keys match the marker's digest. FORWARD is still ACCEPT.

Every case also requires that guest SSH (standing in for Tailscale SSH)
answers throughout and at the end.

## Happy paths

| id | injection | pass |
| --- | --- | --- |
| H-01 | none: reserve, publish, arm, start, observe, controller probes, confirm (I5) | confirmed |
| H-02 | a second converge on the confirmed host, then a third (H7) | no reservation, no change, both runs |
| H-03 | a post-commit `reconfigure` with a changed owned key (H7) | the key is written, a drained restart is recorded, the marker is untouched, and no restart happens |
| H-04 | `reconfigure` interrupted mid-write (H7) | the next `reconfigure` completes it; the marker is untouched |

## Rollback driver robustness

| id | injection | pass |
| --- | --- | --- |
| R-01 | kill each rollback phase in turn (F9) | that phase is timed out; the later phases run in the same firing; rolled back |
| R-02 | hang each rollback phase in turn (F9) | the same as R-01 |
| R-03 | kill a dead-man firing halfway (F9) | the next firing completes it; rolled back |
| R-04 | repeatedly kill the rollback driver's parent at the same phase (G8) | that phase is skipped after 3 attempts; the later phases run |
| R-05 | a `Restart=` respawn of docker.service during rollback (rider 1) | no respawn starts the daemon, because docker.socket is stopped first; rolled back |
| R-06 | rollback from the publishing phase (rider 4) | the next run is not stranded; the next publish handles the non-empty `dpkg --audit` |

## Concurrency and races

| id | injection | pass |
| --- | --- | --- |
| C-01 | `confirm` and the deadline firing concurrently, in both orders (F9) | exactly one outcome, never both |
| C-02 | a second controller's `reserve` during each phase of a healthy run (F9, H7, I5) | refused; the run is unaffected |
| C-03 | SIGSTOP each subcommand while it holds the lock (G8) | it is killed within budget plus 30 s; the lock is released |
| C-04 | a delayed `publish` after a newer reservation (G8) | refused |
| C-05 | a duplicate `start` after rollback began (G8) | refused |
| C-06 | `confirm` after the deadline (G8) | refused; the rollback wins |
| C-07 | `confirm` retried after a crash past the commit point, more than 120 s later (G8) | it finishes; confirmed |
| C-08 | duplicate `observe` (H7) | refused |
| C-09 | the observer paused just before canary creation, then rollback, then the observer resumed (H7) | the observer is dead; rolled back |
| C-10 | a delayed `arm` (H7) | the timer fires at the recorded deadline, not later |

## Reboots and durability

| id | injection | pass |
| --- | --- | --- |
| B-01 | reboot before the commit point (F9) | no unit starts; no Docker rule exists |
| B-02 | reboot after `reserve`, and again after `started` (G8, as revised by H1 and I1-I2) | no unit starts; the next controller is refused, naming the run, its phase and its deadline, and changes nothing; the operator's `recover` (`-e docker_engine_recover=<run>`) rolls the run back |
| B-03 | fail the directory fsync after the commit rename (F9) | the run stays committed and is never rolled back |
| B-04 | a crash between the commit rename and the phase update (H7) | dispatched by the marker: confirmed |
| B-05 | reboot after a failed directory fsync (H7) | dispatched by the marker: confirmed |
| B-06 | an interrupted inert publish, resumed by `recover` (I5) | the publish completes, or the run rolls back; never stranded |

## Probe and controller failures

| id | injection | pass |
| --- | --- | --- |
| P-01 | a failed observation sample (G8) | `observe` triggers the rollback; rolled back |
| P-02 | a failed sample while the observer exits (H7) | the rollback runs with no deadlock; rolled back |
| P-03 | the controller is killed after the observer's challenge (§Acceptance) | the deadline rolls the run back |
| P-04 | the controller's confirmation is withheld (§Acceptance) | the deadline restores FORWARD and removes Docker's chains; SSH answers |
| P-05 | the LLM health stub is stopped during the window (rider 5) | the controller-side rescue runs `rollback`; rolled back |
| P-06 | the new-SSH-session probe fails (rider 5) | the controller-side rescue runs `rollback`; rolled back |
| P-07 | `tailscaled`, `k3s-agent` or a must-stay-running stub is inactive before the change | the role refuses before any change; the host is untouched |

## Classification (Mechanism 6)

| id | found | pass |
| --- | --- | --- |
| M-01 | packages installed by this role's audited set, not confirmed | resumed, then confirmed or rolled back |
| M-02 | a `rollback-partial` run | refused unless `docker_engine_acknowledge_run=<id>` is given |
| M-03 | a foreign Docker package or `/var/lib/docker` state with no `installed` record | refused; nothing is touched |
| M-04 | a non-empty `dpkg --audit` left by an earlier rollback (rider 4) | the next publish completes it inside the fence |
