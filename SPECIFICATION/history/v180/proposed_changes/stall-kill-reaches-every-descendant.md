---
topic: stall-kill-reaches-every-descendant
author: claude-opus-5-5
created_at: 2026-11-10T01:40:45Z
---

## Proposal: A stalled gate's kill reaches every process the run started

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Extend the stall-bound kill from a run's process group to every process attributed to the run, including a descendant that entered a new OS session. This applies to both the suite-green replay leg and the detached gate runner. The rule defines attribution so that it survives re-parenting, forbids signalling unattributed processes, requires each process's pid and pre-signal command line to be named, and names a process that cannot be killed as unended. It adds a Stall bound bullet to the Detached gate runner contract and adds And-lines to the two stall scenarios, with no H2 change. The change is spec-first and owned by livespec-dev-tooling-5lhafp.

### Motivation

Measured by homelab-k8s-worker-nodes on 2026-11-09 and 2026-11-10, and recorded on livespec-dev-tooling-5lhafp:

- Commit gate 20261109T152810Z (worktree homelab-worker-lend-idle-share) was ended by the suite-green leg's 900 s stall window at about 15:46Z.
- PID 210253 survived it. It was an ansible-playbook started at 15:51:31Z by tests/livespec_dev_tooling/test_fabro_factory_registry_role.py on xdist worker gw0. It was launched through uvx and had started its own session, so it was outside the process group the leg killed.
- It was re-parented to init. pytest then deleted its tmp cwd and inventory under it, and it spun in state R for about 9 hours until it was sent SIGTERM by hand.

The ratified text bounds the kill at "the run's whole process group, pytest-xdist workers included". This appears in contracts.md §"Suite-green replay leg" **Progress bound**, in non-functional-requirements.md §"Developer host platforms", and in the two stall scenarios. A descendant in a session of its own is outside that group, so the shipped behaviour conforms while leaving the orphan. The detached gate runner's stall bound in gate-run.sh does the same: it sends TERM and then KILL to `-$gate_pid` only. livespec-dev-tooling-5lhafp is held at the spec-change tier until this ratifies.

legacy-coordinator-agent's design note on 5lhafp (rule K) asks for one design that covers this case and the coverage-directory leak of livespec-dev-tooling-8o8e.16, because both are a run's ending missing what the run created. That leak's lifecycle is proposed separately in `check-runner-coverage-dir-cleanup` (non-functional-requirements.md §"Enforcement-suite invocation"). That proposal governs the check runner's own temp directories on SIGTERM or SIGHUP. This one governs the processes a stalled gate's kill must reach. Each proposal is valid on its own. This proposal's SIGTERM-first order is what lets that sibling's cleanup run, and the sibling adds the cleanup duty.

This aligns with the in-flight v175 revise, livespec-dev-tooling#3955: that revise does not change the process-group sentences this proposal extends.

### Proposed Changes

Wording note: below, a "pytest session" is pytest's own run, and a "new OS session" is the kernel session a process enters with `setsid`. The term "attributed to the run" is defined inside insertion 1, where it first lands in the spec, and the other insertions cross-reference it.

**1. contracts.md §"Suite-green replay leg", **Progress bound** bullet.** Immediately after the sentence "When the leg ends a run, it MUST kill the run's whole process group, pytest-xdist workers included.", change "kill" to "end" in that sentence, so that it does not read as SIGKILL ahead of the SIGTERM-first order. Then insert after it:

> A process is attributed to the run when it descends from the run's root process. This holds through any chain of parents, and it still holds after the process enters a new OS session with `setsid` or is re-parented to init. The leg MUST establish the run's identity before the run starts, so that this attribution holds for a descendant that later leaves the process group. The leg MUST also end every other process attributed to the run, including one that entered a new OS session. A child subreaper or a per-run cgroup are examples of the means. A process the run started that other runs then share, such as a lazily started cache server, is ended like any other. The kill grace period is 30 seconds. The detached gate runner MAY take it from `GATE_STALL_KILL_GRACE_SECONDS`, where a non-numeric or non-positive value means 30 seconds. A value below 30 SHOULD NOT be used for a run whose command can start a check runner. The leg MUST end attributed processes in this order: it sends SIGTERM to every attributed process, including the run's process group; it waits the kill grace period, or until every attributed process has exited if that is sooner; and only then does it send SIGKILL to any attributed process still alive. That order lets a terminated process, such as a check runner, run its own cleanup on SIGTERM before it can be killed. The leg MUST NOT signal a process that is not attributed to the run. It MUST re-verify each process's attribution immediately before signalling it, and it MUST repeat its pass, at most three passes in all, until a pass finds no attributed process alive. Every pass after the first sends SIGKILL directly. The refusal event MUST name, for each process the leg ended outside the run's own process group, its pid and the command line read immediately before it was signalled. An attributed process still alive after the last pass and a further wait of the kill grace period MUST be named in the event as unended, and the commit is refused all the same. Inside a gate Job, a pod teardown that ends every process in the pod satisfies this ending, and no naming is owed for the processes the teardown ends. These descendant-reaching sentences are spec-first: the shipped leg sends SIGKILL straight to the run's process group (`os.killpg`), with no SIGTERM and no grace period. Work item livespec-dev-tooling-5lhafp owns the change.

