# 011 — Dev-host system CPU: process-creation churn from shell loops, plus per-session kernel time

Recorded 2026-11-11 by seat dev-host-test-gate-load, on legacy-coordinator-agent's request. At 04:58Z the coordinator read
the dev host at load 46.7 on 18 CPUs, 15% idle, with 31% SYSTEM time. This note measures where the kernel time goes. Data:
`data/011-system-cpu/`.

## Finding

The dev host's kernel time comes from two sources:

- **Process-creation churn.** Bash loops start a short-lived child for every small step: `awk`, `basename`, `cat`, `tr`,
  `sed`, `date`, `mkdir`, `crictl`.
- **A steady floor of per-session kernel time** spread across about 35 agent sessions.

Neither disk I/O nor tmpfs explains it. Major faults ran at 4 per second, iowait at 1-5%, and `/dev/shm` was 1% used.
`/tmp` was 70% full, but nothing in the sample points at it.

**05:08-05:11Z, during the burst.**

- `mpstat` read 34.0% system, 56.6% user and 7.3% idle (30 s), at load 61.4.
- The host created 457 processes per second and took 175,000 minor page faults per second.
- A 20 s `bpftrace` exec count saw 9,074 execs (454/s). Nearly all were children of `bash`: `awk` 1,356, `bash` 933,
  `basename` 857, `crictl` 787, `cat` 436, `tr` 408, `sed` 307, `date` 297.
- Processes that EXITED inside those 20 s had used 6.92 cores: `bash` 2.32, `python3` 1.32.
- `pidstat`, which sees only processes that live across a whole 1 s sample, attributed just 4.11 system cores. That gap
  is the short-lived processes.
- 30% of the execs descended from one host-local pytest: legacy-coordinator-agent's accidental `just hook_gate=1 check` in
  the primary, started 04:32:05Z. A zsh command substitution inside a double-quoted `bd comment` ran it, and the
  coordinator ended it about 05:25Z. Its `test_2000_concurrent_warms_keep_an_earlier_pin_tag_a_container_references` forks
  thousands of `sandbox-image-warm.sh` shells, each calling `crictl`, `awk` and `basename`.

**05:25-05:26Z, after that run ended.**

- Execs fell to 138/s, but system time stayed at 33.2% (`mpstat` 05:26Z: 44.9% user, 15.4% idle, load 86).
- The remaining execs are diffuse. 31% had ancestors already gone. The rest came from:
  - seats' scratchpad watcher loops: `turn-watch.sh` 5.8%, `direct-*.sh` 4.7%, `seat-events.sh` 3.9%,
    `ending-screen.sh` 1.9%, and `stall-check.sh`;
  - `gate_remote_delegate run` and `pre_commit_delegate run` poll loops, 4.3% and 2.0%;
  - two orchestrator `dispatcher.py` payload processes, 3.8% and 2.2%;
  - each Claude session's own shell calls, about 2% apiece.
- Among long-lived processes, `claude` (all sessions together) held 1.28 system cores. Next were `python3` 0.49,
  `herdr` 0.38 (system-heavy: 0.38 system against 0.23 user) and `bash` 0.37.

## Levers

1. **Seat watcher loops: the cheapest lever.** Most of them poll by forking `date`, `awk`, `basename`, `cat` or `tr` on
   every iteration. Rewriting them with bash builtins (`printf '%(...)T'`, `${var##*/}`, `read`, `[[ ]]`), polling less
   often, or replacing them with the harness's own background-task notifications would remove most of the 138/s steady
   churn. `livespec-dev-tooling-2zotza` is the same defect class in `gate-run.sh list`.
2. **Host-local full suites.** The `test_2000_concurrent_warms` family is heavy by design and normally runs inside gate
   Jobs. The coordinator's interim rule and qpgiip's guard keep the full suite off the dev host.
3. **Per-session kernel floor.** About 0.04 system cores per Claude session, times 35 sessions. That is a sizing fact,
   not a defect. It is left as is.

## Blind spots

- Per-process system time for short-lived processes is not separated from user time in the exit accounting. The
  6.92-core exited-process figure is total runtime.
- The 05:26Z system share (33%) is not fully attributed. `pidstat` and the exit trace together leave about 1-2 system
  cores unnamed, plausibly kernel work done on behalf of exec and fault handling (`kworker` threads showed 0.43 cores in
  the exit trace).
- Each sample is a single window of 10-30 s, not a 4-hour measurement.