**2. contracts.md §"Detached gate runner".** Immediately after the **Terminal states** bullet, add this bullet:

> - **Stall bound.** When a gate command has produced neither new output in its run's `output.log` nor a renewal of the run's progress stamp (`LIVESPEC_GATE_RUN_PROGRESS_STAMP`) for the stall window, the runner ends the command. The window is set by `LIVESPEC_SUITE_GREEN_STALL_SECONDS` and defaults to 900 seconds. The run then records a `FAILED` verdict naming that window, never a pass. The runner MUST establish the command's run identity, in the sense of §"Suite-green replay leg" **Progress bound**, before it launches the command. When the runner ends a command, it MUST end every process attributed to the command's run: the command's own process group, and every descendant that entered a new OS session. That includes the pytest session of a suite-green replay leg the command runs, and the wrapper of any detached gate run the command started; that run's own record then reads `DIED_WITHOUT_VERDICT`. The attribution, SIGTERM-then-grace-then-SIGKILL order, re-verification, repeated-pass, naming and unended rules of §"Suite-green replay leg" **Progress bound** apply to the runner unchanged, with `output.log` in place of the refusal event, except that the runner's kill grace period is overridable as stated there; the same gate-Job exception applies. This bullet is spec-first: the shipped `gate-run.sh` sends TERM, waits the grace period, and then sends KILL to the command's process group only. Work item livespec-dev-tooling-5lhafp owns the change.

**3. non-functional-requirements.md §"Developer host platforms", paragraph "**A gate always ends with a verdict.**".** Immediately after the sentence "A session that has stopped making progress MUST be ended, with its whole process group, pytest-xdist workers included.", insert:

> Every other process attributed to that pytest session's run, in the sense of contracts.md §"Suite-green replay leg" **Progress bound**, MUST be ended with it, including one that entered a new OS session. A process attributed to the run MUST NOT still be alive once the gate has recorded its verdict or its no-verdict state, except one named as unended under contracts.md §"Suite-green replay leg" **Progress bound**. The leg and the detached gate runner end runs by those rules, and by §"Detached gate runner" **Stall bound**, wherever they run: on a developer host, in a gate Job, and in a factory sandbox. In a gate Job, a pod teardown that ends every process in the pod satisfies the ending, and no naming is owed for processes the teardown ends.

**4. scenarios.md, `## Scenario: a suite-green run that stops printing output for the stall window is ended`.** Change the line "Then it MUST kill the run's whole process group, pytest-xdist workers included" to "Then it MUST end the run's whole process group, pytest-xdist workers included". Immediately after it, add:

```
And every other process attributed to the run, including one that entered a new OS session, MUST be ended before the commit is refused

And each attributed process found in the first pass MUST receive SIGTERM, and SIGKILL only if it is still alive after the kill grace period

And the refusal event MUST name the pid and command line of each process the leg ended outside the run's process group
```

**5. scenarios.md, `## Scenario: a gate pytest session that stops making progress ends without a pass`.** Immediately after the line "Then the session's whole process group, pytest-xdist workers included, MUST be ended", add:

```
And every other process attributed to the gate's run, including one that entered a new OS session and the pytest session of a nested suite-green leg, MUST be ended before the gate records its verdict or its no-verdict state

And each attributed process found in the first pass MUST receive SIGTERM, and SIGKILL only if it is still alive after the kill grace period
```

No `## ` heading is added, renamed or removed, so `tests/heading-coverage.json` needs no co-edit. Both scenario headings keep their existing registry rows. When the owed tests land, livespec-dev-tooling-5lhafp SHOULD point those rows at tests that start a subprocess in a new OS session.
